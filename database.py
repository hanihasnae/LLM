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
            co2_kg FLOAT NOT NULL,             -- émissions en kg CO2
            scope INTEGER NOT NULL,            -- Scope 1 ou 2
            calculated_at TIMESTAMP DEFAULT NOW()
        );
    """)
    
    conn.commit()
    cursor.close()
    conn.close()
    print("✅ Tables créées avec succès !")

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