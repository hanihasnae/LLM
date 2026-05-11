# cbam_reference_complete.py
# Référence officielle CBAM — Règlement UE 2025/2620
# Source : CBAM_Benchmarks_20260206.xlsx
# ══════════════════════════════════════════════════════════════════
# RÈGLE FONDAMENTALE :
#
# Émissions INDIRECTES = émissions liées à l'électricité consommée
#
# Fer & Acier   → émissions indirectes EXCLUES → utiliser Column A
# Aluminium     → émissions indirectes EXCLUES → utiliser Column A
# Hydrogène     → émissions indirectes EXCLUES → utiliser Column A
# Ciment        → émissions indirectes INCLUSES → utiliser Column B
# Engrais       → émissions indirectes INCLUSES → utiliser Column B
# ══════════════════════════════════════════════════════════════════
 
CBAM_REFERENCE = {
 
    # ══════════════════════════════════════════════════════════════
    # SECTEUR 1 — FER & ACIER
    # Émissions indirectes : EXCLUES → Column A obligatoire
    # Codes NC : 2601, 7201–7229
    # ══════════════════════════════════════════════════════════════
    "Iron & Steel": {
        "fr":                    "Fer et Acier",
        "codes_nc":              "2601, 7201–7229",
        "nb_produits":           570,  # avec sous-routes
        "emissions_indirectes":  "EXCLUES",
        "colonne_obligatoire":   "A",
        "raison_colonne": (
            "Les émissions liées à l'électricité (Scope 2) sont EXCLUES "
            "du calcul CBAM pour l'acier. On utilise Column A qui reflète "
            "uniquement les émissions directes du procédé de fabrication."
        ),
 
        "routes": {
 
            # ── Route (C) ─────────────────────────────────────────
            "(C)": {
                "nom":         "Four Électrique à Arc (EAF)",
                "procede":     "Production d'acier à partir de ferraille recyclée",
                "bmg_a_range": "0.000 – 0.453 tCO₂/t",
                "bmg_b_range": "1.288 – 1.779 tCO₂/t",
                "nb_produits": 289,
                "choisir_si": [
                    "Votre usine utilise un four électrique à arc (EAF)",
                    "Votre matière première principale est de la ferraille recyclée",
                    "Vous produisez de l'acier courant (lingots, demi-produits)"
                ],
                "exemples_produits": [
                    "72061000 — Lingots acier non allié",
                    "72071114 — Demi-produits acier < 0.25% carbone",
                    "72072015 — Demi-produits acier ≥ 0.25% carbone"
                ],
                "alerte": (
                    "BMG_A très bas (≈0.15) car EAF avec ferraille = "
                    "procédé peu émetteur en CO₂ direct"
                )
            },
 
            # ── Route (D) ─────────────────────────────────────────
            "(D)": {
                "nom":         "EAF — Recyclage direct intégré",
                "procede":     "Four électrique avec recyclage en boucle fermée",
                "bmg_a_range": "0.027 – 0.330 tCO₂/t",
                "bmg_b_range": "0.424 – 0.740 tCO₂/t",
                "nb_produits": 20,
                "choisir_si": [
                    "EAF avec système de recyclage intégré en boucle fermée",
                    "Procédé avec récupération maximale des chutes internes"
                ],
                "note": "Sous-route de (C) — benchmark encore plus bas"
            },
 
            # ── Route (E) ─────────────────────────────────────────
            "(E)": {
                "nom":         "EAF — Procédé alternatif",
                "procede":     "Four électrique avec procédé alternatif optimisé",
                "bmg_a_range": "0.027 – 0.330 tCO₂/t",
                "bmg_b_range": "0.027 – 0.331 tCO₂/t",
                "nb_produits": 20,
                "choisir_si": [
                    "EAF avec technologie alternative certifiée",
                    "BMG_A ≈ BMG_B → procédé très optimisé"
                ],
                "note": (
                    "Route E : BMG_A ≈ BMG_B — la route de production "
                    "n'impacte presque pas les émissions"
                )
            },
 
            # ── Route (F) ─────────────────────────────────────────
            "(F)": {
                "nom":         "Aciers Alliés Spéciaux — EAF",
                "procede":     "Production d'aciers alliés via four électrique",
                "bmg_a_range": "0.223 – 0.453 tCO₂/t",
                "bmg_b_range": "1.577 – 1.807 tCO₂/t",
                "nb_produits": 11,
                "choisir_si": [
                    "Vous produisez des aciers alliés spéciaux via EAF",
                    "Aciers à outils, aciers haute vitesse, aciers inox"
                ],
                "exemples_produits": [
                    "72241010 — Lingots acier à outils",
                    "72241090 — Aciers alliés primaires",
                    "72249002 — Demi-produits acier à outils"
                ]
            },
 
            # ── Route (F)(1) ──────────────────────────────────────
            "(F)(1)": {
                "nom":         "Aciers Alliés — Haut Fourneau",
                "procede":     "Production d'aciers alliés via voie intégrée BF-BOF",
                "bmg_a_range": "0.000 – 0.453 tCO₂/t",
                "bmg_b_range": "1.460 – 1.807 tCO₂/t",
                "nb_produits": 70,
                "choisir_si": [
                    "Aciers alliés produits via haut fourneau + convertisseur",
                    "Voie intégrée avec minerai de fer vierge"
                ]
            },
 
            # ── Route (G) ─────────────────────────────────────────
            "(G)": {
                "nom":         "Aciers Alliés Spéciaux — Route G",
                "procede":     "Aciers alliés avec procédé G (technologie spécifique)",
                "bmg_a_range": "0.100 – 0.330 tCO₂/t",
                "bmg_b_range": "0.752 – 0.982 tCO₂/t",
                "nb_produits": 11,
                "choisir_si": [
                    "Procédé G certifié par votre auditeur CBAM",
                    "Aciers spéciaux avec technologie G documentée"
                ]
            },
 
            # ── Route (G)(1) ──────────────────────────────────────
            "(G)(1)": {
                "nom":         "Aciers Alliés — Route G + Haut Fourneau",
                "procede":     "Combinaison procédé G avec voie intégrée",
                "bmg_a_range": "0.100 – 0.330 tCO₂/t",
                "bmg_b_range": "0.752 – 0.982 tCO₂/t",
                "nb_produits": 11,
                "choisir_si": [
                    "Procédé G combiné avec haut fourneau"
                ]
            },
 
            # ── Route (H) ─────────────────────────────────────────
            "(H)": {
                "nom":         "Aciers Alliés Spéciaux — Route H",
                "procede":     "Aciers alliés avec procédé H",
                "bmg_a_range": "0.100 – 0.330 tCO₂/t",
                "bmg_b_range": "0.410 – 0.640 tCO₂/t",
                "nb_produits": 11,
                "choisir_si": [
                    "Procédé H certifié par votre auditeur CBAM"
                ]
            },
 
            # ── Route (H)(1) ──────────────────────────────────────
            "(H)(1)": {
                "nom":         "Aciers Alliés — Route H + Haut Fourneau",
                "procede":     "Combinaison procédé H avec voie intégrée",
                "bmg_a_range": "0.100 – 0.330 tCO₂/t",
                "bmg_b_range": "0.410 – 0.640 tCO₂/t",
                "nb_produits": 11,
                "choisir_si": [
                    "Procédé H combiné avec haut fourneau"
                ]
            },
 
            # ── Route (J) ─────────────────────────────────────────
            "(J)": {
                "nom":         "Aciers Alliés Spéciaux — Route J",
                "procede":     "Aciers alliés avec procédé J",
                "bmg_a_range": "0.128 – 0.358 tCO₂/t",
                "bmg_b_range": "0.950 – 1.180 tCO₂/t",
                "nb_produits": 11,
                "choisir_si": [
                    "Procédé J certifié par votre auditeur CBAM"
                ]
            },
 
            # ── Route (J)(1) ──────────────────────────────────────
            "(J)(1)": {
                "nom":         "Aciers Alliés — Route J + Haut Fourneau",
                "procede":     "Combinaison procédé J avec voie intégrée",
                "bmg_a_range": "0.128 – 0.358 tCO₂/t",
                "bmg_b_range": "0.950 – 1.180 tCO₂/t",
                "nb_produits": 11,
                "choisir_si": [
                    "Procédé J combiné avec haut fourneau"
                ]
            },
 
            # ── Route (1) ─────────────────────────────────────────
            "(1)": {
                "nom":         "Ferro-Alliages — Haut Fourneau Standard",
                "procede":     "Production de ferro-alliages via haut fourneau",
                "bmg_a_range": "0.038 – 2.390 tCO₂/t",
                "bmg_b_range": "1.142 – 2.390 tCO₂/t",
                "nb_produits": 104,
                "choisir_si": [
                    "Vous produisez des ferro-alliages",
                    "Ferro-manganèse, ferro-chrome, ferro-nickel",
                    "Haut fourneau standard comme procédé principal"
                ],
                "exemples_produits": [
                    "72021120 — Ferro-manganèse > 2% carbone",
                    "72024110 — Ferro-chrome > 4% carbone",
                    "72026000 — Ferro-nickel (BMG=2.390 — le plus élevé !)"
                ]
            },
 
            # ── Route (2) ─────────────────────────────────────────
            "(2)": {
                "nom":         "Ferro-Alliages — Procédé Alternatif",
                "procede":     "Production de ferro-alliages par procédé alternatif",
                "bmg_a_range": "1.106 – 2.295 tCO₂/t",
                "bmg_b_range": "1.106 – 2.295 tCO₂/t",
                "nb_produits": 9,
                "choisir_si": [
                    "Ferro-alliages via procédé alternatif au haut fourneau",
                    "BMG_A = BMG_B — pas de distinction recyclé/vierge"
                ],
                "note": "BMG_A = BMG_B pour cette route"
            }
        }
    },
 
    # ══════════════════════════════════════════════════════════════
    # SECTEUR 2 — ALUMINIUM
    # Émissions indirectes : EXCLUES → Column A obligatoire
    # Codes NC : 7601–7616
    # ══════════════════════════════════════════════════════════════
    "Aluminium": {
        "fr":                   "Aluminium",
        "codes_nc":             "7601–7616",
        "nb_produits":          58,
        "emissions_indirectes": "EXCLUES",
        "colonne_obligatoire":  "A",
        "raison_colonne": (
            "Les émissions liées à l'électricité sont EXCLUES pour "
            "l'aluminium. Column A = émissions directes uniquement. "
            "ATTENTION : différence x25 entre aluminium recyclé et primaire !"
        ),
 
        "routes": {
 
            # ── Route (K) ─────────────────────────────────────────
            "(K)": {
                "nom":         "Électrolyse Hall-Héroult",
                "procede":     "Production d'aluminium par électrolyse de l'alumine",
                "bmg_a_range": "0.046 – 1.423 tCO₂/t",
                "bmg_b_range": "1.423 – 1.599 tCO₂/t",
                "nb_produits": 58,
                "choisir_si": [
                    "Aluminium brut non allié (76011010, 76011090)",
                    "Alliages d'aluminium bruts (76012030–76012080)",
                    "Procédé principal : électrolyse Hall-Héroult"
                ],
                "exemples_produits": [
                    "76011010 — Aluminium brut non allié (slabs) BMG_A=1.423",
                    "76041010 — Barres aluminium non allié     BMG_A=0.056",
                    "76031000 — Poudres aluminium               BMG_A=0.046"
                ],
                "alerte": (
                    "⚠️ CRITIQUE : BMG_A varie de 0.046 à 1.423 selon le produit. "
                    "Aluminium brut = 1.423 / Produits transformés = 0.046–0.060. "
                    "Vérifiez votre code CN exact !"
                )
            },
 
            # ── Route (L) ─────────────────────────────────────────
            "(L)": {
                "nom":         "Aluminium — Énergie Renouvelable",
                "procede":     "Production aluminium primaire avec électricité renouvelable",
                "bmg_a_range": "0.091 tCO₂/t",
                "bmg_b_range": "0.091 tCO₂/t",
                "nb_produits": 5,
                "choisir_si": [
                    "Votre usine utilise exclusivement de l'énergie renouvelable",
                    "Certifié énergie verte par organisme accrédité",
                    "Alumineries hydroélectriques ou solaires"
                ],
                "exemples_produits": [
                    "76011010 — Aluminium brut non allié",
                    "76011090 — Aluminium non allié autre",
                    "76012030 — Alliages aluminium bruts (slabs)",
                    "76012040 — Alliages aluminium bruts (billettes)",
                    "76012080 — Alliages aluminium bruts (autres)"
                ],
                "avantage": (
                    "✅ ÉNORME AVANTAGE : BMG = 0.091 vs 1.423 route K standard. "
                    "Réduction de 94% du benchmark !"
                )
            }
        }
    },
 
    # ══════════════════════════════════════════════════════════════
    # SECTEUR 3 — CIMENT
    # Émissions indirectes : INCLUSES → Column B obligatoire
    # Codes NC : 2507, 2523
    # ══════════════════════════════════════════════════════════════
    "Cement": {
        "fr":                   "Ciment",
        "codes_nc":             "2507, 2523",
        "nb_produits":          6,
        "emissions_indirectes": "INCLUSES",
        "colonne_obligatoire":  "B",
        "raison_colonne": (
            "Pour le ciment, les émissions électricité sont INCLUSES "
            "car le four de cuisson consomme beaucoup d'énergie. "
            "Column B inclut donc Scope 1 + Scope 2 dans le benchmark."
        ),
 
        "routes": {
 
            # ── Route (A) ─────────────────────────────────────────
            "(A)": {
                "nom":         "Procédé Standard Clinker Portland",
                "procede":     "Cuisson calcaire à 1450°C — voie sèche ou humide",
                "bmg_b":       0.666,
                "nb_produits": 2,
                "choisir_si": [
                    "Vous produisez du clinker pur (25231000)",
                    "Vous produisez d'autres ciments non Portland (25239000)",
                    "Four rotatif standard — voie sèche"
                ],
                "exemples_produits": [
                    "25231000 — Clinker ciment       BMG_B=0.666",
                    "25239000 — Autres ciments       BMG_B=0.666"
                ],
                "note": (
                    "60% des émissions ciment = décarbonatation calcaire "
                    "(CaCO₃ → CaO + CO₂) — inévitable quelque soit le procédé"
                )
            },
 
            # ── Route (B) ─────────────────────────────────────────
            "(B)": {
                "nom":         "Procédé avec Combustibles Alternatifs",
                "procede":     "Four avec mix combustibles fossiles + alternatifs",
                "bmg_b_range": "0.847 – 0.859 tCO₂/t",
                "nb_produits": 2,
                "choisir_si": [
                    "Clinker avec combustibles alternatifs (pneus, déchets...)",
                    "Ciment Portland blanc (25232100)",
                    "Procédé avec additifs supplémentaires"
                ],
                "exemples_produits": [
                    "25231000 — Clinker (route B)     BMG_B=0.859",
                    "25239000 — Autres ciments (B)   BMG_B=0.847"
                ],
                "note": (
                    "BMG_B plus élevé car inclut émissions "
                    "des combustibles alternatifs utilisés"
                )
            },
 
            # ── Route (1) ─────────────────────────────────────────
            "(1)": {
                "nom":         "Ciment Alumineux Standard",
                "procede":     "Fusion de bauxite et calcaire — ciment fondu",
                "bmg_b":       0.717,
                "nb_produits": 1,
                "choisir_si": [
                    "Vous produisez du ciment alumineux (ciment fondu)",
                    "Résistance à la chaleur ou aux sulfates requise",
                    "Applications réfractaires"
                ],
                "exemples_produits": [
                    "25233000 — Ciment alumineux   BMG_B=0.717"
                ]
            },
 
            # ── Route (2) ─────────────────────────────────────────
            "(2)": {
                "nom":         "Ciment Alumineux Alternatif",
                "procede":     "Ciment alumineux avec procédé alternatif",
                "bmg_b":       0.686,
                "nb_produits": 1,
                "choisir_si": [
                    "Ciment alumineux via procédé alternatif optimisé",
                    "BMG légèrement inférieur à route (1)"
                ],
                "exemples_produits": [
                    "25233000 — Ciment alumineux (alt.)  BMG_B=0.686"
                ]
            }
        }
    },
 
    # ══════════════════════════════════════════════════════════════
    # SECTEUR 4 — ENGRAIS
    # Émissions indirectes : INCLUSES → Column B obligatoire
    # Codes NC : 2808, 2834, 3102–3105
    # ══════════════════════════════════════════════════════════════
    "Fertilisers": {
        "fr":                   "Engrais",
        "codes_nc":             "2808, 2834, 3102–3105",
        "nb_produits":          27,
        "emissions_indirectes": "INCLUSES",
        "colonne_obligatoire":  "B",
        "raison_colonne": (
            "Pour les engrais, les émissions électricité sont INCLUSES "
            "car la synthèse Haber-Bosch consomme énormément d'énergie. "
            "Column B = Scope 1 + Scope 2 dans le benchmark."
        ),
 
        "routes": {
 
            # ── Route (1) ─────────────────────────────────────────
            "(1)": {
                "nom":         "Haber-Bosch — Gaz Naturel (SMR)",
                "procede":     "Synthèse ammoniac via Steam Methane Reforming",
                "bmg_b_range": "0.701 – 0.701 tCO₂/t",
                "nb_produits": 1,
                "choisir_si": [
                    "Production ammoniac/engrais via gaz naturel",
                    "Reformage vapeur méthane (SMR) comme source H₂",
                    "Procédé Haber-Bosch conventionnel"
                ],
                "exemples_produits": [
                    "31025000 — Sodium nitrate   BMG_B=0.701"
                ],
                "note": (
                    "Route la plus courante dans les usines d'engrais marocaines"
                )
            },
 
            # ── Route (2) ─────────────────────────────────────────
            "(2)": {
                "nom":         "Haber-Bosch — Source Alternative H₂",
                "procede":     "Synthèse ammoniac via H₂ renouvelable ou récupération CO₂",
                "bmg_b_range": "0.685 – 0.685 tCO₂/t",
                "nb_produits": 1,
                "choisir_si": [
                    "Hydrogène vert (électrolyse eau + énergie renouvelable)",
                    "Récupération et utilisation du CO₂ (CCU)",
                    "Procédé Haber-Bosch décarboné"
                ],
                "exemples_produits": [
                    "31025000 — Sodium nitrate (alt.)  BMG_B=0.685"
                ],
                "avantage": (
                    "✅ Benchmark légèrement inférieur à route (1) "
                    "car source H₂ moins émettrice"
                )
            }
        }
    },
 
    # ══════════════════════════════════════════════════════════════
    # SECTEUR 5 — HYDROGÈNE
    # Émissions indirectes : EXCLUES → Column A obligatoire
    # Codes NC : 2804
    # ══════════════════════════════════════════════════════════════
    "Hydrogen": {
        "fr":                   "Hydrogène",
        "codes_nc":             "2804",
        "nb_produits":          1,
        "emissions_indirectes": "EXCLUES",
        "colonne_obligatoire":  "A",
        "raison_colonne": (
            "Pour l'hydrogène, seules les émissions directes comptent. "
            "Column A = Scope 1 uniquement. "
            "Benchmark unique : 5.089 tCO₂/t pour tout type de production."
        ),
 
        "routes": {
            "UNIQUE": {
                "nom":         "Benchmark Unique — Tous Procédés",
                "procede":     "Steam Methane Reforming (SMR) ou électrolyse",
                "bmg_a":       5.089,
                "bmg_b":       5.089,
                "nb_produits": 1,
                "choisir_si": [
                    "Un seul produit : Hydrogène pur (28041000)",
                    "Même benchmark quel que soit le procédé"
                ],
                "exemples_produits": [
                    "28041000 — Hydrogène  BMG=5.089"
                ],
                "note": (
                    "BMG très élevé (5.089) car reflète la production "
                    "SMR actuelle dominante. "
                    "L'hydrogène vert n'a pas encore de route séparée "
                    "dans ce règlement."
                )
            }
        }
    }
}
 
 
# ══════════════════════════════════════════════════════════════
# FONCTIONS UTILITAIRES
# ══════════════════════════════════════════════════════════════
 
