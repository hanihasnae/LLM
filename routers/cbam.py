# routers/cbam.py
# Endpoints CBAM — Conformité et analyse financière
 
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from cbam_engine import (
    rechercher_benchmark,
    calculer_conformite,
    construire_contexte_cbam,
    get_tous_benchmarks_secteur,
    charger_benchmarks,
    PRIX_CARBONE_EU
)
from cbam_reference_complete import get_colonne_obligatoire, CBAM_REFERENCE
from database import get_connection

# Mapping catégorie Excel → secteur FR + clé CBAM
_CAT_TO_SECTEUR = {
    "iron & steel": ("Acier/Fer",  "Iron & Steel"),
    "aluminium":    ("Aluminium",  "Aluminium"),
    "cement":       ("Ciment",     "Cement"),
    "fertilisers":  ("Engrais",    "Fertilisers"),
    "hydrogen":     ("Hydrogène",  "Hydrogen"),
}
 
router = APIRouter(prefix="/cbam", tags=["CBAM"])
 
 
# ── MODÈLES ───────────────────────────────────────
 
class ConformiteInput(BaseModel):
    production_tonnes: float
    cn_code:           Optional[str]   = None
    mot_cle:           Optional[str]   = None
    secteur:           Optional[str]   = None
    route:             Optional[str]   = None
    colonne:           Optional[str]   = 'A'
    prix_carbone:      Optional[float] = PRIX_CARBONE_EU
    annee:             Optional[int]   = None   # None = toutes les années
    trimestre:         Optional[int]   = None   # 1-4, None = toute l'année
 
 
# ══════════════════════════════════════════════════
# ENDPOINT 1 — Recherche benchmark
# ══════════════════════════════════════════════════
 
@router.get("/benchmark")
def get_benchmark(
    cn_code:  Optional[str] = None,
    mot_cle:  Optional[str] = None,
    colonne:  str = 'A'
):
    """
    Recherche un benchmark CBAM par code NC ou mot-clé.
    
    Exemples :
    - /cbam/benchmark?cn_code=72011011
    - /cbam/benchmark?mot_cle=steel
    - /cbam/benchmark?mot_cle=aluminium
    - /cbam/benchmark?mot_cle=cement
    """
    if not cn_code and not mot_cle:
        raise HTTPException(
            status_code=400,
            detail="Fournir cn_code ou mot_cle"
        )
 
    resultats = rechercher_benchmark(
        cn_code=cn_code,
        mot_cle=mot_cle,
        colonne=colonne
    )
 
    if not resultats:
        raise HTTPException(
            status_code=404,
            detail=f"Aucun benchmark trouvé"
        )
 
    return {
        "count":      len(resultats),
        "colonne":    colonne,
        "benchmarks": resultats[:20]  # Max 20 résultats
    }
 
 
# ══════════════════════════════════════════════════
# ENDPOINT 2 — Conformité automatique
# Utilise les données réelles de la DB
# ══════════════════════════════════════════════════
 
@router.post("/conformite")
def calculer_conformite_endpoint(data: ConformiteInput):
    """
    Calcule la conformité CBAM avec les émissions réelles de la DB.
    
    Body :
    {
      "production_tonnes": 500,
      "cn_code": "72011011",     ← ou
      "mot_cle": "steel",
      "colonne": "A",
      "prix_carbone": 65.0
    }
    """
 
    # Récupère les émissions réelles de la DB
    conn   = get_connection()
    cursor = conn.cursor()
 
    cursor.execute("""
        SELECT 
            SUM(e.co2_kg) as total_co2_kg,
            COUNT(*)      as nb_activites
        FROM emissions e
        JOIN activities a ON a.id = e.activity_id
        WHERE a.actif = true
        AND e.actif   = true
    """)
    row = cursor.fetchone()
    cursor.close()
    conn.close()
 
    total_co2_kg = float(row["total_co2_kg"] or 0)
 
    if total_co2_kg == 0:
        raise HTTPException(
            status_code=400,
            detail="Aucune émission enregistrée. Ajoutez des activités d'abord."
        )
 
    # Calcule la conformité
    rapport = calculer_conformite(
        total_co2_kg      = total_co2_kg,
        production_tonnes = data.production_tonnes,
        cn_code           = data.cn_code,
        mot_cle           = data.mot_cle,
        colonne           = data.colonne or 'A',
        prix_carbone      = data.prix_carbone or PRIX_CARBONE_EU
    )
 
    return rapport
 
 
