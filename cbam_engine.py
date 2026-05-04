# cbam_engine.py
# Moteur de conformité CBAM — Règlement UE 2025/2620
# Basé sur les benchmarks officiels
 
import pandas as pd     # pour lire le fichier excel 
import os    # gere les fichiers ,chemins, systemes
from functools import lru_cache    # Mémoriser le résultat d’une fonction
from typing import Optional
from cbam_reference_complete import (
    get_colonne_obligatoire,
    get_guide_choix_route,
    CBAM_REFERENCE
)
 
# Chemin du fichier benchmarks
BENCHMARKS_PATH = os.path.join(
    os.path.dirname(__file__), 
    "data", 
    "benchmarks_cbam.xlsx"
)
 
# Prix carbone EU ETS (€/tonne CO₂) — à mettre à jour régulièrement
PRIX_CARBONE_EU = 76.50  # Prix approximatif 2026
 
 
@lru_cache(maxsize=1)
def charger_benchmarks() -> pd.DataFrame:
    """
    Charge et nettoie le fichier Excel des benchmarks CBAM.
    lru_cache = chargé une seule fois en mémoire.
    """
    df = pd.read_excel(BENCHMARKS_PATH, sheet_name='Benchmarks')
    df.columns = ['cn_code', 'cn_description', 'bmg_a', 'route_a', 'bmg_b', 'route_b']
 
    # Ajoute la catégorie à chaque ligne
    categorie_actuelle = None
    categories = []
    for _, row in df.iterrows():
        cn = str(row['cn_code']) if pd.notna(row['cn_code']) else ''
        if cn and not cn.replace(' ', '').replace('.', '').isdigit() and cn != 'nan':
            categorie_actuelle = cn
        categories.append(categorie_actuelle)
    df['categorie'] = categories

    # Forward-fill CN code et description pour les lignes de continuation
    # (ex: row 9 pour 25239000 route B a cn_code=NaN dans l'Excel)
    last_numeric_cn  = None
    last_desc        = None
    for i, row in df.iterrows():
        cn = row['cn_code']
        if pd.notna(cn) and str(cn).replace(' ', '').replace('.', '').isdigit():
            last_numeric_cn = cn
            last_desc       = row['cn_description']
        elif pd.isna(cn) and last_numeric_cn is not None:
            df.at[i, 'cn_code']        = last_numeric_cn
            if pd.isna(row['cn_description']):
                df.at[i, 'cn_description'] = last_desc

    # Garde seulement les lignes avec CN code numérique
    df = df[df['cn_code'].apply(
        lambda x: str(x).replace(' ', '').isdigit() if pd.notna(x) else False
    )].copy()
 
    # Nettoyage
    df['cn_code']         = df['cn_code'].astype(str).str.strip()
    df['cn_description']  = df['cn_description'].fillna('').str.strip()
    df['bmg_a']           = pd.to_numeric(df['bmg_a'], errors='coerce')
    df['bmg_b']           = pd.to_numeric(df['bmg_b'], errors='coerce')
 
    return df.reset_index(drop=True)
 
 
def rechercher_benchmark(
    cn_code: Optional[str] = None,
    mot_cle: Optional[str] = None,
    colonne: str = 'A'
) -> list[dict]:
    """
    Recherche un benchmark par code CN ou mot-clé produit.
 
    Args:
        cn_code  : Code douanier ex: "72011011"
        mot_cle  : Nom produit ex: "steel", "aluminium", "cement"
        colonne  : 'A' ou 'B' selon la route de production
 
    Returns:
        Liste de produits correspondants avec leur benchmark
    """
    df  = charger_benchmarks()
    bmg = f'bmg_{colonne.lower()}'
 
    if cn_code:
        # Recherche exacte par code CN
        cn_code  = str(cn_code).strip()
        resultats = df[df['cn_code'] == cn_code]
 
        if resultats.empty:
            # Recherche partielle (début du code)
            resultats = df[df['cn_code'].str.startswith(cn_code[:4])]
 
    elif mot_cle:
        # Recherche par mot-clé dans la description
        resultats = df[
            df['cn_description'].str.contains(mot_cle, case=False, na=False) |
            df['categorie'].str.contains(mot_cle, case=False, na=False)
        ]
    else:
        return []
 
    # Formate les résultats
    return [
        {
            "cn_code":     row['cn_code'],
            "description": row['cn_description'],
            "categorie":   row['categorie'],
            "bmg_a":       float(row['bmg_a']) if pd.notna(row['bmg_a']) else None,
            "bmg_b":       float(row['bmg_b']) if pd.notna(row['bmg_b']) else None,
            "route_a":     str(row['route_a']) if pd.notna(row['route_a']) else None,
            "route_b":     str(row['route_b']) if pd.notna(row['route_b']) else None,
            "bmg_selectionne": float(row[bmg]) if pd.notna(row[bmg]) else None,
            "unite":       "tCO2e/tonne produit"
        }
        for _, row in resultats.iterrows()
    ]
 
 
