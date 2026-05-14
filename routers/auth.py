# routers/auth.py
# Endpoints d'authentification : register / login / me

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from database import get_connection
from dependencies import create_access_token, get_current_user
from passlib.context import CryptContext

router  = APIRouter(prefix="/auth", tags=["Authentication"])
pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

SECTEURS_VALIDES = ["Acier/Fer", "Aluminium", "Ciment", "Engrais", "Hydrogène"]


# ── Pydantic models ───────────────────────────────────────────

class RegisterInput(BaseModel):
    email:                      str
    password:                   str
    nom_entreprise:             str
    secteur:                    str
    cn_code:                    Optional[str]   = None
    production_annuelle_tonnes: float           = 1000.0
    route_production:           Optional[str]   = None


class LoginInput(BaseModel):
    email:    str
    password: str


# ── Endpoints ─────────────────────────────────────────────────

@router.post("/register", summary="Créer un compte entreprise")
def register(data: RegisterInput):
    if data.secteur not in SECTEURS_VALIDES:
        raise HTTPException(400, f"Secteur invalide. Choisir parmi : {SECTEURS_VALIDES}")
    if len(data.password) < 6:
        raise HTTPException(400, "Le mot de passe doit contenir au moins 6 caractères")

    conn   = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id FROM users WHERE email = %s", (data.email.lower(),))
        if cursor.fetchone():
            raise HTTPException(400, "Cette adresse email est déjà utilisée")

        pw_hash = pwd_ctx.hash(data.password)

        cursor.execute("""
            INSERT INTO users
                (email, password_hash, nom_entreprise, secteur,
                 cn_code, production_annuelle_tonnes, route_production)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            data.email.lower(), pw_hash, data.nom_entreprise, data.secteur,
            data.cn_code, data.production_annuelle_tonnes, data.route_production,
        ))
        user_id = cursor.fetchone()["id"]

        # Crée le profil CBAM pour ce nouvel utilisateur
        cursor.execute("""
            INSERT INTO company_profile
                (user_id, nom_entreprise, secteur, cn_code,
                 production_annuelle_tonnes, route_production)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            user_id, data.nom_entreprise, data.secteur, data.cn_code,
            data.production_annuelle_tonnes, data.route_production,
        ))

        conn.commit()
    except HTTPException:
        conn.rollback(); raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(500, str(e))
    finally:
        cursor.close(); conn.close()

    token = create_access_token(user_id, data.email, data.secteur)
    return {
        "access_token": token,
        "token_type":   "bearer",
        "user": {
            "id":             user_id,
            "email":          data.email,
            "nom_entreprise": data.nom_entreprise,
            "secteur":        data.secteur,
        },
    }


@router.post("/login", summary="Se connecter")
def login(data: LoginInput):
    conn   = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email = %s", (data.email.lower(),))
    user = cursor.fetchone()
    cursor.close(); conn.close()

    if not user or not pwd_ctx.verify(data.password, user["password_hash"]):
        raise HTTPException(401, "Email ou mot de passe incorrect")

    token = create_access_token(user["id"], user["email"], user["secteur"])
    return {
        "access_token": token,
        "token_type":   "bearer",
        "user": {
            "id":             user["id"],
            "email":          user["email"],
            "nom_entreprise": user["nom_entreprise"],
            "secteur":        user["secteur"],
        },
    }


@router.get("/me", summary="Profil de l'utilisateur connecté")
def get_me(current_user: dict = Depends(get_current_user)):
    conn   = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, email, nom_entreprise, secteur, cn_code,
               production_annuelle_tonnes, route_production, created_at
        FROM users WHERE id = %s
    """, (current_user["user_id"],))
    user = cursor.fetchone()
    cursor.close(); conn.close()

    if not user:
        raise HTTPException(404, "Utilisateur introuvable")
    return dict(user)