# ══════════════════════════════════════════════════
# ENDPOINT 3 — Rapport complet CBAM
# ══════════════════════════════════════════════════
 
@router.post("/rapport-complet")
def rapport_cbam_complet(data: ConformiteInput):
    """
    Génère un rapport CBAM complet avec :
    - Conformité par scope
    - Exposition financière
    - Recommandations
    - Contexte pour le LLM
    """
    conn   = get_connection()
    cursor = conn.cursor()

    # ── Filtre période ────────────────────────────────────────────────
    _FR_TO_CBAM = {
        "Acier/Fer": "Iron & Steel", "Aluminium": "Aluminium",
        "Ciment":    "Cement",       "Engrais":   "Fertilisers",
        "Hydrogène": "Hydrogen",
    }
    secteur_cbam = _FR_TO_CBAM.get(data.secteur or "", data.secteur or "")
    colonne = get_colonne_obligatoire(secteur_cbam) if secteur_cbam else (data.colonne or 'A')

    periode_where = ""
    periode_params: list = []
    if data.annee:
        periode_where += " AND EXTRACT(YEAR FROM a.date) = %s"
        periode_params.append(data.annee)
    if data.trimestre and data.annee:
        mois_debut = (data.trimestre - 1) * 3 + 1
        mois_fin   = mois_debut + 2
        periode_where += " AND EXTRACT(MONTH FROM a.date) BETWEEN %s AND %s"
        periode_params.extend([mois_debut, mois_fin])

    base_where = "WHERE a.actif = true AND e.actif = true" + periode_where

    # ── CO2 total et par scope ────────────────────────────────────────
    cursor.execute(
        f"SELECT SUM(e.co2_kg) as total FROM emissions e JOIN activities a ON a.id = e.activity_id {base_where}",
        periode_params
    )
    total_co2_kg = float(cursor.fetchone()["total"] or 0)

    cursor.execute(
        f"SELECT e.scope, SUM(e.co2_kg) as co2_kg FROM emissions e JOIN activities a ON a.id = e.activity_id {base_where} GROUP BY e.scope",
        periode_params
    )
    scopes = {row["scope"]: float(row["co2_kg"]) for row in cursor.fetchall()}

    # ── Par source ────────────────────────────────────────────────────
    cursor.execute(
        f"SELECT a.source, SUM(e.co2_kg) as co2_kg FROM activities a JOIN emissions e ON e.activity_id = a.id {base_where} GROUP BY a.source ORDER BY co2_kg DESC",
        periode_params
    )
    sources = [dict(r) for r in cursor.fetchall()]

    # ── Période effective en DB ───────────────────────────────────────
    cursor.execute(
        f"SELECT MIN(a.date) as date_min, MAX(a.date) as date_max, COUNT(DISTINCT a.id) as nb FROM activities a JOIN emissions e ON e.activity_id = a.id {base_where}",
        periode_params
    )
    periode_row = dict(cursor.fetchone() or {})

    cursor.close()
    conn.close()

    # ── Colonne A → Scope 1 seulement | Colonne B → Scope 1 + 2 ────────
    scope1_kg = scopes.get(1, 0.0)
    scope2_kg = scopes.get(2, 0.0)
    co2_pour_cbam = scope1_kg if colonne == 'A' else (scope1_kg + scope2_kg)

    # Calcul conformité principal
    rapport = calculer_conformite(
        total_co2_kg      = co2_pour_cbam,
        production_tonnes = data.production_tonnes,
        cn_code           = data.cn_code,
        mot_cle           = data.mot_cle,
        secteur           = secteur_cbam,   # clé anglaise → benchmark correct
        route             = data.route,
        colonne           = colonne,
        prix_carbone      = data.prix_carbone or PRIX_CARBONE_EU
    )

    # Normalise le champ benchmark : toujours un nombre ou null (jamais un dict)
    bmg_raw = rapport.get("benchmark")
    if isinstance(bmg_raw, dict):
        rapport["benchmark"] = bmg_raw.get("bmg_selectionne")

    # Contexte LLM
    contexte_llm = construire_contexte_cbam(
        total_co2_kg      = co2_pour_cbam,
        production_tonnes = data.production_tonnes,
        cn_code           = data.cn_code,
        mot_cle           = data.mot_cle,
        secteur           = secteur_cbam,
        route             = data.route,
    )

    return {
        **rapport,
        "detail_scopes":      scopes,
        "detail_sources":     sources,
        "contexte_llm":       contexte_llm,
        "colonne_utilisee":   colonne,
        "co2_utilise_kg":     round(co2_pour_cbam, 2),
        "co2_scope1_kg":      round(scope1_kg, 2),
        "co2_scope2_kg":      round(scope2_kg, 2),
        "total_co2_kg":       round(total_co2_kg, 2),
        "reglementation":     "Règlement UE 2025/2620 — Commission Implementing Regulation",
        "periode_date_min":   str(periode_row.get("date_min") or ""),
        "periode_date_max":   str(periode_row.get("date_max") or ""),
        "nb_activites":       int(periode_row.get("nb") or 0),
        "filtre_annee":       data.annee,
        "filtre_trimestre":   data.trimestre,
        "colonne_explication": (
            "Scope 1 uniquement (émissions directes) — électricité exclue du calcul CBAM"
            if colonne == 'A' else
            "Scope 1 + Scope 2 (émissions directes + électricité incluses dans le calcul CBAM)"
        ),
    }
 
 
