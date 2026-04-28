# iot_simulator.py
# Simule des capteurs IoT qui envoient des données en temps réel
# Lance ce fichier dans un terminal séparé

import requests  # Elle sert à envoyer des requêtes HTTP vers ton API 
import random   # Il sert à générer des valeurs aléatoires
import time
from datetime import datetime, date

API_URL = "http://localhost:8000"

# ── CONFIGURATION DES CAPTEURS ─────────────────────
# Chaque capteur a un type, une plage de valeurs réaliste
CAPTEURS = [
    {
        "id":          "CAPTEUR-ELEC-01",
        "nom":         "Compteur électricité — Atelier A",
        "type":        "electricity",
        "unite":       "kWh",
        "min":         50,    # consommation minimale par envoi
        "max":         200,   # consommation maximale par envoi
        "intervalle":  10     # envoie toutes les 10 secondes
    },
    {
        "id":          "CAPTEUR-ELEC-02",
        "nom":         "Compteur électricité — Bureaux",
        "type":        "electricity",
        "unite":       "kWh",
        "min":         20,
        "max":         80,
        "intervalle":  15
    },
    {
        "id":          "CAPTEUR-FUEL-01",
        "nom":         "Débitmètre fuel — Groupe électrogène",
        "type":        "fuel",
        "unite":       "litres",
        "min":         10,
        "max":         50,
        "intervalle":  30
    },
    {
        "id":          "CAPTEUR-GAZ-01",
        "nom":         "Compteur gaz — Chaudière",
        "type":        "gas",
        "unite":       "m3",
        "min":         5,
        "max":         25,
        "intervalle":  20
    }
]


def envoyer_mesure(capteur: dict):
    """Envoie une mesure d'un capteur vers l'API FastAPI"""

    # Génère une valeur réaliste avec légère variation aléatoire
    quantite = round(random.uniform(capteur["min"], capteur["max"]), 2)

    # Ajoute une anomalie aléatoire (5% de chance)
    if random.random() < 0.05:
        quantite = quantite * random.uniform(2.5, 4.0)  # pic anormal
        print(f"⚠️  ANOMALIE détectée sur {capteur['id']} : {quantite} {capteur['unite']}")

    # Crée un dictionnaire appelé payload
    payload = {
        "source":   capteur["type"],
        "quantity": quantite,
        "unit":     capteur["unite"],
        "date":     date.today().isoformat()
    }

    try:
        res = requests.post(
            f"{API_URL}/activities",
            json=payload,
            timeout=5
        )

        if res.status_code == 200:
            data = res.json()
            co2  = data.get("calcul", {}).get("co2_kg", "?")
            print(
                f"✅ [{datetime.now().strftime('%H:%M:%S')}] "
                f"{capteur['id']} → "
                f"{quantite} {capteur['unite']} → "
                f"{co2} kg CO₂"
            )
        else:
            print(f"❌ Erreur API : {res.status_code}")

    except requests.exceptions.ConnectionError:
        print("❌ API déconnectée — relance uvicorn main:app --reload")
    except Exception as e:
        print(f"❌ Erreur : {e}")


def lancer_simulateur():
    """Lance tous les capteurs en boucle"""

    print("=" * 60)
    print("🏭 SIMULATEUR IOT CARBONIQ")
    print("=" * 60)
    print(f"📡 {len(CAPTEURS)} capteurs actifs")
    print(f"🔗 API : {API_URL}")
    print("=" * 60)
    print("Appuie sur Ctrl+C pour arrêter\n")

    # Compteurs pour chaque capteur
    compteurs = {c["id"]: 0 for c in CAPTEURS}

    while True:
        maintenant = time.time()

        for capteur in CAPTEURS:
            # Vérifie si c'est le moment d'envoyer pour ce capteur
            if maintenant - compteurs[capteur["id"]] >= capteur["intervalle"]:
                envoyer_mesure(capteur)
                compteurs[capteur["id"]] = maintenant

        time.sleep(1)  # vérifie chaque seconde


if __name__ == "__main__":
    try:
        lancer_simulateur()
    except KeyboardInterrupt:
        print("\n\n🛑 Simulateur arrêté.")