def get_colonne_obligatoire(secteur: str) -> str:
    """Retourne A ou B selon le secteur."""
    for key, data in CBAM_REFERENCE.items():
        if secteur.lower() in key.lower() or key.lower() in secteur.lower():
            return data["colonne_obligatoire"]
    return "A"  # défaut sécurisé
 
 
def get_raison_colonne(secteur: str) -> str:
    """Retourne l'explication du choix de colonne."""
    for key, data in CBAM_REFERENCE.items():
        if secteur.lower() in key.lower() or key.lower() in secteur.lower():
            return data["raison_colonne"]
    return ""
 
 
def get_routes_secteur(secteur: str) -> dict:
    """Retourne toutes les routes d'un secteur."""
    for key, data in CBAM_REFERENCE.items():
        if secteur.lower() in key.lower() or key.lower() in secteur.lower():
            return data["routes"]
    return {}
 
 
def get_guide_choix_route(secteur: str, cn_code: str = None) -> dict:
    """
    Guide l'utilisateur dans le choix de sa route.
    Retourne les questions à poser et les routes correspondantes.
    """
    colonne = get_colonne_obligatoire(secteur)
    routes  = get_routes_secteur(secteur)
 
    return {
        "secteur":           secteur,
        "colonne_a_utiliser": colonne,
        "raison":            get_raison_colonne(secteur),
        "emissions_indirectes": CBAM_REFERENCE.get(secteur, {}).get(
            "emissions_indirectes", "INCONNUE"
        ),
        "routes_disponibles": routes,
        "message_utilisateur": (
            f"Pour votre secteur '{secteur}', vous devez utiliser "
            f"la Colonne {colonne}. "
            + ("Les émissions électricité sont EXCLUES de votre calcul CBAM."
               if colonne == "A"
               else "Les émissions électricité sont INCLUSES dans votre calcul CBAM.")
        )
    }
 