# ══════════════════════════════════════════════════
# ENDPOINT 4 — Secteurs disponibles
# ══════════════════════════════════════════════════
 
@router.get("/secteurs")
def get_secteurs():
    """Liste tous les secteurs CBAM disponibles"""
    return {
        "secteurs": [
            {
                "nom":         "Iron & Steel",
                "description": "Fer, acier et produits dérivés",
                "nb_produits": 478,
                "mot_cle":     "steel"
            },
            {
                "nom":         "Aluminium",
                "description": "Aluminium et alliages",
                "nb_produits": 58,
                "mot_cle":     "aluminium"
            },
            {
                "nom":         "Cement",
                "description": "Ciment et clinker",
                "nb_produits": 6,
                "mot_cle":     "cement"
            },
            {
                "nom":         "Fertilisers",
                "description": "Engrais azotés",
                "nb_produits": 27,
                "mot_cle":     "fertiliser"
            },
            {
                "nom":         "Hydrogen",
                "description": "Hydrogène",
                "nb_produits": 1,
                "mot_cle":     "hydrogen"
            }
        ]
    }
 
 
# ══════════════════════════════════════════════════
# ENDPOINT 5 — Prix carbone actuel
# ══════════════════════════════════════════════════
 
@router.get("/lookup")
def lookup_cn_code(cn_code: str):
    """
    Identifie un produit par son code NC et retourne :
    secteur, description, colonne A/B, routes disponibles, benchmarks.
    Utilisé pour l'auto-remplissage du formulaire profil.
    """
    cn_code = cn_code.strip()
    if not cn_code:
        raise HTTPException(status_code=400, detail="Code NC vide")

    df = charger_benchmarks()

    # Recherche exacte, puis partielle (4 premiers chiffres)
    rows = df[df['cn_code'] == cn_code]
    if rows.empty:
        rows = df[df['cn_code'].str.startswith(cn_code[:4])]
    if rows.empty:
        raise HTTPException(status_code=404, detail=f"Code NC '{cn_code}' introuvable")

    # Catégorie du premier résultat → secteur FR
    categorie  = str(rows.iloc[0]['categorie'] or '').strip()
    cat_lower  = categorie.lower()
    secteur_fr = ""
    cbam_key   = ""
    for k, (fr, ck) in _CAT_TO_SECTEUR.items():
        if k in cat_lower:
            secteur_fr, cbam_key = fr, ck
            break

    colonne = get_colonne_obligatoire(cbam_key) if cbam_key else "A"

    # Routes disponibles pour ce CN code (lignes non-NaN route_a)
    route_col = f"route_{colonne.lower()}"
    routes_disponibles = []
    seen = set()
    for _, row in rows.iterrows():
        r = str(row[route_col]).strip()
        if r and r not in ('None', 'nan') and r not in seen:
            seen.add(r)
            routes_disponibles.append(r)

    # Description du produit
    description = str(rows.iloc[0]['cn_description'] or '').strip()

    # Benchmarks (colonne sélectionnée)
    bmg_col = f"bmg_{colonne.lower()}"
    benchmarks_list = []
    seen_bmg = set()
    for _, row in rows.iterrows():
        r_raw     = str(row[route_col]).strip()
        route_val = r_raw if r_raw not in ('None', 'nan') else None
        bmg_val   = float(row[bmg_col]) if str(row[bmg_col]) not in ('nan', 'None') else None
        key = (route_val, bmg_val)
        if bmg_val is not None and key not in seen_bmg:
            seen_bmg.add(key)
            benchmarks_list.append({"route": route_val, "bmg": bmg_val})

    return {
        "cn_code":            cn_code,
        "description":        description,
        "categorie":          categorie,
        "secteur_fr":         secteur_fr,
        "cbam_key":           cbam_key,
        "colonne":            colonne,
        "colonne_raison":     (
            "Scope 1 uniquement — émissions électricité EXCLUES"
            if colonne == "A" else
            "Scope 1 + Scope 2 — émissions électricité INCLUSES"
        ),
        "routes_disponibles": routes_disponibles,
        "benchmarks":         benchmarks_list,
        "trouve":             True
    }


