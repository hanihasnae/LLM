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
 
    # Total émissions + par scope
    cursor.execute("""
        SELECT SUM(e.co2_kg) as total
        FROM emissions e
        JOIN activities a ON a.id = e.activity_id
        WHERE a.actif = true AND e.actif = true
    """)
    total_co2_kg = float(cursor.fetchone()["total"] or 0)

    cursor.execute("""
        SELECT e.scope, SUM(e.co2_kg) as co2_kg
        FROM emissions e
        JOIN activities a ON a.id = e.activity_id
        WHERE a.actif = true AND e.actif = true
        GROUP BY e.scope
    """)
    scopes = {row["scope"]: float(row["co2_kg"]) for row in cursor.fetchall()}

    # Par source
    cursor.execute("""
        SELECT a.source, SUM(e.co2_kg) as co2_kg
        FROM activities a
        JOIN emissions e ON e.activity_id = a.id
        WHERE a.actif = true AND e.actif = true
        GROUP BY a.source
        ORDER BY co2_kg DESC
    """)
    sources = [dict(r) for r in cursor.fetchall()]

    cursor.close()
    conn.close()

    # Colonne = secteur → automatique selon Règlement UE 2025/2620
    colonne = data.colonne or 'A'
    if data.secteur:
        colonne = get_colonne_obligatoire(data.secteur)

    # Column A = Scope 1 uniquement / Column B = Scope 1+2
    co2_pour_cbam = scopes.get(1, 0) if colonne == 'A' else total_co2_kg

    # Calcul conformité principal
    rapport = calculer_conformite(
        total_co2_kg      = co2_pour_cbam,
        production_tonnes = data.production_tonnes,
        cn_code           = data.cn_code,
        mot_cle           = data.mot_cle,
        secteur           = data.secteur,
        route             = data.route,
        colonne           = colonne,
        prix_carbone      = data.prix_carbone or PRIX_CARBONE_EU
    )

    # Contexte LLM
    contexte_llm = construire_contexte_cbam(
        total_co2_kg      = co2_pour_cbam,
        production_tonnes = data.production_tonnes,
        cn_code           = data.cn_code,
        mot_cle           = data.mot_cle,
        secteur           = data.secteur,
        route             = data.route,
    )
 
    return {
        **rapport,
        "detail_scopes":      scopes,
        "detail_sources":     sources,
        "contexte_llm":       contexte_llm,
        "colonne_utilisee":   colonne,
        "co2_utilise_kg":     round(co2_pour_cbam, 2),
        "total_co2_kg":       round(total_co2_kg, 2),
        "reglementation":     "Règlement UE 2025/2620 — Commission Implementing Regulation"
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
 