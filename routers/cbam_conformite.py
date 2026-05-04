# ═══════════════════════════════════════════════════════════════════════════════
# CarbonIQ — Conformité CBAM avec DVs depuis Excel
# Source unique : DVs_as_adopted_v20260204.xlsx
# ═══════════════════════════════════════════════════════════════════════════════

from typing import Optional, Dict
from cbam_dv_loader_lite import get_loader


# Trajectoire Free Allocation (seul paramètre hardcodé - réglementaire)
FREE_ALLOCATION = {
    2026: 0.975,   # 2.5%
    2027: 0.95,    # 5%
    2028: 0.90,    # 10%
    2029: 0.775,   # 22.5%
    2030: 0.515,   # 48.5%
}

PRIX_CARBONE_EU = 76.50  # €/tonne (réglementaire)


def calculer_conformite_cbam(
    country: str,
    cn_code: str,
    intensite_reelle: float,       # tCO2/tonne produit
    production_tonnes: float,       # tonnes produites
    annee: int = 2026,
    deduction_article9: float = 0.0,  # prix carbone Maroc payé
) -> Dict:
    """
    Calcul CONFORMITÉ CBAM avec DVs depuis Excel.
    
    Source : Fichier Excel officiel Règlement UE 2025/2621
    
    Args:
        country: Pays (ex: "Morocco")
        cn_code: Code NC 8 chiffres (ex: "25232900")
        intensite_reelle: Émissions réelles en tCO2/tonne
        production_tonnes: Quantité produite en tonnes
        annee: Année de déclaration (2026, 2027, etc.)
        deduction_article9: Montant déduction Maroc en €
    
    Returns:
        Dict complet pour rapport Page 4
    """
    
    loader = get_loader()
    
    # 1. Lookup depuis Excel
    dv = loader.lookup(country, cn_code)
    
    if dv is None:
        return {
            "status": "error",
            "cn_code": cn_code,
            "country": country,
            "message": f"Code NC {cn_code} non trouvé dans {country}",
            "action": "Vérifier le code ou utiliser benchmark Règlement 2025/2620"
        }
    
    # 2. Récupérer mark-up selon année
    mark_up_key = f"markup_{annee}"
    dv_markup = dv.get(mark_up_key, dv["markup_2026"])
    dv_total = dv["dv_total"]
    
    # 3. Free Allocation factor
    facteur = FREE_ALLOCATION.get(annee, FREE_ALLOCATION[2026])
    
    # 4. Calculs
    excedent = max(0, intensite_reelle - dv_total) * production_tonnes
    taxe_brute = excedent * PRIX_CARBONE_EU
    taxe_ajustee = taxe_brute * facteur
    taxe_nette = max(0, taxe_ajustee - deduction_article9)
    
    economie = (dv_markup - intensite_reelle) / dv_markup * 100 if dv_markup > 0 else 0
    statut = "CONFORME" if intensite_reelle <= dv_total else "NON CONFORME"
    
    return {
        "status": "success",
        # ─── Données produit Excel ───────────────────────────────
        "cn_code": cn_code,
        "description": dv["description"],
        "secteur": dv["sector"],
        "route": dv["route"],
        "source_fichier": dv["source_file"],
        "source_onglet": dv["source_sheet"],
        
        # ─── DVs officiel ────────────────────────────────────────
        "dv_direct_scope1": dv["dv_direct"],
        "dv_indirect_scope2": dv["dv_indirect"],
        "dv_total": dv["dv_total"],
        "dv_markup": dv_markup,
        
        # ─── Données réelles ────────────────────────────────────
        "intensite_reelle": intensite_reelle,
        "production_tonnes": production_tonnes,
        
        # ─── Résultats ──────────────────────────────────────────
        "statut": statut,
        "economie_pourcentage": round(economie, 1),
        "excedent_tco2": round(excedent, 2),
        "taxe_brute": round(taxe_brute, 2),
        "facteur_free_allocation": facteur,
        "reduction_percentage": round((1 - facteur) * 100, 1),
        "taxe_ajustee": round(taxe_ajustee, 2),
        "deduction_article9": deduction_article9,
        "taxe_nette_due": round(taxe_nette, 2),
    }


def generer_page4_text(calcul: Dict) -> str:
    """
    Génère le texte de Page 4 prêt pour le rapport.
    """
    if calcul["status"] == "error":
        return f"⚠️  {calcul['message']}"
    
    c = calcul
    lines = [
        "═" * 70,
        "PAGE 4 — CONFORMITÉ CBAM (Règlement UE 2025/2621)",
        "═" * 70,
        "",
        f"Produit      : {c['description']}",
        f"Code NC      : {c['cn_code']}",
        f"Secteur      : {c['secteur']}",
        f"Route        : {c['route']}",
        "",
        f"Source DVs   : {c['source_fichier']} — Onglet '{c['source_onglet']}'",
        "",
        "── VALEURS PAR DÉFAUT (depuis Excel) ────────────────────────",
        f"  Scope 1 (direct)    : {c['dv_direct_scope1']:.4f} tCO₂/t",
        f"  Scope 2 (indirect)  : {c['dv_indirect_scope2']:.4f} tCO₂/t",
        f"  Total benchmark     : {c['dv_total']:.4f} tCO₂/t",
        f"  Mark-up {2026}          : {c['dv_markup']:.4f} tCO₂/t",
        "",
        "── DONNÉES RÉELLES ──────────────────────────────────────────",
        f"  Intensité réelle    : {c['intensite_reelle']:.4f} tCO₂/t",
        f"  Production          : {c['production_tonnes']:.0f} tonnes",
        "",
        "── CONFORMITÉ ───────────────────────────────────────────────",
        f"  Status              : {c['statut']} {'✅' if c['statut'] == 'CONFORME' else '❌'}",
        f"  Économie carbone    : {c['economie_pourcentage']}% sous mark-up",
        "",
        "── CALCUL TAXE CBAM ────────────────────────────────────────",
        f"  Excédent carbone    : {c['excedent_tco2']:.2f} tCO₂",
        f"  Prix EU ETS         : {PRIX_CARBONE_EU}€/t",
        f"  Taxe brute          : {c['taxe_brute']:.2f}€",
        f"  Free Allocation ×{c['facteur_free_allocation']:.3f} (-{c['reduction_percentage']:.1f}%) : {c['taxe_ajustee']:.2f}€",
        f"  Déduction Article 9 : -{c['deduction_article9']:.2f}€",
        "",
        f"  ═ TAXE NETTE DUE : {c['taxe_nette_due']:.2f}€ ═",
        "═" * 70,
    ]
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("TEST 1 : Ciment conforme\n")
    result = calculer_conformite_cbam(
        country="Morocco",
        cn_code="25232900",
        intensite_reelle=0.78,
        production_tonnes=12000
    )
    print(generer_page4_text(result))
    
    print("\n\nTEST 2 : Ammoniac dépassant\n")
    result = calculer_conformite_cbam(
        country="Morocco",
        cn_code="28141000",
        intensite_reelle=2.50,
        production_tonnes=8000,
        deduction_article9=5000
    )
    print(generer_page4_text(result))
    
    print("\n\nTEST 3 : Aluminium Route (L)\n")
    result = calculer_conformite_cbam(
        country="Morocco",
        cn_code="7601",
        intensite_reelle=0.30,
        production_tonnes=5000
    )
    print(generer_page4_text(result))