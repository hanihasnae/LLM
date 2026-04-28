# routers/data.py
from fastapi import APIRouter
from pydantic import BaseModel
from database import get_connection
from datetime import date
from contextlib import contextmanager

router = APIRouter()

@contextmanager
def db_cursor():
    """Ouvre une connexion, donne le curseur, ferme tout automatiquement."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        yield cursor, conn
    finally:
        cursor.close()
        conn.close()

# --- MODÈLES (structure des données qu'on envoie/reçoit) ---

class ActivityInput(BaseModel):
    """Structure pour ajouter une activité"""
    source: str      # 'electricity', 'fuel', 'gas'
    quantity: float  # combien
    unit: str        # 'kWh', 'litres', 'm3'
    date: date       # la date

# --- ENDPOINTS ---

@router.get("/activities")
def get_all_activities():
    with db_cursor() as (cursor, _):
        cursor.execute("SELECT * FROM activities ORDER BY date DESC")
        activities = cursor.fetchall()
    return {"data": activities, "count": len(activities)}


@router.post("/activities")
def add_activity(activity: ActivityInput):
    with db_cursor() as (cursor, conn):
        cursor.execute("""
            INSERT INTO activities (source, quantity, unit, date)
            VALUES (%s, %s, %s, %s)
            RETURNING id
        """, (activity.source, activity.quantity, activity.unit, activity.date))
        new_id = cursor.fetchone()["id"]
        conn.commit()
    return {"message": "Activité ajoutée ✅", "id": new_id}


@router.get("/emission-factors")
def get_emission_factors():
    with db_cursor() as (cursor, _):
        cursor.execute("SELECT * FROM emission_factors")
        factors = cursor.fetchall()
    return {"data": factors}


@router.get("/emissions")
def get_emissions():
    with db_cursor() as (cursor, _):
        cursor.execute("""
            SELECT
                a.id, a.source, a.quantity, a.unit, a.date, ef.scope,
                ROUND((a.quantity * ef.factor)::numeric, 2) AS co2_kg
            FROM activities a
            JOIN emission_factors ef ON a.source = ef.energy_type
            ORDER BY a.date DESC
            LIMIT 100
        """)
        activities = cursor.fetchall()

        cursor.execute("""
            SELECT
                TO_CHAR(a.date, 'Mon YY')   AS mois,
                DATE_TRUNC('month', a.date) AS mois_date,
                ROUND(SUM(CASE WHEN ef.scope = 1 THEN a.quantity * ef.factor ELSE 0 END)::numeric, 2) AS scope1_kg,
                ROUND(SUM(CASE WHEN ef.scope = 2 THEN a.quantity * ef.factor ELSE 0 END)::numeric, 2) AS scope2_kg
            FROM activities a
            JOIN emission_factors ef ON a.source = ef.energy_type
            GROUP BY TO_CHAR(a.date, 'Mon YY'), DATE_TRUNC('month', a.date)
            ORDER BY mois_date
        """)
        par_mois = cursor.fetchall()

    return {"activities": activities, "par_mois": par_mois}


@router.get("/summary")
def get_summary():
    with db_cursor() as (cursor, _):
        cursor.execute("""
            SELECT
                a.source, SUM(a.quantity) as total_quantity, a.unit, ef.factor,
                SUM(a.quantity * ef.factor) as total_co2_kg, ef.scope
            FROM activities a
            JOIN emission_factors ef ON a.source = ef.energy_type
            GROUP BY a.source, a.unit, ef.factor, ef.scope
        """)
        summary = cursor.fetchall()

    total_co2 = sum(row["total_co2_kg"] for row in summary)
    return {
        "details": summary,
        "total_co2_kg":     round(total_co2, 2),
        "total_co2_tonnes": round(total_co2 / 1000, 4)
    }
