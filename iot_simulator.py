# iot_simulator.py
# Simulateur IoT industriel réaliste — CarbonIQ
#
# Usage :
#   python iot_simulator.py              → flux temps réel
#   python iot_simulator.py --seed 30   → injecte 30 jours d'historique puis démarre le flux

import requests
import random
import time
import sys     # lire les arguments du terminal
from datetime import datetime, date, timedelta

API_URL = "http://localhost:8000"

# ══════════════════════════════════════════════════════════════
#  DÉFINITION DES CAPTEURS INDUSTRIELS
#  Chaque capteur a :
#    base       → consommation horaire de référence (pleine charge)
#    bruit_pct  → bruit gaussien ± X% autour de la base
#    intervalle → secondes entre deux envois (temps réel)
#    profil     → pattern journalier : "shift3x8" | "shift2x8" | "continu" | "bureaux"
#    anomalie   → probabilité d'un pic anormal (0.0–1.0)
# ══════════════════════════════════════════════════════════════
CAPTEURS = [
    # ── Électricité ─────────────────────────────────────────
    {
        "id":          "ELEC-FOUR-01",
        "nom":         "Four de fusion — Ligne 1",
        "type":        "electricity",
        "unite":       "kWh",
        "base":        320,       # kWh/h à pleine charge
        "bruit_pct":   0.08,
        "intervalle":  12,
        "profil":      "shift3x8",
        "anomalie":    0.03,      # 3% de chance de pic (surtension)
    },
    {
        "id":          "ELEC-COMP-01",
        "nom":         "Compresseurs air — Atelier B",
        "type":        "electricity",
        "unite":       "kWh",
        "base":        145,
        "bruit_pct":   0.12,
        "intervalle":  15,
        "profil":      "shift2x8",
        "anomalie":    0.04,
    },
    {
        "id":          "ELEC-UTIL-01",
        "nom":         "Utilités & Éclairage — Site",
        "type":        "electricity",
        "unite":       "kWh",
        "base":        55,
        "bruit_pct":   0.06,
        "intervalle":  20,
        "profil":      "bureaux",
        "anomalie":    0.01,
    },
    # ── Fuel ────────────────────────────────────────────────
    {
        "id":          "FUEL-GEN-01",
        "nom":         "Groupe électrogène — Secours",
        "type":        "fuel",
        "unite":       "litres",
        "base":        18,        # L/h en fonctionnement
        "bruit_pct":   0.15,
        "intervalle":  25,
        "profil":      "continu",
        "anomalie":    0.06,      # démarrage d'urgence simulé
    },
    {
        "id":          "FUEL-CHAUD-01",
        "nom":         "Chaudière fuel — Vapeur process",
        "type":        "fuel",
        "unite":       "litres",
        "base":        42,
        "bruit_pct":   0.10,
        "intervalle":  20,
        "profil":      "shift3x8",
        "anomalie":    0.02,
    },
    # ── Gaz naturel ─────────────────────────────────────────
    {
        "id":          "GAZ-FOUR-01",
        "nom":         "Brûleurs gaz — Four de traitement",
        "type":        "gas",
        "unite":       "m3",
        "base":        28,        # m³/h
        "bruit_pct":   0.09,
        "intervalle":  18,
        "profil":      "shift3x8",
        "anomalie":    0.02,
    },
    {
        "id":          "GAZ-CHAUD-01",
        "nom":         "Chaudière gaz — Chauffage",
        "type":        "gas",
        "unite":       "m3",
        "base":        12,
        "bruit_pct":   0.14,
        "intervalle":  30,
        "profil":      "bureaux",
        "anomalie":    0.01,
    },
]


# ══════════════════════════════════════════════════════════════
#  PATTERNS DE CHARGE HORAIRE (0h → 23h, facteur multiplicatif)
# ══════════════════════════════════════════════════════════════
PROFILS = {
    # 3×8 : forte charge 06h-22h, ralenti la nuit
    "shift3x8": [
        0.30, 0.25, 0.20, 0.20, 0.25, 0.35,  # 00-05
        0.75, 0.90, 0.95, 1.00, 1.00, 0.95,  # 06-11
        0.85, 0.90, 0.95, 1.00, 0.98, 0.95,  # 12-17
        0.90, 0.85, 0.70, 0.55, 0.40, 0.32,  # 18-23
    ],
    # 2×8 : 06h-22h seulement
    "shift2x8": [
        0.10, 0.10, 0.10, 0.10, 0.10, 0.20,
        0.80, 0.95, 1.00, 1.00, 0.95, 0.90,
        0.80, 0.85, 0.90, 0.95, 0.90, 0.85,
        0.70, 0.50, 0.25, 0.15, 0.10, 0.10,
    ],
    # Bureaux : 8h-18h en semaine
    "bureaux": [
        0.05, 0.05, 0.05, 0.05, 0.05, 0.08,
        0.15, 0.35, 0.75, 0.90, 0.95, 0.90,
        0.70, 0.90, 0.95, 0.85, 0.65, 0.40,
        0.20, 0.12, 0.08, 0.06, 0.05, 0.05,
    ],
    # Continu : quasi-constant
    "continu": [
        0.80, 0.80, 0.80, 0.80, 0.80, 0.85,
        0.90, 0.95, 1.00, 1.00, 1.00, 1.00,
        1.00, 1.00, 1.00, 0.98, 0.95, 0.90,
        0.88, 0.85, 0.83, 0.82, 0.81, 0.80,
    ],
}