def calculer_conformite(
    total_co2_kg:        float,
    production_tonnes:   float,
    cn_code:             Optional[str] = None,
    mot_cle:             Optional[str] = None,
    secteur:             Optional[str] = None,
    route:               Optional[str] = None,
    colonne:             str = 'A',
    prix_carbone:        float = PRIX_CARBONE_EU
) -> dict:
    """
    Calcule la conformité CBAM complète.

    Règle officielle :
    - Column A = Scope 1 uniquement (Steel, Aluminium, Hydrogen)
    - Column B = Scope 1 + Scope 2  (Cement, Fertilisers)
    La colonne est déterminée par le secteur, PAS par l'utilisateur.

    Args:
        secteur  : Nom du secteur CBAM → détermine automatiquement la colonne A/B
        route    : Route de production ex: "(A)", "(K)", "(1)" → sélectionne la ligne Excel
        colonne  : Ignoré si secteur fourni (dérivé automatiquement)
    """

    if production_tonnes <= 0:
        return {"erreur": "Production doit être > 0", "valide": False}

    # Colonne déterminée par le secteur (règle officielle UE 2025/2620)
    if secteur:
        colonne = get_colonne_obligatoire(secteur)

    total_co2_tonnes = total_co2_kg / 1000
    intensite        = total_co2_tonnes / production_tonnes

    benchmarks = rechercher_benchmark(cn_code=cn_code, mot_cle=mot_cle, colonne=colonne)

    if not benchmarks:
        return {
            "valide":           True,
            "intensite":        round(intensite, 4),
            "total_co2_tonnes": round(total_co2_tonnes, 4),
            "production":       production_tonnes,
            "benchmark":        None,
            "statut":           "BENCHMARK_INCONNU",
            "message":          "Aucun benchmark trouvé pour ce produit",
            "recommandation":   "Vérifiez le code NC ou le nom du produit"
        }

    # Sélectionne la ligne selon la route de production
    # route_a et route_b contiennent la même valeur pour une ligne donnée
    if route:
        bm = next(
            (b for b in benchmarks
             if str(b.get('route_a') or '').strip() == route
             or str(b.get('route_b') or '').strip() == route),
            benchmarks[0]
        )
    else:
        bm = benchmarks[0]

    bmg_valeur = bm.get("bmg_selectionne")
 
    if bmg_valeur is None:
        return {
            "valide":           True,
            "intensite":        round(intensite, 4),
            "total_co2_tonnes": round(total_co2_tonnes, 4),
            "benchmark":        bm,
            "statut":           "BENCHMARK_NUL",
            "message":          "Benchmark = 0 pour ce produit (exonéré)"
        }
 
    # Conformité
    conforme  = intensite <= bmg_valeur
    excedent  = max(0, intensite - bmg_valeur) * production_tonnes
    taxe_euro = excedent * prix_carbone
 
    # Calcul de la marge (bmg_valeur=0 = produit exonéré → conformité parfaite)
    if bmg_valeur == 0:
        return {
            "valide":           True,
            "intensite":        round(intensite, 4),
            "total_co2_tonnes": round(total_co2_tonnes, 4),
            "benchmark":        bm,
            "statut":           "BENCHMARK_NUL",
            "message":          "Benchmark = 0 pour ce produit (exonéré de CBAM)"
        }
    marge_pct = ((bmg_valeur - intensite) / bmg_valeur) * 100
 
    # Niveau de risque
    if conforme:
        if marge_pct > 20:
            risque = "FAIBLE"
        elif marge_pct > 5:
            risque = "MOYEN"
        else:
            risque = "ÉLEVÉ"
    else:
        if abs(marge_pct) > 20:
            risque = "CRITIQUE"
        else:
            risque = "ÉLEVÉ"
 
    return {
        "valide":             True,
        "statut":             "CONFORME" if conforme else "NON_CONFORME",
        "conforme":           conforme,
        "risque":             risque,
 
        # Calculs
        "intensite_reelle":   round(intensite, 4),
        "benchmark":          round(bmg_valeur, 4),
        "marge_pct":          round(marge_pct, 2),
        "excedent_tco2":      round(excedent, 4),
 
        # Financier
        "exposition_financiere": {
            "taxe_estimee_euro":  round(taxe_euro, 2),
            "prix_carbone_euro":  prix_carbone,
            "devise":             "EUR"
        },
 
        # Produit
        "produit": {
            "cn_code":     bm["cn_code"],
            "description": bm["description"],
            "categorie":   bm["categorie"],
            "colonne":     colonne,
            "unite":       "tCO2e/tonne produit"
        },
 
        # Données brutes
        "donnees": {
            "total_co2_kg":      round(total_co2_kg, 2),
            "total_co2_tonnes":  round(total_co2_tonnes, 4),
            "production_tonnes": production_tonnes
        },
 
        # Recommandations
        "recommandation": _generer_recommandation(
            conforme, risque, intensite, bmg_valeur, taxe_euro, marge_pct
        )
    }
 
 
