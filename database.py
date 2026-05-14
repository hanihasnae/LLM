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

    # Table users — comptes entreprise avec authentification
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id                        SERIAL PRIMARY KEY,
            email                     VARCHAR(255) UNIQUE NOT NULL,
            password_hash             VARCHAR(255) NOT NULL,
            nom_entreprise            VARCHAR(100) NOT NULL DEFAULT 'Mon Entreprise',
            secteur                   VARCHAR(50)  NOT NULL DEFAULT 'Ciment',
            cn_code                   VARCHAR(20),
            production_annuelle_tonnes FLOAT       DEFAULT 1000.0,
            route_production          VARCHAR(10),
            created_at                TIMESTAMP    DEFAULT NOW()
        );
    """)

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

    # Migration : isolation par utilisateur (activities)
    cursor.execute("""
        ALTER TABLE activities
            ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id);
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
    cursor.execute("""
        ALTER TABLE company_profile
            ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id);
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

    # Migration : user_id sur scope3_entries (doit être après la création de la table)
    cursor.execute("""
        ALTER TABLE scope3_entries
            ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id);
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

    # Table cement_types — types de ciment EN 197-1 avec ratios clinker
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cement_types (
            id                  SERIAL PRIMARY KEY,
            code                VARCHAR(20) UNIQUE NOT NULL,
            label               VARCHAR(120) NOT NULL,
            cn_code             VARCHAR(20),
            clinker_typical_pct FLOAT NOT NULL,  -- % clinker typique (valeur médiane EN 197-1)
            clinker_pct_min     FLOAT,
            clinker_pct_max     FLOAT,
            eu_benchmark_tco2_t FLOAT,           -- benchmark UE 2025/2620 (Colonne B)
            standard            VARCHAR(50) DEFAULT 'EN 197-1',
            notes               TEXT,
            active              BOOLEAN DEFAULT true,
            created_at          TIMESTAMP DEFAULT NOW()
        );
    """)

    # Table cement_emission_factors — facteurs d'émission par défaut Maroc 2026
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cement_emission_factors (
            id           SERIAL PRIMARY KEY,
            factor_name  VARCHAR(50) UNIQUE NOT NULL,
            value        FLOAT NOT NULL,
            unit         VARCHAR(30),
            source       VARCHAR(100) DEFAULT 'CBAM IR 2025/2621 — Maroc 2026',
            notes        TEXT,
            created_at   TIMESTAMP DEFAULT NOW()
        );
    """)

    # Table fertilizer_types — types d'engrais azotés CBAM avec teneurs en azote EN std
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fertilizer_types (
            id                    SERIAL PRIMARY KEY,
            code                  VARCHAR(20) UNIQUE NOT NULL,
            label                 VARCHAR(120) NOT NULL,
            formula               VARCHAR(30),
            cn_code               VARCHAR(20),
            n_pct_std             FLOAT NOT NULL,    -- % N standard (base de calcul)
            n_pct_tolerance       FLOAT DEFAULT 10.0, -- ±% tolérance acceptable
            emission_intensity    FLOAT NOT NULL,    -- tCO2e/t produit (Maroc 2026, SMR)
            eu_benchmark_tco2_t   FLOAT,             -- benchmark CBAM Colonne B
            notes                 TEXT,
            active                BOOLEAN DEFAULT true,
            created_at            TIMESTAMP DEFAULT NOW()
        );
    """)

    # Table pfc_default_values — valeurs EU par défaut pour émissions PFC aluminium
    # (Règl. UE 2025/2621 — IPCC AR6 2024)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pfc_default_values (
            id               SERIAL PRIMARY KEY,
            country_code     VARCHAR(5)   NOT NULL DEFAULT 'MA',
            production_type  VARCHAR(20)  NOT NULL,   -- 'primary' | 'secondary'
            year_from        INTEGER      NOT NULL DEFAULT 2026,
            cf4_kg_t         FLOAT        NOT NULL,   -- kg CF₄ par tonne Al
            c2f6_kg_t        FLOAT        NOT NULL,   -- kg C₂F₆ par tonne Al
            c2f6_cf4_ratio   FLOAT,
            source           VARCHAR(100) DEFAULT 'CBAM IR 2025/2621',
            notes            TEXT,
            created_at       TIMESTAMP    DEFAULT NOW(),
            UNIQUE(country_code, production_type, year_from)
        );
    """)

    # Table hydrogen_production_methods — procédés de production H₂ (CBAM Colonne A)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS hydrogen_production_methods (
            id                          SERIAL PRIMARY KEY,
            code                        VARCHAR(30) UNIQUE NOT NULL,
            label                       TEXT NOT NULL,
            is_electrolysis             BOOLEAN NOT NULL DEFAULT false,
            direct_intensity_tco2_t     FLOAT,          -- NULL pour électrolyse
            default_elec_source_code    VARCHAR(30),    -- source élec par défaut
            default_kwh_per_kg          FLOAT,          -- conso élec par défaut (kWh/kg H₂)
            eu_benchmark_tco2_t         FLOAT DEFAULT 5.089,
            cn_code                     VARCHAR(20) DEFAULT '28044000',
            notes                       TEXT,
            active                      BOOLEAN DEFAULT true,
            created_at                  TIMESTAMP DEFAULT NOW()
        );
    """)

    # Table hydrogen_electricity_sources — intensités carbone par source électrique
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS hydrogen_electricity_sources (
            id                  SERIAL PRIMARY KEY,
            code                VARCHAR(30) UNIQUE NOT NULL,
            label               TEXT NOT NULL,
            intensity_tco2_mwh  FLOAT NOT NULL,
            notes               TEXT,
            active              BOOLEAN DEFAULT true,
            created_at          TIMESTAMP DEFAULT NOW()
        );
    """)

    # Table hydrogen_electrolysis_types — consommation électrique par technologie
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS hydrogen_electrolysis_types (
            id          SERIAL PRIMARY KEY,
            code        VARCHAR(30) UNIQUE NOT NULL,
            label       TEXT NOT NULL,
            kwh_per_kg  FLOAT NOT NULL,
            notes       TEXT,
            active      BOOLEAN DEFAULT true,
            created_at  TIMESTAMP DEFAULT NOW()
        );
    """)

    conn.commit()
    cursor.close()
    conn.close()
    print("Tables creees avec succes !")

def insert_fertilizer_defaults():
    """Insère les 6 types d'engrais azotés CBAM avec émissions par défaut (Maroc 2026, SMR)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM fertilizer_types")
    if cursor.fetchone()["count"] > 0:
        cursor.close(); conn.close(); return

    # (code, label, formula, cn_code, n_std%, tolerance%, intensity tCO2e/t, benchmark, notes)
    # Intensités calculées : facteur base N = 1.94 tCO2e/t N (SMR Maroc) avec ajustements
    rows = [
        ('AMMONIA',  'Ammonia (NH₃) 99.8%',              'NH₃',          '28141000',
         82.4, 10.0, 1.60, 0.46,
         'Ammoniac anhydre — précurseur universel. Intensité = 1.94 × 0.824. '
         'Benchmark CN 2814 10 00.'),

        ('UREA',     'Urea 46% N',                        '(NH₂)₂CO',    '31021000',
         46.0, 10.0, 0.74, 0.42,
         'Urée prillée/granulée. Intensité réduite : CO₂ capturé lors de la synthèse urée '
         '(2NH₃ + CO₂ → CO(NH₂)₂ + H₂O). Benchmark CN 3102 10 00.'),

        ('AN_34',    'Ammonium Nitrate 34.5% N',          'NH₄NO₃',      '31023090',
         34.5, 10.0, 0.59, 0.27,
         'Ammonitrate haut titre (34.5% N). Inclut N₂O de la synthèse d\'acide nitrique '
         '(GWP 265). CN 3102 30 90.'),

        ('AN_28',    'Ammonium Nitrate 28% N',             'NH₄NO₃',      '31023010',
         28.0, 10.0, 0.48, 0.22,
         'Solution ammonitrate 28% N. CN 3102 30 10.'),

        ('AS_21',    'Ammonium Sulphate 21% N',            '(NH₄)₂SO₄',   '31022100',
         21.0, 10.0, 0.22, 0.11,
         'Sulfate d\'ammonium — sous-produit caprolactame ou acide acrylique. '
         'Émissions allouées faibles (by-product). CN 3102 21 00.'),

        ('HNO3_15',  'Nitric Acid (HNO₃) 15% N',         'HNO₃',        '28081000',
         22.2, 10.0, 0.45, 0.20,
         'Acide nitrique industriel (pureté 68% ≈ 22.2% N). Inclut N₂O procédé Ostwald. '
         'CN 2808 00 00.'),
    ]
    cursor.executemany("""
        INSERT INTO fertilizer_types
            (code, label, formula, cn_code, n_pct_std, n_pct_tolerance,
             emission_intensity, eu_benchmark_tco2_t, notes)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (code) DO NOTHING
    """, rows)
    conn.commit()
    cursor.close(); conn.close()
    print("✅ Types d'engrais insérés !")


