# routers/aluminium.py
# Endpoints CBAM spécifiques au secteur Aluminium
# — PFC (perfluorocarburé) : CF₄ et C₂F₆

from fastapi import APIRouter, Query, HTTPException
from database import get_connection
from services.aluminium_pfc import AluminiumPFCCalculator

router = APIRouter(prefix="/aluminium", tags=["Aluminium CBAM"])


@router.get("/pfc/defaults")
def get_pfc_defaults():
    """Retourne toutes les valeurs EU par défaut de la table pfc_default_values (Maroc 2026)."""
    conn = get_connection()
    try:
        calc = AluminiumPFCCalculator(conn)
        defaults = calc._load_defaults()
        return {"country_code": "MA", "year_from": 2026, "defaults": defaults}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/pfc/calculate")
def calculate_pfc(
    production_type: str = Query(
        ...,
        description="Type de production : 'primary' (bauxite) ou 'secondary' (ferraille)",
        pattern="^(primary|secondary)$",
    ),
    production_tonnes: float = Query(
        1000.0,
        gt=0,
        description="Production annuelle en tonnes d'aluminium",
    ),
):
    """
    Calcule les émissions PFC aluminium depuis les valeurs EU par défaut (CBAM IR 2025/2621).

    - **primary** : aluminium primaire depuis bauxite — électrolyse Hall-Héroult, émissions CF₄/C₂F₆ liées aux effets d'anode.
    - **secondary** : aluminium secondaire depuis ferraille — refonte, pas d'effet d'anode → PFC ≈ 0.

    Facteurs GWP utilisés (IPCC AR6 2024) : CF₄ = 7 380, C₂F₆ = 12 400.
    """
    conn = get_connection()
    try:
        calc = AluminiumPFCCalculator(conn)
        result = calc.calculate_simple(production_type, production_tonnes)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()