def _generer_recommandation(
    conforme:    bool,
    risque:      str,
    intensite:   float,
    benchmark:   float,
    taxe:        float,
    marge_pct:   float
) -> str:
    """Génère une recommandation textuelle selon le statut."""
 
    if conforme:
        if risque == "FAIBLE":
            return (
                f"✅ Excellente conformité. Votre intensité ({intensite:.4f}) est "
                f"{marge_pct:.1f}% sous le benchmark ({benchmark:.4f}). "
                f"Continuez vos efforts de décarbonation."
            )
        elif risque == "MOYEN":
            return (
                f"⚠️ Conforme mais surveillez votre intensité ({intensite:.4f}). "
                f"Marge de {marge_pct:.1f}% avant le seuil CBAM ({benchmark:.4f}). "
                f"Envisagez des optimisations préventives."
            )
        else:
            return (
                f"🔶 Conforme mais à risque ! Intensité ({intensite:.4f}) très proche "
                f"du benchmark ({benchmark:.4f}). Marge de seulement {marge_pct:.1f}%. "
                f"Action corrective recommandée."
            )
    else:
        return (
            f"❌ Non conforme ! Intensité ({intensite:.4f}) dépasse le benchmark "
            f"({benchmark:.4f}) de {abs(marge_pct):.1f}%. "
            f"Exposition financière estimée : {taxe:.0f} € de taxe CBAM. "
            f"Réduction urgente des émissions requise."
        )
 
 
def construire_contexte_cbam(
    total_co2_kg:      float,
    production_tonnes: float,
    cn_code:           Optional[str] = None,
    mot_cle:           Optional[str] = None,
    secteur:           Optional[str] = None,
    route:             Optional[str] = None,
    colonne:           str = 'A'
) -> str:
    """
    Construit le contexte CBAM pour le LLM (RAG).
    secteur  → détermine colonne A/B automatiquement
    route    → sélectionne la ligne benchmark exacte
    """
    rapport = calculer_conformite(
        total_co2_kg      = total_co2_kg,
        production_tonnes = production_tonnes,
        cn_code           = cn_code,
        mot_cle           = mot_cle,
        secteur           = secteur,
        route             = route,
        colonne           = colonne
    )
 
    if not rapport.get("valide"):
        return "Données insuffisantes pour l'analyse CBAM."
 
    if rapport["statut"] in ("BENCHMARK_INCONNU", "BENCHMARK_NUL"):
        msg = rapport.get("message", "")
        rec = rapport.get("recommandation", "")
        return f"Analyse CBAM : {msg}. {rec}".strip()

    conforme = rapport["conforme"]
    prod     = rapport.get("produit", {})
    fin      = rapport.get("exposition_financiere", {})
    donnees  = rapport.get("donnees", {})
 
    contexte = f"""
ANALYSE CONFORMITÉ CBAM (Règlement UE 2025/2620) :
 
PRODUIT :
- Code NC        : {prod.get('cn_code', 'N/A')}
- Description    : {prod.get('description', 'N/A')}
- Secteur        : {prod.get('categorie', 'N/A')}
 
CALCUL D'INTENSITÉ :
- Émissions totales  : {donnees.get('total_co2_tonnes', 0):.4f} tCO₂e
- Production         : {donnees.get('production_tonnes', 0)} tonnes
- Intensité réelle   : {rapport.get('intensite_reelle', 0):.4f} tCO₂e/tonne
- Benchmark CBAM     : {rapport.get('benchmark', 0):.4f} tCO₂e/tonne
 
STATUT : {'✅ CONFORME' if conforme else '❌ NON CONFORME'}
- Marge              : {rapport.get('marge_pct', 0):.2f}%
- Niveau de risque   : {rapport.get('risque', 'N/A')}
- Excédent CO₂       : {rapport.get('excedent_tco2', 0):.4f} tCO₂e
 
EXPOSITION FINANCIÈRE :
- Taxe CBAM estimée  : {fin.get('taxe_estimee_euro', 0):.2f} €
- Prix carbone EU ETS : {fin.get('prix_carbone_euro', 0)} €/tonne
 
RECOMMANDATION : {rapport.get('recommandation', '')}
"""
    return contexte
 
 
def get_tous_benchmarks_secteur(secteur: str) -> list[dict]:
    """Retourne tous les benchmarks d'un secteur."""
    df = charger_benchmarks()
    resultats = df[df['categorie'].str.contains(secteur, case=False, na=False)]
    return [
        {
            "cn_code":     row['cn_code'],
            "description": row['cn_description'][:80] + '...'
                           if len(str(row['cn_description'])) > 80
                           else row['cn_description'],
            "bmg_a":       float(row['bmg_a']) if pd.notna(row['bmg_a']) else None,
            "bmg_b":       float(row['bmg_b']) if pd.notna(row['bmg_b']) else None,
        }
        for _, row in resultats.iterrows()
    ]
 