# routers/engrais.py
# Endpoints CBAM spécifiques au secteur Engrais (azotés)
# Règl. UE 2025/2621 · Colonne B (Scope 1+2)

from fastapi import APIRouter, Query, HTTPException
from database import get_connection
from services.engrais_cbam import FertilizerCBAMCalculator

router = APIRouter(prefix="/engrais", tags=["Engrais CBAM"])


@router.get("/types")
def get_fertilizer_types():
    """Liste tous les types d'engrais azotés disponibles avec leur teneur N standard."""
    conn = get_connection()
    try:
        calc  = FertilizerCBAMCalculator(conn)
        types = calc._load_fertilizer_types()
        return {
            "types": [
                {
                    "code":                 code,
                    "label":                data["label"],
                    "formula":              data["formula"],
                    "cn_code":              data["cn_code"],
                    "n_pct_std":            data["n_pct_std"],
                    "n_pct_tolerance":      data["n_pct_tolerance"],
                    "n_pct_min":            round(data["n_pct_std"] * (1 - data["n_pct_tolerance"] / 100), 1),
                    "n_pct_max":            round(data["n_pct_std"] * (1 + data["n_pct_tolerance"] / 100), 1),
                    "emission_intensity":   data["emission_intensity"],
                    "benchmark_tco2_t":     data["benchmark_db"],
                }
                for code, data in types.items()
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/calculate")
def calculate_fertilizer_cbam(
    fertilizer_type: str = Query(
        ...,
        description="Code du type d'engrais : AMMONIA | UREA | AN_34 | AN_28 | AS_21 | HNO3_15",
    ),
    production_tonnes: float = Query(
        1000.0,
        gt=0,
        description="Production annuelle en tonnes",
    ),
    n_pct: float | None = Query(
        None,
        ge=0,
        le=100,
        description="Teneur en azote réelle (%) — optionnel, ±10% du standard autorisé",
    ),
    year: int = Query(
        2026,
        ge=2026,
        le=2030,
        description="Année CBAM pour le calcul de la Free Allocation (2026–2030)",
    ),
):
    """
    Calcule les émissions intrinsèques et le coût CBAM pour un engrais azoté.

    **Formule (Colonne B — Scope 1+2) :**
    ```
    intensity_tco2_t = base_emission_intensity × (actual_N% / standard_N%)
    total_tco2       = intensity × production_tonnes
    ```

    **Ajustement N :**
    - Tolérance ±10% du N standard
    - Si actual_n_pct non fourni → utilise la valeur standard

    **Coût CBAM :**
    ```
    chargeable = intensity - benchmark
    obligation = 1 - free_allocation(année)
    coût       = max(0, chargeable) × obligation × production × prix_carbone
    ```
    """
    conn = get_connection()
    try:
        calc     = FertilizerCBAMCalculator(conn)
        embedded = calc.calculate_emissions(fertilizer_type, production_tonnes, n_pct)
        result   = calc.calculate_cbam_cost(embedded, year)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()
