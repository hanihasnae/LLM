# routers/company.py
# Profil entreprise — lu par le chat CBAM automatiquement

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from database import get_connection
from dependencies import get_current_user
from cbam_reference_complete import get_colonne_obligatoire, CBAM_REFERENCE

router = APIRouter()

SECTEURS_VALIDES = {
    "Acier/Fer":  "steel",
    "Aluminium":  "aluminium",
    "Ciment":     "cement",
    "Engrais":    "fertiliser",
    "Hydrogène":  "hydrogen",
}

SECTEUR_TO_CBAM_KEY = {
    "Acier/Fer": "Iron & Steel",
    "Aluminium": "Aluminium",
    "Ciment":    "Cement",
    "Engrais":   "Fertilisers",
    "Hydrogène": "Hydrogen",
}


class ProfilInput(BaseModel):
    nom_entreprise:             str           = "Mon Entreprise"
    secteur:                    str
    cn_code:                    Optional[str] = None
    production_annuelle_tonnes: float
    route_production:           Optional[str] = None


@router.get("/company/profile")
def get_profile(current_user: dict = Depends(get_current_user)):
    conn   = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM company_profile WHERE user_id = %s ORDER BY id LIMIT 1",
        (current_user["user_id"],)
    )
    row = cursor.fetchone()
    cursor.close(); conn.close()

    if not row:
        return {"profil": None, "configure": False}

    profil = dict(row)
    profil["mot_cle"] = SECTEURS_VALIDES.get(profil.get("secteur", ""), "")
    return {"profil": profil, "configure": True}


@router.post("/company/profile")
def save_profile(data: ProfilInput, current_user: dict = Depends(get_current_user)):
    if data.secteur not in SECTEURS_VALIDES:
        raise HTTPException(
            status_code=400,
            detail=f"Secteur invalide. Choisir parmi : {list(SECTEURS_VALIDES.keys())}"
        )
    if data.production_annuelle_tonnes <= 0:
        raise HTTPException(status_code=400, detail="Production doit être > 0")

    uid    = current_user["user_id"]
    conn   = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM company_profile WHERE user_id = %s LIMIT 1", (uid,))
    existing = cursor.fetchone()

    if existing:
        cursor.execute("""
            UPDATE company_profile
            SET nom_entreprise             = %s,
                secteur                    = %s,
                cn_code                    = %s,
                production_annuelle_tonnes = %s,
                route_production           = %s,
                updated_at                 = NOW()
            WHERE id = %s
        """, (
            data.nom_entreprise, data.secteur, data.cn_code,
            data.production_annuelle_tonnes, data.route_production,
            existing["id"]
        ))
    else:
        cursor.execute("""
            INSERT INTO company_profile
            (user_id, nom_entreprise, secteur, cn_code, production_annuelle_tonnes, route_production)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            uid, data.nom_entreprise, data.secteur, data.cn_code,
            data.production_annuelle_tonnes, data.route_production
        ))

    conn.commit()
    cursor.close(); conn.close()

    cbam_key = SECTEUR_TO_CBAM_KEY.get(data.secteur, "")
    colonne  = get_colonne_obligatoire(cbam_key) if cbam_key else "A"
    return {
        "message":            "✅ Profil enregistré",
        "secteur":            data.secteur,
        "mot_cle":            SECTEURS_VALIDES[data.secteur],
        "production":         data.production_annuelle_tonnes,
        "route":              data.route_production,
        "colonne_obligatoire": colonne,
        "colonne_raison":     (
            "Scope 1 uniquement — émissions électricité EXCLUES"
            if colonne == "A" else
            "Scope 1 + Scope 2 — émissions électricité INCLUSES"
        )
    }