@router.get("/prix-carbone")
def get_prix_carbone():
    """Retourne le prix carbone EU ETS utilisé"""
    return {
        "prix_euro_par_tonne": PRIX_CARBONE_EU,
        "source":  "EU ETS — estimation 2026",
        "note":    "Mettez à jour PRIX_CARBONE_EU dans cbam_engine.py",
        "url_reference": "https://ember-climate.org/data/carbon-price-viewer/"
    }


# ══════════════════════════════════════════════════
# ENDPOINT 6 — Conformité DVs officiels (Règl. 2025/2621)
# Source unique : DVs as adopted_v20260204.xlsx
# ══════════════════════════════════════════════════

@router.get("/conformite-dv")
def conformite_dv(annee: int = 2026):
    """
    Calcul de conformité CBAM avec les Default Values officiels (Règl. UE 2025/2621).

    Logique :
      I = (Scope1 + Scope2) / production
      DV = colonne F du fichier Excel (markup_annee)
      excédent = max(0, I - DV)
      taxe = excédent × production × 76.50 € × facteur_free_allocation

    Retourne : intensité, DV, excédent, taxe, statut CBAM.
    """
    conn   = get_connection()
    conn.autocommit = True
    cursor = conn.cursor()

    # Profil entreprise
    profil = {}
    try:
        cursor.execute("SELECT * FROM company_profile ORDER BY id LIMIT 1")
        row = cursor.fetchone()
        profil = dict(row) if row else {}
    except Exception:
        pass

    # CO2 par scope (en tonnes)
    scopes = {}
    try:
        cursor.execute("""
            SELECT e.scope, SUM(e.co2_kg) / 1000.0 AS co2_tonnes
            FROM emissions e
            JOIN activities a ON a.id = e.activity_id
            WHERE a.actif = true AND e.actif = true
            GROUP BY e.scope
        """)
        scopes = {row["scope"]: float(row["co2_tonnes"]) for row in cursor.fetchall()}
    except Exception:
        pass

    cursor.close()
    conn.close()

    cn_code    = profil.get("cn_code") or ""
    production = float(profil.get("production_annuelle_tonnes") or 0)

    if not cn_code:
        raise HTTPException(status_code=400, detail="Code NC manquant dans le profil entreprise.")
    if production <= 0:
        raise HTTPException(status_code=400, detail="Production annuelle non renseignée dans le profil.")

    scope1_t = scopes.get(1, 0.0)
    scope2_t = scopes.get(2, 0.0)

    if scope1_t + scope2_t == 0:
        raise HTTPException(status_code=400, detail="Aucune émission enregistrée. Ajoutez des activités d'abord.")

    # Benchmark général (pour comparaison de performance)
    benchmark_val = None
    secteur = profil.get("secteur") or ""
    cbam_key = _CAT_TO_SECTEUR.get(secteur.lower(), (None, None))[1] if secteur else None
    mot_cle_map = {
        "Acier/Fer": "steel", "Aluminium": "aluminium",
        "Ciment": "cement",   "Engrais": "fertiliser", "Hydrogène": "hydrogen",
    }
    mot_cle = mot_cle_map.get(secteur)
    if mot_cle or cn_code:
        colonne = get_colonne_obligatoire(cbam_key) if cbam_key else "A"
        bmgs = rechercher_benchmark(cn_code=cn_code, mot_cle=mot_cle, colonne=colonne)
        if bmgs:
            benchmark_val = bmgs[0].get("bmg_selectionne")

    from routers.cbam_conformite import calculer_conformite_cbam
    result = calculer_conformite_cbam(
        country            = "Morocco",
        cn_code            = cn_code,
        co2_scope1_tonnes  = scope1_t,
        co2_scope2_tonnes  = scope2_t,
        production_tonnes  = production,
        annee              = annee,
        benchmark_tco2_t   = benchmark_val,
    )

    return result
 