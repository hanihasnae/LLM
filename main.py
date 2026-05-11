# main.py
# C'est le fichier qu'on lance pour démarrer toute l'application

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from database import create_tables, insert_default_factors
from routers import data , pdf , erp , tracabilite , chat , cbam , company , report, scope3


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

# ── FICHIERS STATIQUES ────────────────────────────────
# Sert tous les fichiers du dossier frontend/ directement.
# Accès : http://localhost:8000/frontend/index.html
# Avantage : même origine → plus besoin de CORS pour le JS
app.mount("/frontend", StaticFiles(directory="frontend"), name="frontend")