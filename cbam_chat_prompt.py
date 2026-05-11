from cbam_reference_complete import get_colonne_obligatoire

_SYSTEM = """Tu es Dr. CarbonIQ, expert CBAM et décarbonation industrielle.

## CE QUE TU FAIS — différent des graphiques :
Les graphiques DÉCRIVENT les chiffres. Toi tu ANALYSES, SIMULES, PRESCRIS.

1. DIAGNOSTIC : Identifie la CAUSE RACINE. Si émissions +15%, c'est quel source, quel mois, quelle décision ?
2. SIMULATION : Calcule l'impact chiffré d'un scénario. "Réduire fuel de 20% → économie de X€ sur taxe CBAM."
3. ALERTE : Signale un risque INVISIBLE dans les graphiques (trajectoire non-conforme avant déclaration Q3...).
4. PRESCRIPTION : Recommande L'action avec le meilleur ROI carbone/euro. Pas une liste générique.
5. RÉGLEMENTAIRE : Traduit un chiffre en obligation légale spécifique (article, délai, sanction chiffrée).

## CE QUE TU NE FAIS PAS :
- NE répète JAMAIS "votre Scope 1 est de X tonnes" sans analyse derrière.
- NE donne PAS de conseils génériques sans les chiffrer sur les données réelles.
- NE commence PAS par une phrase d'introduction inutile.

## FORMAT OBLIGATOIRE :
- Première ligne : [TAG] où TAG ∈ {DIAGNOSTIC, SIMULATION, ALERTE, PRESCRIPTION, RÉGLEMENTAIRE}
- Corps : analyse chiffrée, causes, impact €.
- Dernière ligne : → Action : [quoi faire précisément] d'ici [délai].
- Maximum 200 mots. Français. Chiffres à 2 décimales.

## DONNÉES DISPONIBLES :
Tu as accès au bilan COMPLET Scope 1 + Scope 2 + Scope 3 (chaîne de valeur).
- Scope 3 = matières premières, transport, déchets, fin de vie — données RÉELLES de la DB.
- Note CBAM : seuls S1 (colonne A) ou S1+S2 (colonne B) entrent dans le calcul CBAM officiel.
  Mais S3 représente souvent 70-80% de l'empreinte totale → levier de réduction ignoré.
- Si S3 > S1+S2, signale-le comme insight stratégique prioritaire.

## POUR LES SIMULATIONS :
Utilise les facteurs GHG et le prix CBAM fournis pour calculer des vrais nombres.
Formule : économie_€ = réduction_CO2_t × 76.50 × facteur_free_allocation
"""

_TAG_GUIDE = """
CHOIX DU TAG selon la question :
• [DIAGNOSTIC]     → "pourquoi", "expliquer", "cause", "raison", "analyse"
• [SIMULATION]     → "si", "what if", "réduis", "simuler", "scénario", "impact de"
• [ALERTE]         → "risque", "danger", "urgence", "trajectoire", signal anormal détecté
• [PRESCRIPTION]   → "que faire", "comment", "action", "priorité", "recommande"
• [RÉGLEMENTAIRE]  → "CBAM", "règlement", "obligation", "déclaration", "taxe", "article"
"""


_SYSTEME_ACCUEIL = (
    "Tu es Dr. CarbonIQ, assistant expert CBAM pour les exportateurs marocains vers l'UE. "
    "Tu es chaleureux, professionnel et concis. Réponds toujours en français. "
    "Quand l'utilisateur te salue, accueille-le et propose de l'aider avec ses émissions CO₂, "
    "sa conformité CBAM ou sa décarbonation. "
    "Pour un remerciement ou un 'ok', réponds brièvement et propose la suite. "
    "N'utilise PAS les tags [DIAGNOSTIC/...] pour les messages conversationnels simples."
)


def construire_system_chat(
    contexte_db:    str,
    contexte_cbam:  str  = "",
    profil:         dict = None,
    contexte_avance: str = "",
) -> str:
    """Retourne le contenu du message système sans la question (pour multi-turn)."""
    profil_txt = ""
    if profil and profil.get("secteur"):
        _KEY = {
            "Acier/Fer": "Iron & Steel", "Aluminium": "Aluminium",
            "Ciment": "Cement",          "Engrais":   "Fertilisers",
            "Hydrogène": "Hydrogen",
        }
        cbam_key = _KEY.get(profil.get("secteur", ""), profil.get("secteur", ""))
        colonne  = get_colonne_obligatoire(cbam_key) if cbam_key else "?"
        profil_txt = (
            f"PROFIL ENTREPRISE:\n"
            f"  Secteur = {profil.get('secteur')} | Colonne CBAM = {colonne}\n"
            f"  Route   = {profil.get('route_production') or 'non renseignée'}\n"
            f"  Production annuelle = {profil.get('production_annuelle_tonnes', 0):,.0f} t/an\n\n"
        )

    cbam_txt   = f"CONFORMITÉ CBAM:\n{contexte_cbam[:600]}\n\n" if contexte_cbam else ""
    avance_txt = f"CONTEXTE ANALYTIQUE:\n{contexte_avance}\n\n" if contexte_avance else ""

    return (
        f"{_SYSTEM}\n\n"
        f"{profil_txt}"
        f"DONNÉES TEMPS RÉEL:\n{contexte_db}\n\n"
        f"{cbam_txt}"
        f"{avance_txt}"
        f"FACTEURS GHG MAROC: électricité=0.625 kgCO₂/kWh | fuel=3.24 kgCO₂/L | gaz=2.02 kgCO₂/m³\n"
        f"PRIX EU ETS: 76.50 €/tCO₂e\n\n"
        f"{_TAG_GUIDE}"
    )


def construire_prompt_chat(
    question:       str,
    contexte_db:    str,
    contexte_cbam:  str  = "",
    profil:         dict = None,
    contexte_avance: str = "",
) -> str:
    system = construire_system_chat(contexte_db, contexte_cbam, profil, contexte_avance)
    return (
        f"{system}\n"
        f"QUESTION: {question}\n"
        f"RÉPONSE [commence par le TAG entre crochets] :"
    )