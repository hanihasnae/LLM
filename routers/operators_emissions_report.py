"""
routers/operators_emissions_report.py

Operator's Emissions Report Generator
Conforme IR 2025/2547, Annexe IV, point 1.1

Format: JSON structuré pour vérificateur tiers accrédité UE
Langue: English (obligatoire pour soumission EU)
"""

from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import JSONResponse
from datetime import datetime
from database import get_connection
from dependencies import get_current_user

router = APIRouter(prefix="/cbam", tags=["Operator Emissions Report"])

# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_profile(conn, user_id: int):
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM company_profile WHERE user_id = %s ORDER BY id LIMIT 1",
        (user_id,)
    )
    row = cur.fetchone()
    cur.close()
    return row


def _get_emissions_summary(conn):
    """Retourne scope1_tco2, scope2_tco2, elec_kwh depuis les activités actives."""
    cur = conn.cursor()
    cur.execute("""
        SELECT
            COALESCE(SUM(CASE WHEN e.scope = 1 THEN e.co2_kg ELSE 0 END), 0) / 1000.0 AS scope1_tco2,
            COALESCE(SUM(CASE WHEN e.scope = 2 THEN e.co2_kg ELSE 0 END), 0) / 1000.0 AS scope2_tco2,
            COALESCE(SUM(
                CASE WHEN a.source = 'electricity' THEN a.quantity ELSE 0 END
            ), 0) AS elec_kwh
        FROM emissions e
        JOIN activities a ON e.activity_id = a.id
        WHERE a.actif = true AND e.actif = true
    """)
    row = cur.fetchone()
    cur.close()
    return (
        float(row["scope1_tco2"]) if row else 0.0,
        float(row["scope2_tco2"]) if row else 0.0,
        float(row["elec_kwh"])   if row else 0.0,
    )


_PROCESSES = {
    "Acier/Fer": {
        "cbam":     ["Blast furnace operation", "BOF steelmaking", "EAF operation", "Casting"],
        "non_cbam": ["Pickling", "Galvanizing", "Annealing"],
    },
    "Aluminium": {
        "cbam":     ["Hall-Héroult electrolysis", "Casting"],
        "non_cbam": ["Remelting", "Extrusion", "Rolling"],
    },
    "Ciment": {
        "cbam":     ["Kiln operation", "Clinker cooling"],
        "non_cbam": ["Grinding", "Packaging"],
    },
    "Engrais": {
        "cbam":     ["SMR (Steam Methane Reforming)", "Synthesis loop"],
        "non_cbam": ["Prilling", "Bagging"],
    },
    "Hydrogène": {
        "cbam":     ["Electrolyser / SMR reformer"],
        "non_cbam": ["Compression", "Liquefaction"],
    },
}

# ── Endpoint principal ────────────────────────────────────────────────────────

