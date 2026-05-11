# ═══════════════════════════════════════════════════════════════════════════════
# CarbonIQ — routers/cbam_conformite.py
# Calcul Conformité CBAM — Logique officielle Règlement UE 2025/2621
#
# ⚠️  Ce fichier n'est PAS un router FastAPI.
#     Il est importé par report.py via :
#     from routers.cbam_conformite import calculer_conformite_cbam
#
# Source DVs : DVs as adopted_v20260204.xlsx — colonne F (markup_2026)
# ═══════════════════════════════════════════════════════════════════════════════

from typing import Optional, Dict
from cbam_dv_loader_lite import get_loader


# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTES RÉGLEMENTAIRES
# ─────────────────────────────────────────────────────────────────────────────

PRIX_CARBONE_EU: float = 76.50  # €/tCO₂ — EU ETS (hardcodé, à externaliser si besoin)

# Facteurs Free Allocation (part de la taxe CBAM effectivement due)
# = proportion des quotas GRATUITS supprimés chaque année
# Source : Article 10, Règlement UE 2023/956
# Exemple 2026 : 2.5% des quotas gratuits supprimés → facteur = 0.025
FREE_ALLOCATION: Dict[int, float] = {
    2026: 0.025,   #  2.5% supprimés
    2027: 0.050,   #  5.0% supprimés
    2028: 0.100,   # 10.0% supprimés
    2029: 0.225,   # 22.5% supprimés
    2030: 0.485,   # 48.5% supprimés
    2034: 1.000,   # 100%  supprimés (phase out complet)
}


# ─────────────────────────────────────────────────────────────────────────────
# FONCTION PRINCIPALE
# ─────────────────────────────────────────────────────────────────────────────