def facteur_charge(capteur: dict, dt: datetime) -> float:
    """Retourne le facteur de charge (0.0→1.0) selon l'heure et le jour."""
    heure   = dt.hour
    profil  = PROFILS.get(capteur["profil"], PROFILS["continu"])
    facteur = profil[heure]

    # Week-end : -35% sur les profils industriels, -60% pour les bureaux
    if dt.weekday() >= 5:
        facteur *= 0.40 if capteur["profil"] == "bureaux" else 0.65

    # Effet saisonnier léger : chaudières +20% en hiver
    if capteur["type"] in ("gas", "fuel") and dt.month in (11, 12, 1, 2):
        facteur *= 1.20

    return facteur


def mesure_realiste(capteur: dict, dt: datetime) -> float:
    """Génère une mesure réaliste avec bruit gaussien et patterns de charge."""
    charge  = facteur_charge(capteur, dt)
    base    = capteur["base"] * charge

    # Bruit gaussien ± bruit_pct
    bruit   = random.gauss(0, base * capteur["bruit_pct"])
    valeur  = max(base * 0.05, base + bruit)   # jamais en dessous de 5% base

    # Pic anormal (panne, surtension, fuite)
    if random.random() < capteur["anomalie"]:
        valeur *= random.uniform(2.8, 5.0)
        return round(valeur, 2), True

    return round(valeur, 2), False


def envoyer_mesure(capteur: dict, dt: datetime = None, silencieux: bool = False):
    """Envoie une mesure vers l'API FastAPI."""
    if dt is None:
        dt = datetime.now()

    quantite, est_anomalie = mesure_realiste(capteur, dt)

    payload = {
        "source":          capteur["type"],
        "quantity":        quantite,
        "unit":            capteur["unite"],
        "date":            dt.date().isoformat(),
        "methode_saisie":  "iot",
        "source_document": capteur["id"],
    }

    try:
        res = requests.post(f"{API_URL}/activities", json=payload, timeout=5)

        if res.status_code == 200:
            co2 = res.json().get("calcul", {}).get("co2_kg", "?")
            if not silencieux:
                flag = "⚠️  ANOMALIE" if est_anomalie else "✅"
                print(
                    f"{flag} [{dt.strftime('%H:%M:%S')}] "
                    f"{capteur['id']:<20} "
                    f"{quantite:>8.2f} {capteur['unite']:<8} "
                    f"→ {co2} kg CO₂"
                )
        else:
            if not silencieux:
                print(f"❌ [{capteur['id']}] Erreur API {res.status_code}")

    except requests.exceptions.ConnectionError:
        print("❌ API déconnectée — relance : uvicorn main:app --reload")
    except Exception as e:
        print(f"❌ Erreur : {e}")


# ══════════════════════════════════════════════════════════════
#  MODE SEED — Injecte N jours d'historique instantanément
# ══════════════════════════════════════════════════════════════
def seeder_historique(nb_jours: int = 30):
    """Injecte des données historiques simulées pour remplir les graphiques."""
    print("=" * 65)
    print(f"🌱 SEED — Injection de {nb_jours} jours d'historique")
    print(f"   {len(CAPTEURS)} capteurs × ~{nb_jours * 4} mesures/capteur")
    print("=" * 65)

    aujourd_hui = date.today()
    total = 0

    for j in range(nb_jours, 0, -1):
        jour = aujourd_hui - timedelta(days=j)
        # 4 mesures par jour par capteur (0h, 6h, 12h, 18h) avec variation
        for heure in [0, 6, 10, 14, 18, 22]:
            dt = datetime(jour.year, jour.month, jour.day, heure,
                          random.randint(0, 59), random.randint(0, 59))
            for capteur in CAPTEURS:
                envoyer_mesure(capteur, dt=dt, silencieux=True)
                total += 1

        print(f"  📅 {jour.isoformat()} — {len(CAPTEURS) * 6} mesures injectées ({total} total)")

    print(f"\n✅ Seed terminé — {total} mesures injectées sur {nb_jours} jours")
    print("   Le graphique Monitoring est maintenant alimenté.\n")


# ══════════════════════════════════════════════════════════════
#  MODE TEMPS RÉEL
# ══════════════════════════════════════════════════════════════
def lancer_simulateur():
    """Lance tous les capteurs en boucle temps réel."""
    print("=" * 65)
    print("🏭 SIMULATEUR IOT CARBONIQ — MODE TEMPS RÉEL")
    print("=" * 65)
    print(f"📡 {len(CAPTEURS)} capteurs actifs :")
    for c in CAPTEURS:
        print(f"   [{c['id']:<20}] {c['nom']}  (toutes les {c['intervalle']}s)")
    print(f"\n🔗 API : {API_URL}")
    print("   Ctrl+C pour arrêter\n")
    print(f"{'':=<65}")
    print(f"{'Capteur':<22} {'Valeur':>10}  {'CO₂':>10}  Statut")
    print(f"{'':=<65}")

    compteurs = {c["id"]: 0.0 for c in CAPTEURS}

    while True:
        maintenant = time.time()
        for capteur in CAPTEURS:
            if maintenant - compteurs[capteur["id"]] >= capteur["intervalle"]:
                envoyer_mesure(capteur)
                compteurs[capteur["id"]] = maintenant
        time.sleep(1)


# ══════════════════════════════════════════════════════════════
#  POINT D'ENTRÉE
# ══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    args = sys.argv[1:]

    if "--seed" in args:
        try:
            idx = args.index("--seed")
            nb_jours = int(args[idx + 1]) if idx + 1 < len(args) else 30
        except (ValueError, IndexError):
            nb_jours = 30

        seeder_historique(nb_jours)
        print("▶️  Démarrage du flux temps réel...\n")

    try:
        lancer_simulateur()
    except KeyboardInterrupt:
        print("\n\n🛑 Simulateur arrêté.")
