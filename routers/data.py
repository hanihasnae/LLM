# routers/data.py
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from database import get_connection
from datetime import date
from contextlib import contextmanager
from typing import Optional
import csv, io

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
    source: str                          # 'electricity', 'fuel', 'gas'
    quantity: float                      # combien
    unit: str                            # 'kWh', 'litres', 'm3'
    date: date                           # la date
    methode_saisie: str = "manuel"       # 'manuel', 'iot', 'erp', 'pdf'
    source_document: Optional[str] = None  # ID capteur, nom fichier ERP, etc.

# --- ENDPOINTS ---

@router.get("/activities")
def get_all_activities(
    methode: Optional[str] = Query(None, description="iot | erp | manuel | pdf"),
    source:  Optional[str] = Query(None, description="electricity | fuel | gas"),
    from_date: Optional[date] = Query(None),
    to_date:   Optional[date] = Query(None),
    limit: int = Query(500, le=2000),
):
    query  = """
        SELECT a.*, ROUND(e.co2_kg::numeric, 3) AS co2_kg, e.scope
        FROM activities a
        LEFT JOIN emissions e ON e.activity_id = a.id AND e.actif = true
        WHERE a.actif = true
    """
    params = []
    if methode:
        query += " AND a.methode_saisie = %s"; params.append(methode)
    if source:
        query += " AND a.source = %s"; params.append(source)
    if from_date:
        query += " AND a.date >= %s"; params.append(from_date)
    if to_date:
        query += " AND a.date <= %s"; params.append(to_date)
    query += " ORDER BY a.created_at DESC LIMIT %s"; params.append(limit)

    with db_cursor() as (cursor, _):
        cursor.execute(query, params)
        activities = cursor.fetchall()
    return {"data": activities, "count": len(activities)}


@router.get("/activities/live")
def get_live_feed(limit: int = Query(50, le=200)):
    """Dernières activités toutes sources confondues — pour le flux temps réel."""
    with db_cursor() as (cursor, _):
        cursor.execute("""
            SELECT a.id, a.source, a.quantity, a.unit, a.date,
                   a.methode_saisie, a.source_document, a.created_at,
                   e.co2_kg, e.scope
            FROM activities a
            LEFT JOIN emissions e ON e.activity_id = a.id AND e.actif = true
            WHERE a.actif = true
            ORDER BY a.created_at DESC
            LIMIT %s
        """, (limit,))
        rows = cursor.fetchall()
    return {"data": rows, "count": len(rows)}


@router.get("/activities/export")
def export_activities_csv(
    methode:   Optional[str]  = Query(None),
    source:    Optional[str]  = Query(None),
    from_date: Optional[date] = Query(None),
    to_date:   Optional[date] = Query(None),
):
    """Export CSV filtré des activités — téléchargement direct."""
    query  = """
        SELECT a.id, a.source, a.quantity, a.unit, a.date,
               a.methode_saisie, a.source_document, a.created_at,
               ROUND(e.co2_kg::numeric, 3) AS co2_kg, e.scope
        FROM activities a
        LEFT JOIN emissions e ON e.activity_id = a.id AND e.actif = true
        WHERE a.actif = true
    """
    params = []
    if methode:
        query += " AND a.methode_saisie = %s"; params.append(methode)
    if source:
        query += " AND a.source = %s"; params.append(source)
    if from_date:
        query += " AND a.date >= %s"; params.append(from_date)
    if to_date:
        query += " AND a.date <= %s"; params.append(to_date)
    query += " ORDER BY a.created_at DESC"

    with db_cursor() as (cursor, _):
        cursor.execute(query, params)
        rows = cursor.fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "source", "quantity", "unit", "date",
                     "methode_saisie", "source_document", "created_at", "co2_kg", "scope"])
    for row in rows:
        writer.writerow([
            row["id"], row["source"], row["quantity"], row["unit"], row["date"],
            row["methode_saisie"], row["source_document"], row["created_at"],
            row["co2_kg"], row["scope"]
        ])

    output.seek(0)
    filename = f"carboniq_activities_{date.today().isoformat()}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.post("/activities")
