# erp_simulator.py
# Simule une API ERP qui retourne des données mensuelles
# Lance avec : python erp_simulator.py

from fastapi import FastAPI
from datetime import date
import uvicorn       # Sert à lancer le serveur FastAPI.
import random

app = FastAPI(title="ERP Simulé — CarbonIQ")

# ── DONNÉES ERP SIMULÉES ───────────────────────────
# Représente les consommations mensuelles d'une entreprise industrielle
DONNEES_ERP = [
    {
        "mois":         "2024-01",
        "electricite_kwh": 45000,
        "fuel_litres":     1200,
        "gaz_m3":          800,
        "production_tonnes": 520,
        "site":           "Usine Casablanca"
    },
    {
        "mois":         "2024-02",
        "electricite_kwh": 42000,
        "fuel_litres":     1100,
        "gaz_m3":          750,
        "production_tonnes": 490,
        "site":           "Usine Casablanca"
    },
    {
        "mois":         "2024-03",
        "electricite_kwh": 48000,
        "fuel_litres":     1350,
        "gaz_m3":          900,
        "production_tonnes": 560,
        "site":           "Usine Casablanca"
    },
    {
        "mois":         "2024-04",
        "electricite_kwh": 44000,
        "fuel_litres":     1150,
        "gaz_m3":          820,
        "production_tonnes": 510,
        "site":           "Usine Casablanca"
    },
    {
        "mois":         "2024-05",
        "electricite_kwh": 46000,
        "fuel_litres":     1250,
        "gaz_m3":          860,
        "production_tonnes": 535,
        "site":           "Usine Casablanca"
    },
    {
        "mois":         "2024-06",
        "electricite_kwh": 50000,
        "fuel_litres":     1400,
        "gaz_m3":          950,
        "production_tonnes": 580,
        "site":           "Usine Casablanca"
    }
]


@app.get("/")
def home():
    return {"message": "ERP Simulé CarbonIQ", "status": "running"}


@app.get("/erp/consommations")
def get_consommations(mois: str = None):
    """Retourne toutes les consommations ou filtre par mois"""
    if mois:
        data = [d for d in DONNEES_ERP if d["mois"] == mois]
        return {"data": data, "count": len(data)}
    return {"data": DONNEES_ERP, "count": len(DONNEES_ERP)}


@app.get("/erp/dernier-mois")
def get_dernier_mois():
    """Retourne les données du dernier mois disponible"""
    return {"data": DONNEES_ERP[-1]}


@app.get("/erp/sites")
def get_sites():
    """Retourne la liste des sites"""
    sites = list(set(d["site"] for d in DONNEES_ERP))
    return {"sites": sites}


if __name__ == "__main__":
    print("🏢 ERP Simulé démarré sur http://localhost:8001")
    uvicorn.run(app, host="0.0.0.0", port=8001)