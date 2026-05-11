# database.py
# Ce fichier gère la connexion entre FastAPI et PostgreSQL

import psycopg2
from psycopg2.extras import RealDictCursor
import os
from dotenv import load_dotenv

# Charge les variables du fichier .env
load_dotenv()

def get_connection():
    """Ouvre une connexion à la base de données"""
    conn = psycopg2.connect(
        os.getenv("DATABASE_URL"),
        cursor_factory=RealDictCursor  # retourne les données en format dictionnaire
    )
    return conn

def create_tables():
    """Crée toutes les tables si elles n'existent pas encore"""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Table 1 : les activités (ex: consommation électricité, fuel...)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS activities (
            id SERIAL PRIMARY KEY,
            source VARCHAR(50) NOT NULL,      -- 'electricity', 'fuel', 'gas'
            quantity FLOAT NOT NULL,           -- combien (ex: 500)
            unit VARCHAR(20) NOT NULL,         -- 'kWh', 'litres', 'm3'
            date DATE NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        );
    """)
    
    # Table 2 : les facteurs d'émission (normes GHG Protocol)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS emission_factors (
            id SERIAL PRIMARY KEY,
            energy_type VARCHAR(50) NOT NULL,  -- 'electricity', 'fuel', 'gas'
            factor FLOAT NOT NULL,             -- kg CO2 par unité
            unit VARCHAR(20) NOT NULL,         -- 'kg CO2/kWh'
            scope INTEGER NOT NULL             -- 1 ou 2
        );
    """)
    
    # Table 3 : les émissions calculées
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS emissions (
            id SERIAL PRIMARY KEY,
            activity_id INTEGER REFERENCES activities(id),
            co2_kg DOUBLE PRECISION NOT NULL,             -- émissions en kg CO2
            scope INTEGER NOT NULL,            -- Scope 1 ou 2
            calculated_at TIMESTAMP DEFAULT NOW()
        );
    """)
    
    # Colonnes de traçabilité soft-delete (ajoutées si absentes)
    cursor.execute("""
        ALTER TABLE activities
            ADD COLUMN IF NOT EXISTS actif           BOOLEAN DEFAULT true,
            ADD COLUMN IF NOT EXISTS raison          TEXT,
            ADD COLUMN IF NOT EXISTS original_id     INTEGER,
            ADD COLUMN IF NOT EXISTS source_document VARCHAR(255),
            ADD COLUMN IF NOT EXISTS methode_saisie  VARCHAR(50) DEFAULT 'manuel';
    """)
    cursor.execute("""
        ALTER TABLE emissions
            ADD COLUMN IF NOT EXISTS actif BOOLEAN DEFAULT true;
    """)

    # Table company_profile — profil CBAM entreprise (une seule ligne)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS company_profile (
            id                        SERIAL PRIMARY KEY,
            nom_entreprise            VARCHAR(100) DEFAULT 'Mon Entreprise',
            secteur                   VARCHAR(50),
            cn_code                   VARCHAR(20),
            production_annuelle_tonnes FLOAT,
            route_production          VARCHAR(10) DEFAULT NULL,
            updated_at                TIMESTAMP DEFAULT NOW()
        );
    """)
    # Migration: élargit la colonne si elle est encore CHAR(1)
    cursor.execute("""
        ALTER TABLE company_profile
            ALTER COLUMN route_production TYPE VARCHAR(10);
    """)

    # Table audit_log — traçabilité CBAM/ISO 14064
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id          SERIAL PRIMARY KEY,
            activity_id INTEGER NOT NULL,
            ancien_id   INTEGER,
            nouveau_id  INTEGER,
            changement  TEXT,
            raison      TEXT,
            created_at  TIMESTAMP DEFAULT NOW()
        );
    """)

    # Table journal_modifications — détail des changements ISO 14064
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS journal_modifications (
            id           SERIAL PRIMARY KEY,
            activity_id  INTEGER,
            champ_modifie TEXT,
            ancienne_val  TEXT,
            nouvelle_val  TEXT,
            raison        TEXT,
            created_at    TIMESTAMP DEFAULT NOW()
        );
    """)

    # Table scope3_entries — émissions chaîne de valeur (GHG Protocol cat 1/3/4/5/9/12)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scope3_entries (
            id               SERIAL PRIMARY KEY,
            category         INTEGER NOT NULL,
            category_name    VARCHAR(100),
            direction        VARCHAR(20),          -- 'upstream' ou 'downstream'
            description      TEXT,
            source_type      VARCHAR(100),
            quantity         FLOAT,
            unit             VARCHAR(20),
            emission_factor  FLOAT,
            co2_kg           FLOAT,
            distance_km      FLOAT,
            weight_tonnes    FLOAT,
            transport_mode   VARCHAR(20),
            origin           TEXT,
            destination      TEXT,
            supplier_name    VARCHAR(100),
            supplier_country VARCHAR(100),
            date             DATE,
            data_quality     VARCHAR(20) DEFAULT 'estimated',
            source_document  TEXT,
            period_quarter   INTEGER,
            period_year      INTEGER,
            actif            BOOLEAN DEFAULT true,
            raison           TEXT,
            updated_at       TIMESTAMP DEFAULT NOW(),
            created_at       TIMESTAMP DEFAULT NOW()
        );
    """)

    # Table journal_scope3 — traçabilité soft-delete Scope 3
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS journal_scope3 (
            id               SERIAL PRIMARY KEY,
            scope3_entry_id  INTEGER REFERENCES scope3_entries(id),
            champ_modifie    TEXT,
            ancienne_val     TEXT,
            nouvelle_val     TEXT,
            raison           TEXT,
            created_at       TIMESTAMP DEFAULT NOW()
        );
    """)

    conn.commit()
    cursor.close()
    conn.close()
    print("Tables creees avec succes !")

def insert_default_factors():
    """Insère les facteurs d'émission standards (GHG Protocol Maroc)"""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Vérifie si les facteurs existent déjà
    cursor.execute("SELECT COUNT(*) FROM emission_factors")
    count = cursor.fetchone()["count"]
    
    factors = [
        # (facteur_kg_CO2, unité, scope, type_énergie)
        (0.625, "kg CO2/kWh",   2, "electricity"),
        (3.24,  "kg CO2/litre", 1, "fuel"),
        (2.02,  "kg CO2/m3",    1, "gas"),
    ]

    if count == 0:
        cursor.executemany("""
            INSERT INTO emission_factors (energy_type, factor, unit, scope)
            VALUES (%s, %s, %s, %s)
        """, [(t, f, u, s) for f, u, s, t in factors])
        print("✅ Facteurs d'émission insérés !")
    else:
        # Met à jour les facteurs existants
        cursor.executemany("""
            UPDATE emission_factors SET factor = %s, unit = %s, scope = %s
            WHERE energy_type = %s
        """, factors)
        print("✅ Facteurs d'émission mis à jour !")

    conn.commit()
    
    cursor.close()
    conn.close()