def insert_hydrogen_defaults():
    """Insère les procédés H₂, sources électriques et types d'électrolyse pour CBAM Colonne A."""
    conn = get_connection()
    cursor = conn.cursor()

    # ── Procédés de production ─────────────────────────────────────────────────
    cursor.execute("SELECT COUNT(*) FROM hydrogen_production_methods")
    if cursor.fetchone()["count"] == 0:
        # (code, label, is_elec, direct_intensity, default_elec_src, default_kwh/kg, benchmark, cn, notes)
        methods = [
            ('SMR_NG',        'SMR — Vaporeformage gaz naturel (H₂ gris)',
             False, 11.1,  None,           None, 5.089, '28044000',
             'IPCC AR6 · Gaz naturel sans CCS · Maroc 2026'),
            ('ELEC_GRID',     'Électrolyse — Réseau électrique Maroc',
             True,  None,  'GRID_MAROC',   48.0, 5.089, '28044000',
             'ONEE réseau 2026 — 0.08 tCO₂/MWh · intensité = kwh_per_kg × 0.08'),
            ('ELEC_RE',       'Électrolyse — Renouvelable certifiée',
             True,  None,  'RE_CERTIFIED', 48.0, 5.089, '28044000',
             'Éolien / Solaire avec PPA certifié · intensité ≈ 0 tCO₂/t'),
            ('BIOMASS_REFORM','Reformage biomasse (H₂ bas carbone)',
             False, 2.0,   None,           None, 5.089, '28044000',
             'Biomasse certifiée ISCC+ · IEA 2024 · 2.0 tCO₂/t H₂'),
            ('ELEC_NUCLEAR',  'Électrolyse nucléaire (H₂ futur)',
             True,  None,  'NUCLEAR',      48.0, 5.089, '28044000',
             'EPR2 / SMR nucléaire · IPCC 2023 · ~0.012 tCO₂/MWh'),
        ]
        cursor.executemany("""
            INSERT INTO hydrogen_production_methods
                (code, label, is_electrolysis, direct_intensity_tco2_t,
                 default_elec_source_code, default_kwh_per_kg,
                 eu_benchmark_tco2_t, cn_code, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (code) DO NOTHING
        """, methods)

    # ── Sources électriques ────────────────────────────────────────────────────
    cursor.execute("SELECT COUNT(*) FROM hydrogen_electricity_sources")
    if cursor.fetchone()["count"] == 0:
        sources = [
            ('GRID_MAROC',   'Réseau Maroc (ONEE)',           0.080,
             'Facteur réseau Maroc 2026 · CBAM IR 2025/2621'),
            ('RE_CERTIFIED', 'Renouvelable certifiée',         0.000,
             'Éolien / Solaire avec PPA ou garanties d\'origine'),
            ('GAS_CCS',      'Gaz naturel + CCS',              1.500,
             'Capture carbone 90% efficacité · IPCC AR6 2023'),
            ('NUCLEAR',      'Nucléaire (faible carbone)',      0.012,
             'Médiane IPCC AR6 2023 · EPR2 / SMR'),
        ]
        cursor.executemany("""
            INSERT INTO hydrogen_electricity_sources (code, label, intensity_tco2_mwh, notes)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (code) DO NOTHING
        """, sources)

    # ── Types d'électrolyse ────────────────────────────────────────────────────
    cursor.execute("SELECT COUNT(*) FROM hydrogen_electrolysis_types")
    if cursor.fetchone()["count"] == 0:
        elec_types = [
            ('STANDARD_AEL', 'Standard Alkaline (AEL)',        48.0,
             'IEA 2024 — rendement typique électrolyseur industriel'),
            ('PEM',          'PEM — Proton Exchange Membrane', 50.0,
             'Proton Exchange Membrane · IEA 2024 · haute pureté'),
            ('ALKALINE_ADV', 'Alkaline haute performance',     55.0,
             'Alkaline avancé basse température · IRENA 2023'),
        ]
        cursor.executemany("""
            INSERT INTO hydrogen_electrolysis_types (code, label, kwh_per_kg, notes)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (code) DO NOTHING
        """, elec_types)

    conn.commit()
    cursor.close(); conn.close()
    print("✅ Données Hydrogène insérées !")