def calculer_conformite_cbam(
    country: str,
    cn_code: str,
    co2_scope1_tonnes: float,       # tCO₂ Scope 1 de la période
    co2_scope2_tonnes: float,       # tCO₂ Scope 2 de la période
    production_tonnes: float,        # tonnes produites sur la même période
    annee: int = 2026,
    benchmark_tco2_t: Optional[float] = None,  # benchmark général (cbam_engine) — optionnel
) -> Dict:
    """
    Calcul officiel de conformité CBAM.

    Logique :
      1. Intensité  I = (Scope1 + Scope2) / production
      2. DV         = markup_2026 depuis colonne F du fichier Excel (Règl. 2025/2621)
      3. Excédent   = max(0, I - DV)
      4. Taxe       = excédent × production × prix_carbone × facteur_free_allocation
      5. Statut     = "No CBAM liability" si I ≤ DV, sinon "CBAM payable"
      6. Benchmark  = usage analytique uniquement (performance, pas taxe)

    Args:
        country            : Pays d'origine (ex: "Morocco")
        cn_code            : Code NC 8 chiffres (ex: "25232900")
        co2_scope1_tonnes  : Émissions directes en tCO₂
        co2_scope2_tonnes  : Émissions indirectes en tCO₂
        production_tonnes  : Production en tonnes
        annee              : Année de déclaration CBAM
        benchmark_tco2_t   : Benchmark général (optionnel, analyse performance)

    Returns:
        Dict complet prêt pour rapport Page 5 (Conformité)
    """

    # ── Garde-fous ────────────────────────────────────────────────────────────
    if production_tonnes <= 0:
        return {
            "status": "error",
            "message": "production_tonnes doit être > 0",
        }

    # ── 1. Calcul intensité carbone ───────────────────────────────────────────
    co2_total_tonnes = co2_scope1_tonnes + co2_scope2_tonnes
    intensite = co2_total_tonnes / production_tonnes   # tCO₂ / tonne produit

    # ── 2. Lookup DV depuis Excel (colonne F = markup_2026) ───────────────────
    loader = get_loader()
    dv_row = loader.lookup(country, cn_code)

    if dv_row is None:
        return {
            "status": "error",
            "cn_code": cn_code,
            "country": country,
            "message": f"Code NC '{cn_code}' non trouvé dans l'onglet '{country}'",
            "action": "Vérifier le code NC ou utiliser benchmark Règlement 2025/2620",
        }

    # Colonne F = markup_2026 (DV officiel avec mark-up pour 2026)
    # Pour les autres années, utiliser markup_2027, markup_2028 si disponibles
    markup_key = f"markup_{annee}"
    dv = dv_row.get(markup_key) or dv_row.get("markup_2026")

    # ── 3. Calcul excédent ────────────────────────────────────────────────────
    excedent_tco2_par_tonne = max(0.0, intensite - dv)
    excedent_total_tco2 = excedent_tco2_par_tonne * production_tonnes

    # ── 4. Calcul taxe CBAM ───────────────────────────────────────────────────
    facteur = FREE_ALLOCATION.get(annee, FREE_ALLOCATION[2026])
    taxe_estimee = excedent_total_tco2 * PRIX_CARBONE_EU * facteur

    # ── 5. Statut de conformité ───────────────────────────────────────────────
    cbam_liability = intensite > dv
    statut = "CBAM payable" if cbam_liability else "No CBAM liability"

    # ── 6. Analyse benchmark (performance uniquement) ─────────────────────────
    benchmark_analyse = None
    if benchmark_tco2_t is not None:
        benchmark_analyse = {
            "valeur_tco2_t": benchmark_tco2_t,
            "performant": intensite <= benchmark_tco2_t,
            "statut_performance": (
                "Performant ✅ (I ≤ benchmark)"
                if intensite <= benchmark_tco2_t
                else "Non performant ⚠️ (I > benchmark)"
            ),
            "ecart_tco2_t": round(intensite - benchmark_tco2_t, 4),
        }

    # ── Résultat final ────────────────────────────────────────────────────────
    return {
        "status": "success",

        # Identification produit
        "cn_code": cn_code,
        "description": dv_row.get("description", ""),
        "secteur": dv_row.get("sector", ""),
        "route": dv_row.get("route", ""),
        "country": country,
        "annee": annee,
        "source_dv_fichier": dv_row.get("source_file", ""),
        "source_dv_onglet": dv_row.get("source_sheet", ""),
        "source_dv_colonne": "F (markup_2026)" if annee == 2026 else f"markup_{annee}",
        "reglementation": "Règlement (UE) 2025/2621",

        # ── Inputs émissions ──────────────────────────────────────
        "co2_scope1_tonnes": round(co2_scope1_tonnes, 4),
        "co2_scope2_tonnes": round(co2_scope2_tonnes, 4),
        "co2_total_tonnes": round(co2_total_tonnes, 4),
        "production_tonnes": production_tonnes,

        # ── Intensité carbone ─────────────────────────────────────
        "intensite_tco2_par_tonne": round(intensite, 4),

        # ── Default Value (DV) ────────────────────────────────────
        "dv_tco2_par_tonne": round(dv, 4),
        "dv_scope1_raw": dv_row.get("dv_direct", None),
        "dv_scope2_raw": dv_row.get("dv_indirect", None),
        "dv_sans_markup": dv_row.get("dv_total", None),

        # ── Excédent ──────────────────────────────────────────────
        "excedent_tco2_par_tonne": round(excedent_tco2_par_tonne, 4),
        "excedent_total_tco2": round(excedent_total_tco2, 4),

        # ── Taxe CBAM ─────────────────────────────────────────────
        "prix_carbone_eu": PRIX_CARBONE_EU,
        "facteur_free_allocation": facteur,
        "facteur_free_allocation_pct": round(facteur * 100, 1),
        "taxe_estimee_eur": round(taxe_estimee, 2),

        # ── Statut conformité ─────────────────────────────────────
        "cbam_liability": cbam_liability,
        "statut": statut,

        # ── Analyse benchmark (optionnel) ─────────────────────────
        "benchmark_analyse": benchmark_analyse,
    }


# ─────────────────────────────────────────────────────────────────────────────
# AFFICHAGE RAPPORT — Page 5 Conformité
# ─────────────────────────────────────────────────────────────────────────────

