# routers/ciment.py
# Endpoints CBAM spécifiques au secteur Ciment
# EN 197-1 · Règl. UE 2025/2621 · Colonne B (Scope 1+2)

from fastapi import APIRouter, Query, HTTPException
from database import get_connection
from services.ciment_cbam import CementEmissionsCalculator

router = APIRouter(prefix="/ciment", tags=["Ciment CBAM"])


@router.get("/types")
def get_cement_types():
    """
    Liste tous les types de ciment EN 197-1 disponibles avec leur ratio clinker.
    """
    conn = get_connection()
    try:
        calc = CementEmissionsCalculator(conn)
        types = calc._load_cement_types()
        return {
            "types": [
                {
                    "code":            code,
                    "label":           data["label"],
                    "cn_code":         data["cn_code"],
                    "clinker_pct":     data["clinker_pct"],
                    "clinker_min":     data["clinker_min"],
                    "clinker_max":     data["clinker_max"],
                    "benchmark_tco2_t": data["benchmark_db"],
                }
                for code, data in types.items()
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/calculate")
def calculate_cement_cbam(
    cement_type: str = Query(
        ...,
        description="Code du type de ciment : CEM_I | CEM_II_A | CEM_II_B | CEM_III_A | CEM_VI | CLINKER",
    ),
    production_tonnes: float = Query(
        1000.0,
        gt=0,
        description="Production annuelle en tonnes de ciment",
    ),
    year: int = Query(
        2026,
        ge=2026,
        le=2030,
        description="Année CBAM pour le calcul de la Free Allocation (2026–2030)",
    ),
):
    """
    Calcule les émissions intrinsèques et le coût CBAM pour un type de ciment donné.

    **Formule CBAM (Colonne B — Scope 1+2) :**
    ```
    Calcination  = (clinker_ratio / 100) × 0.525 tCO₂/t clinker
    Combustible  = 0.285 tCO₂/t ciment  (défaut Maroc 2026)
    Électricité  = 0.080 tCO₂/t ciment  (défaut Maroc 2026)
    TOTAL        = calcination + combustible + électricité
    ```

    **Coût CBAM :**
    ```
    chargeable = TOTAL - benchmark
    obligation_factor = 1 - free_allocation(année)
    coût = max(0, chargeable) × obligation_factor × production × prix_carbone
    ```
    """
    conn = get_connection()
    try:
        # Récupère les émissions Scope 1 et Scope 2 réelles enregistrées
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                COALESCE(SUM(CASE WHEN e.scope = 1 THEN e.co2_kg ELSE 0 END), 0) AS scope1_kg,
                COALESCE(SUM(CASE WHEN e.scope = 2 THEN e.co2_kg ELSE 0 END), 0) AS scope2_kg
            FROM emissions e
            JOIN activities a ON e.activity_id = a.id
            WHERE a.actif = true AND e.actif = true
        """)
        row = cursor.fetchone()
        cursor.close()
        scope1_kg = float(row["scope1_kg"]) if row and row["scope1_kg"] else None
        scope2_kg = float(row["scope2_kg"]) if row and row["scope2_kg"] else None

        calc     = CementEmissionsCalculator(conn)
        embedded = calc.calculate_embedded_emissions_standard(
            cement_type, production_tonnes,
            scope1_co2_kg=scope1_kg,
            scope2_co2_kg=scope2_kg,
        )
        result   = calc.calculate_cbam_cost(embedded, year)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/emission-factors")
def get_cement_emission_factors():
    """Retourne les facteurs d'émission par défaut utilisés pour le calcul."""
    conn = get_connection()
    try:
        calc = CementEmissionsCalculator(conn)
        return {"factors": calc._load_emission_factors()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()