def insert_cement_defaults():
    """Insère les types de ciment EN 197-1 et les facteurs d'émission Maroc 2026."""
    conn = get_connection()
    cursor = conn.cursor()

    # ── Types de ciment (ratio clinker EN 197-1, benchmark Colonne B CBAM) ──
    cursor.execute("SELECT COUNT(*) FROM cement_types")
    if cursor.fetchone()["count"] == 0:
        rows = [
            # (code, label, cn_code, clinker_typical_pct, min, max, benchmark, notes)
            ('CEM_I',     'CEM I — Portland pur (95–100% clinker)',    '25232900', 97.5, 95.0, 100.0, 0.666,
             'Portland pur — four voie sèche (A). BMG_B Colonne B = 0.666'),
            ('CEM_II_A',  'CEM II/A — Composite (80–94% clinker)',     '25232900', 87.0, 80.0,  94.0, 0.666,
             'Ciment composé — constituants secondaires 6-20%'),
            ('CEM_II_B',  'CEM II/B — Composite (65–79% clinker)',     '25232900', 72.0, 65.0,  79.0, 0.666,
             'Ciment composé — constituants secondaires 21-35%'),
            ('CEM_III_A', 'CEM III/A — Laitier haut-fourneau (40–64%)', '25232900', 52.0, 40.0, 64.0, 0.666,
             'Ciment de laitier — substitution laitier 36-60%'),
            ('CEM_VI',    'CEM VI — Bas-carbone (35–50% clinker)',     '25232900', 42.5, 35.0,  50.0, 0.666,
             'Ciment bas-carbone — composition multicomposant (EN 197-1:2023)'),
            ('CLINKER',   'Clinker pur (100%)',                         '25231000', 100.0,100.0,100.0, 0.825,
             'Clinker Portland brut — benchmark CN 2523 10 00'),
        ]
        cursor.executemany("""
            INSERT INTO cement_types
                (code, label, cn_code, clinker_typical_pct, clinker_pct_min,
                 clinker_pct_max, eu_benchmark_tco2_t, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (code) DO NOTHING
        """, rows)
        print("✅ Types de ciment insérés !")

    # ── Facteurs d'émission par défaut Maroc 2026 ──
    cursor.execute("SELECT COUNT(*) FROM cement_emission_factors")
    if cursor.fetchone()["count"] == 0:
        factors = [
            ('clinker_calcination', 0.525, 'tCO2/t clinker',
             'Stoichiométrie CaCO3→CaO+CO2 — constante IPCC/CBAM'),
            ('kiln_fuel_default',   0.285, 'tCO2/t ciment',
             'Combustion four rotatif — valeur par défaut Maroc 2026 (CBAM IR 2025/2621)'),
            ('electricity_default', 0.080, 'tCO2/t ciment',
             'Consommation électrique broyage/finition — réseau Maroc (0.625 kgCO2/kWh × ~128 kWh/t)'),
        ]
        cursor.executemany("""
            INSERT INTO cement_emission_factors (factor_name, value, unit, notes)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (factor_name) DO NOTHING
        """, factors)
        print("✅ Facteurs d'émission ciment insérés !")

    conn.commit()
    cursor.close()
    conn.close()