def add_activity(activity: ActivityInput):
    
    # Vérifie que la source est valide
    valid_sources = ["electricity", "fuel", "gas"]
    if activity.source not in valid_sources:
        raise HTTPException(
            status_code=400,
            detail=f"Source invalide. Choisir parmi : {valid_sources}"
        )

    with db_cursor() as (cursor, conn):
        
        # Étape 1 — Insère l'activité
        cursor.execute("""
            INSERT INTO activities (source, quantity, unit, date, methode_saisie, source_document)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (activity.source, activity.quantity, activity.unit, activity.date,
              activity.methode_saisie, activity.source_document))
        
        new_id = cursor.fetchone()["id"]

        # Étape 2 — Trouve le facteur d'émission
        cursor.execute("""
            SELECT factor, scope FROM emission_factors
            WHERE energy_type = %s
        """, (activity.source,))
        
        factor_row = cursor.fetchone()

        # Étape 3 — Calcule et insère l'émission
        co2_kg = 0
        scope  = 0

        if factor_row:
            co2_kg = activity.quantity * factor_row["factor"]
            scope  = factor_row["scope"]

            cursor.execute("""
                INSERT INTO emissions (activity_id, co2_kg, scope)
                VALUES (%s, %s, %s)
            """, (new_id, co2_kg, scope))

        conn.commit()

    return {
        "message": "Activité ajoutée ✅",
        "id": new_id,
        "calcul": {
            "quantite":    activity.quantity,
            "unite":       activity.unit,
            "facteur_co2": factor_row["factor"] if factor_row else 0,
            "co2_kg":      round(co2_kg, 1),
            "co2_tonnes":  round(co2_kg / 1000, 4),
            "scope":       f"Scope {scope}"
        }
    }


@router.get("/emission-factors")
def get_emission_factors():
    with db_cursor() as (cursor, _):
        cursor.execute("SELECT * FROM emission_factors")
        factors = cursor.fetchall()
    return {"data": factors}


@router.get("/emissions")
def get_emissions():
    with db_cursor() as (cursor, _):
        # Lit la table emissions (source de vérité = même source que le LLM)
        # Filtre actif=true sur activities ET emissions
        cursor.execute("""
            SELECT
                a.id,
                a.source,
                a.quantity,
                a.unit,
                a.date,
                e.scope,
                e.co2_kg
            FROM activities a
            JOIN emissions e ON e.activity_id = a.id
            WHERE a.actif = true
              AND e.actif = true
            ORDER BY a.date DESC
        """)
        activities = cursor.fetchall()

        cursor.execute("""
            SELECT
                TO_CHAR(a.date, 'Mon YY')   AS mois,
                DATE_TRUNC('month', a.date) AS mois_date,
                ROUND(SUM(CASE WHEN e.scope = 1 THEN e.co2_kg ELSE 0 END)::numeric, 1) AS scope1_kg,
                ROUND(SUM(CASE WHEN e.scope = 2 THEN e.co2_kg ELSE 0 END)::numeric, 1) AS scope2_kg
            FROM activities a
            JOIN emissions e ON e.activity_id = a.id
            WHERE a.actif = true
              AND e.actif = true
            GROUP BY TO_CHAR(a.date, 'Mon YY'), DATE_TRUNC('month', a.date)
            ORDER BY mois_date
        """)
        s12_mois = {row["mois_date"]: dict(row) for row in cursor.fetchall()}

        cursor.execute("""
            SELECT
                TO_CHAR(date, 'Mon YY')   AS mois,
                DATE_TRUNC('month', date) AS mois_date,
                ROUND(SUM(co2_kg)::numeric, 1) AS scope3_kg
            FROM scope3_entries
            WHERE actif = true
            GROUP BY TO_CHAR(date, 'Mon YY'), DATE_TRUNC('month', date)
            ORDER BY mois_date
        """)
        s3_mois = {row["mois_date"]: float(row["scope3_kg"]) for row in cursor.fetchall()}

    # Fusionner les deux séries par mois_date
    all_dates = sorted(set(list(s12_mois.keys()) + list(s3_mois.keys())))
    par_mois = []
    for d in all_dates:
        base = s12_mois.get(d, {"mois": d.strftime("%b %y") if hasattr(d, "strftime") else str(d),
                                 "mois_date": d, "scope1_kg": 0.0, "scope2_kg": 0.0})
        par_mois.append({
            "mois":      base["mois"],
            "mois_date": base["mois_date"],
            "scope1_kg": float(base["scope1_kg"] or 0),
            "scope2_kg": float(base["scope2_kg"] or 0),
            "scope3_kg": s3_mois.get(d, 0.0),
        })

    return {"activities": activities, "par_mois": par_mois}


@router.get("/summary")
def get_summary():
    with db_cursor() as (cursor, _):

        # ── 1. Détail par source — donut chart ────────────────────────────────
        cursor.execute("""
            SELECT
                a.source,
                SUM(a.quantity) AS total_quantity,
                a.unit,
                ef.factor,
                SUM(a.quantity * ef.factor) AS total_co2_kg,
                ef.scope
            FROM activities a
            JOIN emission_factors ef ON a.source = ef.energy_type
            WHERE a.actif = true
            GROUP BY a.source, a.unit, ef.factor, ef.scope
        """)
        summary = cursor.fetchall()

        # ── 2. Scope 1 & 2 ────────────────────────────────────────────────────
        cursor.execute("""
            SELECT e.scope, SUM(e.co2_kg) AS co2_kg
            FROM emissions e
            JOIN activities a ON a.id = e.activity_id
            WHERE a.actif = true AND e.actif = true
            GROUP BY e.scope
        """)
        scopes = {row["scope"]: float(row["co2_kg"]) for row in cursor.fetchall()}

        # ── 3. Scope 3 ────────────────────────────────────────────────────────
        cursor.execute("""
            SELECT direction, SUM(co2_kg) AS co2_kg
            FROM scope3_entries
            WHERE actif = true
            GROUP BY direction
        """)
        scope3_dir = {row["direction"]: float(row["co2_kg"]) for row in cursor.fetchall()}

    scope1_kg            = scopes.get(1, 0.0)
    scope2_kg            = scopes.get(2, 0.0)
    scope3_upstream_kg   = scope3_dir.get("upstream", 0.0)
    scope3_downstream_kg = scope3_dir.get("downstream", 0.0)
    scope3_kg            = scope3_upstream_kg + scope3_downstream_kg
    total_kg             = scope1_kg + scope2_kg + scope3_kg

    return {
        "details":                summary,
        "scope1_kg":              round(scope1_kg, 3),
        "scope2_kg":              round(scope2_kg, 3),
        "scope3_kg":              round(scope3_kg, 3),
        "scope3_upstream_kg":     round(scope3_upstream_kg, 3),
        "scope3_downstream_kg":   round(scope3_downstream_kg, 3),
        "total_co2_kg":           round(total_kg, 3),
        "scope1_tonnes":          round(scope1_kg / 1000, 3),
        "scope2_tonnes":          round(scope2_kg / 1000, 3),
        "scope3_tonnes":          round(scope3_kg / 1000, 3),
        "total_co2_tonnes":       round(total_kg / 1000, 3),
        "scope1_pct":             round(scope1_kg / total_kg * 100, 1) if total_kg > 0 else 0,
        "scope2_pct":             round(scope2_kg / total_kg * 100, 1) if total_kg > 0 else 0,
        "scope3_pct":             round(scope3_kg / total_kg * 100, 1) if total_kg > 0 else 0,
    }