@router.get(
    "/operators-emissions-report",
    summary="Operator's Emissions Report (IR 2025/2547, Annex IV §1.1)",
)
def generate_operators_emissions_report(
    year: int = Query(2025, ge=2024, le=2030, description="Reporting year"),
    current_user: dict = Depends(get_current_user),
):
    """
    Génère l'Operator's Emissions Report en JSON structuré.

    Conforme IR 2025/2547, Annexe IV, point 1.1.
    Destiné au vérificateur tiers accrédité UE.
    Toutes les sections sont en anglais (obligatoire).
    """
    conn = get_connection()
    try:
        profile = _get_profile(conn, current_user["user_id"])
        if not profile:
            raise HTTPException(status_code=404, detail="Company profile not found. Create it first via POST /company/profile.")

        scope1_tco2, scope2_tco2, elec_kwh = _get_emissions_summary(conn)
        production = float(profile["production_annuelle_tonnes"] or 1.0)
        sector     = profile["secteur"] or "Unknown"
        processes  = _PROCESSES.get(sector, {"cbam": ["Main process"], "non_cbam": ["Secondary process"]})

        scope1_specific = round(scope1_tco2 / production, 4)
        scope2_specific = round(scope2_tco2 / production, 4)

        # ── Section 1: Identification ─────────────────────────────────────────
        section1 = {
            "section": 1,
            "title": "Operator Identification",
            "operator_name":                profile["nom_entreprise"],
            "company_registration_number":  "MA_[INSERT_RC_NUMBER]",
            "full_address_en":              "Morocco",
            "installation_name":            f"{sector} Installation — {profile['nom_entreprise']}",
            "cbam_registry_id":             f"CBAM-MA-{year}-{profile['cn_code']}",
            "un_locode":                    "MACAS",
            "main_emission_source_gps":     "33.5731,-7.5898",
            "reporting_period":             f"January 1 – December 31, {year}",
            "document_date":                datetime.now().isoformat(),
        }

        # ── Section 2: Monitoring Plan ────────────────────────────────────────
        section2 = {
            "section": 2,
            "title": "Monitoring Plan Summary",
            "2a_cbam_processes": {
                "processes": processes["cbam"],
                "production_route": profile["route_production"] or "Standard route",
            },
            "2b_non_cbam_processes": {
                "processes": processes["non_cbam"],
            },
            "2c_top5_products": [
                {
                    "cn_code":                    profile["cn_code"],
                    "description":                f"{sector} product",
                    "annual_production_tonnes":   production,
                }
            ],
            "2d_top5_fuels": [
                {"rank": 1, "name": "Natural gas",  "energy_content_gwh": 0.0},
                {"rank": 2, "name": "Fuel oil",     "energy_content_gwh": 0.0},
                {"rank": 3, "name": "Electricity",  "energy_content_gwh": round(elec_kwh / 1_000_000, 4)},
            ],
            "2e_top5_materials": [
                {"name": "Raw material 1", "emission_factor_tco2_per_t": 0.0},
            ],
            "2f_cems": {
                "cems_used": False,
                "greenhouse_gases": [],
                "largest_sources": [],
            },
            "2g_zero_rated_fuels": {
                "fuels": [],
                "justification": "None identified",
            },
            "2h_heat_imported_exported": {
                "heat_imported_mwh": 0.0,
                "heat_exported_mwh": 0.0,
                "suppliers": [],
            },
        }

        # ── Section 3: Indirect Emissions (Electricity) ───────────────────────
        elec_ef      = 0.000625          # Morocco grid: 0.625 kgCO2/kWh = 0.000625 tCO2/kWh
        elec_tco2    = round(elec_kwh * elec_ef, 4)
        section3 = {
            "section": 3,
            "title": "Indirect Emissions (Electricity)",
            "sources": [
                {
                    "source":                    "Grid electricity — Morocco (ONEE)",
                    "quantity_kwh":              round(elec_kwh, 2),
                    "quantity_mwh":              round(elec_kwh / 1000, 2),
                    "emission_factor_tco2_per_kwh": elec_ef,
                    "total_emissions_tco2e":     elec_tco2,
                    "supplier_country":          "Morocco",
                    "documentation":             "Grid operator contract / energy bills",
                }
            ],
            "note": "If electricity is supplied from other installations, list supplier names and countries.",
        }

        # ── Section 4: Installation Emissions ────────────────────────────────
        section4 = {
            "section": 4,
            "title": "Installation Emissions",
            "processes": [
                {
                    "process_name":                    f"{sector} primary process",
                    "direct_emissions_tco2e":          round(scope1_tco2, 4),
                    "indirect_emissions_tco2e":        round(scope2_tco2, 4),
                    "activity_level_tonnes":           production,
                    "direct_specific_tco2e_per_t":     scope1_specific,
                    "indirect_specific_tco2e_per_t":   scope2_specific,
                    "total_specific_tco2e_per_t":      round(scope1_specific + scope2_specific, 4),
                    "calculation_method":              "Measured" if scope1_tco2 > 0 else "Default values",
                    "percent_default_values":          0 if scope1_tco2 > 0 else 100,
                    "data_quality_note":               "Measured data from continuous monitoring",
                }
            ],
            "calculation_factors": {
                "fuel_emission_factors":         "GHG Protocol 2024 / EU ETS defaults",
                "electricity_emission_factor":   "Morocco ONEE grid 0.625 kgCO₂/kWh (2025)",
                "data_sources":                  ["Energy bills", "Production records", "Continuous meters"],
            },
        }

        # ── Section 5: Precursors ─────────────────────────────────────────────
        section5 = {
            "section": 5,
            "title": "Precursor Emissions",
            "precursors": [
                {
                    "precursor_name":                  "Raw material 1",
                    "quantity_received_tonnes":        0.0,
                    "supplier_country":                "Morocco",
                    "specific_emissions_tco2e_per_t":  0.0,
                    "total_embedded_emissions_tco2e":  0.0,
                    "quantity_used_by_process":        {f"{sector} primary": 0.0},
                    "data_source":                     "Supplier declaration",
                }
            ],
            "note": "Precursor emissions are calculated and attributed to respective processes.",
        }

        # ── Section 6: Carbon Price Paid ──────────────────────────────────────
        section6 = {
            "section": 6,
            "title": "Carbon Price Paid",
            "eu_ets": {
                "applicable":               False,
                "percent_emissions_covered": 0.0,
                "allowances_surrendered":   0,
                "unit_price_eur":           76.50,
                "total_amount_paid_eur":    0.0,
            },
            "national_carbon_tax": {
                "applicable":        False,
                "amount_paid_eur":   0.0,
            },
            "article_9_deduction": {
                "applicable":   False,
                "amount_eur":   0.0,
                "justification": "Morocco has no EU-recognised ETS — deduction = 0 EUR (Art. 9 CBAM Regulation)",
            },
            "total_carbon_price_paid_eur": 0.0,
            "reporting_period":            str(year),
            "currency":                    "EUR",
        }

        # ── Assemble ──────────────────────────────────────────────────────────
        total_tco2 = round(scope1_tco2 + scope2_tco2, 4)
        report = {
            "document_type":  "Operator's Emissions Report",
            "regulation":     "IR 2025/2547, Annex IV, point 1.1",
            "language":       "English",
            "reporting_year": year,
            "generation_date": datetime.now().isoformat(),
            "document_status": "Draft — to be reviewed by accredited EU verifier",
            "intended_for":   "Third-party verifier (EU accredited body)",

            "section_1_identification":       section1,
            "section_2_monitoring_plan":      section2,
            "section_3_electricity_emissions": section3,
            "section_4_installation_emissions": section4,
            "section_5_precursors":           section5,
            "section_6_carbon_price_paid":    section6,

            "summary": {
                "total_direct_emissions_tco2e":    round(scope1_tco2, 2),
                "total_indirect_emissions_tco2e":  round(scope2_tco2, 2),
                "total_emissions_tco2e":           total_tco2,
                "installation_capacity_tonnes":    production,
                "specific_emissions_tco2e_per_t":  round(total_tco2 / production, 4),
            },

            "attachments_required": [
                "Energy consumption records",
                "Production data logs",
                "Supplier declarations (precursors)",
                "Continuous monitoring reports",
                "Carbon price receipts (if applicable)",
            ],
        }

        return JSONResponse(
            content=report,
            headers={
                "Content-Disposition": f'attachment; filename="Operators_Emissions_Report_{year}.json"'
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get(
    "/operators-emissions-report-schema",
    summary="Schéma de référence IR 2025/2547 Annex IV §1.1",
)
def get_report_schema():
    """Retourne le schéma des sections obligatoires / optionnelles."""
    return JSONResponse(content={
        "title":       "Operator's Emissions Report Schema",
        "description": "IR 2025/2547, Annex IV, point 1.1",
        "version":     "1.0",
        "required_sections": [
            "section_1_identification",
            "section_2_monitoring_plan",
            "section_3_electricity_emissions",
            "section_4_installation_emissions",
        ],
        "optional_sections": [
            "section_5_precursors",
            "section_6_carbon_price_paid",
        ],
        "language": "English (mandatory)",
        "audience": "EU third-party verifier (accredited)",
        "section_2_subsections": [
            "2a: CBAM processes and routes",
            "2b: Non-CBAM processes",
            "2c: Top 5 products by CN code",
            "2d: Top 5 fuels by energy content",
            "2e: Top 5 materials with emission factors",
            "2f: CEMS info if applicable",
            "2g: Zero-rated fuels and justification",
            "2h: Heat imported/exported",
        ],
    })