def generer_page5_text(calcul: Dict) -> str:
    """
    Génère le bloc texte formaté pour la Page 5 (Conformité) du rapport.
    """
    if calcul["status"] == "error":
        return f"⚠️  ERREUR : {calcul['message']}\n→ Action : {calcul.get('action', '')}"

    c = calcul
    statut_icon = "✅" if not c["cbam_liability"] else "❌"

    lines = [
        "═" * 70,
        "PAGE 5 — CONFORMITÉ CBAM",
        f"Source DVs : {c['reglementation']}",
        f"Fichier    : {c['source_dv_fichier']} — Onglet '{c['source_dv_onglet']}'",
        f"Colonne    : {c['source_dv_colonne']}",
        "═" * 70,
        "",
        f"Produit    : {c['description']}",
        f"Code NC    : {c['cn_code']}",
        f"Secteur    : {c['secteur']}",
        f"Route      : {c['route']}",
        f"Année      : {c['annee']}",
        "",
        "── 1. CALCUL INTENSITÉ ─────────────────────────────────────────",
        f"  CO₂ Scope 1         : {c['co2_scope1_tonnes']:.4f} tCO₂",
        f"  CO₂ Scope 2         : {c['co2_scope2_tonnes']:.4f} tCO₂",
        f"  CO₂ Total           : {c['co2_total_tonnes']:.4f} tCO₂",
        f"  Production          : {c['production_tonnes']:.2f} t",
        f"  I = CO₂ / Prod.     : {c['intensite_tco2_par_tonne']:.4f} tCO₂/t",
        "",
        "── 2. DEFAULT VALUE (DV) — Colonne F Excel ─────────────────────",
        f"  DV sans mark-up     : {c['dv_sans_markup']:.4f} tCO₂/t",
        f"  DV avec mark-up     : {c['dv_tco2_par_tonne']:.4f} tCO₂/t  ← utilisé",
        "",
        "── 3. EXCÉDENT ─────────────────────────────────────────────────",
        f"  max(0, I - DV)      : max(0, {c['intensite_tco2_par_tonne']:.4f} - {c['dv_tco2_par_tonne']:.4f})",
        f"  Excédent / tonne    : {c['excedent_tco2_par_tonne']:.4f} tCO₂/t",
        f"  Excédent total      : {c['excedent_total_tco2']:.4f} tCO₂",
        "",
        "── 4. TAXE CBAM ────────────────────────────────────────────────",
        f"  Formule             : excédent × production × prix × facteur",
        f"  = {c['excedent_total_tco2']:.4f} × {c['prix_carbone_eu']} × {c['facteur_free_allocation']}",
        f"  Facteur Free Alloc. : {c['facteur_free_allocation']} ({c['facteur_free_allocation_pct']}% quotas supprimés)",
        f"  ┌─────────────────────────────────────",
        f"  │ TAXE ESTIMÉE : {c['taxe_estimee_eur']:.2f} €",
        f"  └─────────────────────────────────────",
        "",
        "── 5. STATUT ───────────────────────────────────────────────────",
        f"  {statut_icon} {c['statut']}",
        f"  (I = {c['intensite_tco2_par_tonne']:.4f} {'≤' if not c['cbam_liability'] else '>'} DV = {c['dv_tco2_par_tonne']:.4f} tCO₂/t)",
    ]

    # Analyse benchmark si disponible
    if c.get("benchmark_analyse"):
        b = c["benchmark_analyse"]
        lines += [
            "",
            "── 6. BENCHMARK (analyse performance) ──────────────────────────",
            f"  Note : le benchmark n'entre PAS dans le calcul de la taxe.",
            f"  Benchmark         : {b['valeur_tco2_t']:.4f} tCO₂/t",
            f"  Écart             : {b['ecart_tco2_t']:+.4f} tCO₂/t",
            f"  Performance       : {b['statut_performance']}",
        ]

    lines.append("═" * 70)
    return "\n".join(lines)


# Alias rétro-compatible (report.py utilise peut-être generer_page4_text)
generer_page4_text = generer_page5_text


# ─────────────────────────────────────────────────────────────────────────────
# TESTS
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":

    print("TEST 1 — Ciment : I ≤ DV → No CBAM liability\n")
    r = calculer_conformite_cbam(
        country="Morocco",
        cn_code="25232900",
        co2_scope1_tonnes=8400,
        co2_scope2_tonnes=1200,
        production_tonnes=12000,
        annee=2026,
        benchmark_tco2_t=0.95,
    )
    print(generer_page5_text(r))

    print("\n\nTEST 2 — Ammoniac : I > DV → CBAM payable\n")
    r = calculer_conformite_cbam(
        country="Morocco",
        cn_code="28141000",
        co2_scope1_tonnes=18000,
        co2_scope2_tonnes=2000,
        production_tonnes=8000,
        annee=2026,
        benchmark_tco2_t=2.20,
    )
    print(generer_page5_text(r))

    print("\n\nTEST 3 — Aluminium Route (L) : très bas\n")
    r = calculer_conformite_cbam(
        country="Morocco",
        cn_code="7601",
        co2_scope1_tonnes=1500,
        co2_scope2_tonnes=0,
        production_tonnes=5000,
        annee=2026,
        benchmark_tco2_t=0.36,
    )
    print(generer_page5_text(r))

    print("\n\nTEST 4 — Année 2029 (facteur 0.225)\n")
    r = calculer_conformite_cbam(
        country="Morocco",
        cn_code="28141000",
        co2_scope1_tonnes=18000,
        co2_scope2_tonnes=2000,
        production_tonnes=8000,
        annee=2029,
    )
    print(generer_page5_text(r))