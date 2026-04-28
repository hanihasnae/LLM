# routers/erp.py
# Importe les données depuis l'ERP vers CarbonIQ

from fastapi import APIRouter, HTTPException
import requests
from database import get_connection
from datetime import datetime

router = APIRouter()

ERP_URL = "http://localhost:8001"


@router.post("/erp/importer")
def importer_depuis_erp(mois: str = None):
    """
    Récupère les données de l'ERP et les importe
    dans la base de données CarbonIQ.
    """

    try:
        # Récupère les données de l'ERP
        url = f"{ERP_URL}/erp/consommations"
        if mois:
            url += f"?mois={mois}"

        res = requests.get(url, timeout=5)
        erp_data = res.json()["data"]

    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"ERP inaccessible : {str(e)}"
        )

    conn     = get_connection()
    cursor   = conn.cursor()
    importes = []

    for ligne in erp_data:
        mois_str = ligne["mois"]

        # Date = dernier jour du mois
        annee, mois_num = mois_str.split("-")
        date_str = f"{mois_str}-28"

        # ── Électricité ──────────────────────────────
        if ligne.get("electricite_kwh"):
            cursor.execute("""
                INSERT INTO activities (source, quantity, unit, date)
                VALUES (%s, %s, %s, %s) RETURNING id
            """, ("electricity", ligne["electricite_kwh"], "kWh", date_str))

            act_id = cursor.fetchone()["id"]
            cursor.execute(
                "SELECT factor, scope FROM emission_factors WHERE energy_type = %s",
                ("electricity",)
            )
            f = cursor.fetchone()
            if f:
                co2 = ligne["electricite_kwh"] * f["factor"]
                cursor.execute(
                    "INSERT INTO emissions (activity_id, co2_kg, scope) VALUES (%s, %s, %s)",
                    (act_id, co2, f["scope"])
                )
                importes.append({"mois": mois_str, "type": "electricity", "co2_kg": co2})

        # ── Fuel ─────────────────────────────────────
        if ligne.get("fuel_litres"):
            cursor.execute("""
                INSERT INTO activities (source, quantity, unit, date)
                VALUES (%s, %s, %s, %s) RETURNING id
            """, ("fuel", ligne["fuel_litres"], "litres", date_str))

            act_id = cursor.fetchone()["id"]
            cursor.execute(
                "SELECT factor, scope FROM emission_factors WHERE energy_type = %s",
                ("fuel",)
            )
            f = cursor.fetchone()
            if f:
                co2 = ligne["fuel_litres"] * f["factor"]
                cursor.execute(
                    "INSERT INTO emissions (activity_id, co2_kg, scope) VALUES (%s, %s, %s)",
                    (act_id, co2, f["scope"])
                )
                importes.append({"mois": mois_str, "type": "fuel", "co2_kg": co2})

        # ── Gaz ──────────────────────────────────────
        if ligne.get("gaz_m3"):
            cursor.execute("""
                INSERT INTO activities (source, quantity, unit, date)
                VALUES (%s, %s, %s, %s) RETURNING id
            """, ("gas", ligne["gaz_m3"], "m3", date_str))

            act_id = cursor.fetchone()["id"]
            cursor.execute(
                "SELECT factor, scope FROM emission_factors WHERE energy_type = %s",
                ("gas",)
            )
            f = cursor.fetchone()
            if f:
                co2 = ligne["gaz_m3"] * f["factor"]
                cursor.execute(
                    "INSERT INTO emissions (activity_id, co2_kg, scope) VALUES (%s, %s, %s)",
                    (act_id, co2, f["scope"])
                )
                importes.append({"mois": mois_str, "type": "gas", "co2_kg": co2})

    conn.commit()
    cursor.close()
    conn.close()

    total_co2 = sum(i["co2_kg"] for i in importes)

    return {
        "message": f"✅ {len(importes)} entrées importées depuis l'ERP",
        "importes": importes,
        "total_co2_kg": round(total_co2, 2)
    }


@router.get("/erp/statut")
def statut_erp():
    """Vérifie si l'ERP est accessible"""
    try:
        res = requests.get(f"{ERP_URL}/", timeout=3)
        return {"statut": "connecté ✅", "url": ERP_URL}
    except:
        return {"statut": "déconnecté ❌", "url": ERP_URL}