def insert_pfc_defaults():
    """Insère les valeurs PFC EU par défaut pour l'aluminium (Maroc 2026)."""
    conn = get_connection()
    cursor = conn.cursor()

    # Vérifie si les valeurs existent déjà
    cursor.execute("SELECT COUNT(*) FROM pfc_default_values WHERE country_code='MA' AND year_from=2026")
    if cursor.fetchone()["count"] > 0:
        cursor.close()
        conn.close()
        return

    # Primary aluminium (Hall-Héroult prebake) — EU average CBAM defaults 2026
    # Secondary aluminium (scrap remelting) — pas d'effet d'anode → PFC = 0
    rows = [
        ('MA', 'primary',   2026, 0.053,  0.0053, 0.10,
         'CBAM IR 2025/2621', 'Aluminium primaire — électrolyse Hall-Héroult (valeur UE par défaut)'),
        ('MA', 'secondary', 2026, 0.0,    0.0,    None,
         'CBAM IR 2025/2621', 'Aluminium secondaire — refonte ferraille (pas d\'effet d\'anode)'),
    ]
    cursor.executemany("""
        INSERT INTO pfc_default_values
            (country_code, production_type, year_from, cf4_kg_t, c2f6_kg_t,
             c2f6_cf4_ratio, source, notes)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (country_code, production_type, year_from) DO NOTHING
    """, rows)
    conn.commit()
    cursor.close()
    conn.close()
    print("✅ Valeurs PFC aluminium insérées !")


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