# routers/hydrogene.py
# Endpoints CBAM — secteur Hydrogène
# Règl. UE 2025/2621 · Colonne A (Scope 1) · Benchmark 5.089 tCO₂/t H₂

from fastapi import APIRouter, Query, HTTPException
from database import get_connection
from services.hydrogene_cbam import HydrogenCBAMCalculator

router = APIRouter(prefix="/hydrogene", tags=["Hydrogène CBAM"])


@router.get("/methods")
def get_production_methods():
    """Liste les procédés de production H₂ avec leurs intensités et caractéristiques."""
    conn = get_connection()
    try:
        calc    = HydrogenCBAMCalculator(conn)
        methods = calc._load_methods()
        return {
            "methods": [
                {
                    "code":             code,
                    "label":            d["label"],
                    "is_electrolysis":  d["is_electrolysis"],
                    "direct_intensity": d["direct_intensity"],
                    "default_elec_src": d["default_elec_src"],
                    "default_kwh_per_kg": d["default_kwh_per_kg"],
                    "benchmark_tco2_t": d["benchmark"],
                    "cn_code":          d["cn_code"],
                    "notes":            d["notes"],
                }
                for code, d in methods.items()
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/electricity-sources")
def get_electricity_sources():
    """Liste les sources électriques disponibles pour l'électrolyse."""
    conn = get_connection()
    try:
        calc    = HydrogenCBAMCalculator(conn)
        sources = calc._load_elec_sources()
        return {
            "sources": [
                {
                    "code":      code,
                    "label":     d["label"],
                    "intensity_tco2_mwh": d["intensity"],
                    "notes":     d["notes"],
                }
                for code, d in sources.items()
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/electrolysis-types")
def get_electrolysis_types():
    """Liste les types d'électrolyseurs avec leur consommation électrique."""
    conn = get_connection()
    try:
        calc  = HydrogenCBAMCalculator(conn)
        types = calc._load_elec_types()
        return {
            "types": [
                {
                    "code":       code,
                    "label":      d["label"],
                    "kwh_per_kg": d["kwh_per_kg"],
                    "notes":      d["notes"],
                }
                for code, d in types.items()
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/calculate")
def calculate_hydrogen_cbam(
    method: str = Query(
        ...,
        description="Code procédé : SMR_NG | ELEC_GRID | ELEC_RE | BIOMASS_REFORM | ELEC_NUCLEAR",
    ),
    production_tonnes: float = Query(
        5000.0, gt=0,
        description="Production annuelle en tonnes de H₂",
    ),
    year: int = Query(
        2026, ge=2026, le=2030,
        description="Année CBAM (2026–2030)",
    ),
    elec_source: str | None = Query(
        None,
        description="Code source électrique (électrolyse) : GRID_MAROC | RE_CERTIFIED | GAS_CCS | NUCLEAR",
    ),
    elec_type: str | None = Query(
        None,
        description="Code électrolyseur : STANDARD_AEL | PEM | ALKALINE_ADV",
    ),
    custom_kwh_per_kg: float | None = Query(
        None, gt=0,
        description="Consommation électrique personnalisée (kWh/kg H₂) — remplace le standard",
    ),
):
    """
    Calcule les émissions intrinsèques H₂ et le coût CBAM (Colonne A).

    **Procédé thermique :**  intensity = valeur directe de la DB

    **Électrolyse :**
    ```
    intensity (tCO₂/t H₂) = kwh_per_kg × elec_intensity_tco2_mwh
    ```

    **Coût CBAM (Colonne A) :**
    ```
    chargeable = intensity - 5.089 (benchmark)
    obligation = 1 - free_allocation(année)
    coût = max(0, chargeable) × obligation × production × 76.50 €/tCO₂
    ```
    """
    conn = get_connection()
    try:
        calc     = HydrogenCBAMCalculator(conn)
        embedded = calc.calculate_emissions(
            method, production_tonnes, elec_source, elec_type, custom_kwh_per_kg
        )
        result   = calc.calculate_cbam_cost(embedded, year)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()
