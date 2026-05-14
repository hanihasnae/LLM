# main.py
# C'est le fichier qu'on lance pour démarrer toute l'application

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from database import create_tables, insert_default_factors, insert_pfc_defaults, insert_cement_defaults, insert_fertilizer_defaults, insert_hydrogen_defaults
from routers import data , pdf , erp , tracabilite , chat , cbam , company , report, scope3
from routers import aluminium, ciment, engrais, hydrogene
from routers.auth import router as auth_router
from routers.cbam_communication import router as cbam_communication_router
from routers.cbam_communication_template import router as cbam_communication_template_router
from routers.operators_emissions_report import router as operators_emissions_report_router

# Crée l'application FastAPI
app = FastAPI(
    title="Carbon Footprint API 🌿",
    description="Système intelligent de gestion d'empreinte carbone",
    version="1.0.0"
)

# ── CORS ──────────────────────────────────────────────
# Sans ça, le navigateur bloque les requêtes fetch() du frontend
# vers l'API car ils sont sur des origines différentes.
# allow_origins=["*"] = accepte toutes les origines (ok en dev)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],      # en prod : mettre l'URL exacte du frontend
    allow_methods=["*"],      # GET, POST, PUT, DELETE...
    allow_headers=["*"],
)

# Au démarrage, crée les tables et insère les facteurs par défaut
@app.on_event("startup")
def startup():
    print("🚀 Démarrage de l'application...")
    create_tables()
    insert_default_factors()
    insert_cement_defaults()
    insert_pfc_defaults()
    insert_fertilizer_defaults()
    insert_hydrogen_defaults()
    print("✅ Application prête !")

# Page d'accueil de l'API
@app.get("/")
def home():
    return {
        "message": "Bienvenue sur Carbon Footprint API 🌿",
        "status": "running",
        "endpoints": [
            "/activities - voir toutes les activités",
            "/activities - ajouter une activité (POST)",
            "/emission-factors - voir les facteurs",
            "/summary - voir le résumé des émissions"
        ]
    }

# Connecte les routes API
app.include_router(data.router)
app.include_router(pdf.router)
app.include_router(erp.router)
app.include_router(tracabilite.router)
app.include_router(chat.router) 
app.include_router(cbam.router)
app.include_router(company.router)
app.include_router(report.router)
app.include_router(scope3.router)
app.include_router(aluminium.router)
app.include_router(ciment.router)
app.include_router(engrais.router)
app.include_router(hydrogene.router)
app.include_router(auth_router)
app.include_router(cbam_communication_router)
app.include_router(cbam_communication_template_router)
app.include_router(operators_emissions_report_router)

# ── FICHIERS STATIQUES ────────────────────────────────
# Sert tous les fichiers du dossier frontend/ directement.
# Accès : http://localhost:8000/frontend/index.html
# Avantage : même origine → plus besoin de CORS pour le JS
app.mount("/frontend", StaticFiles(directory="frontend"), name="frontend")