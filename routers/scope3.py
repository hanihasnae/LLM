# ══════════════════════════════════════════
# routers/scope3.py — CRUD Scope 3
# ══════════════════════════════════════════

from fastapi import APIRouter, HTTPException, Query
from database import get_connection as get_db_connection
from datetime import date, datetime
from typing import Optional

router = APIRouter(prefix="/scope3", tags=["Scope 3"])

# ── Mapping facteurs (sera remplacé par DB lookup) ──
SCOPE3_FACTORS = {
    # Cat 1 - Matières premières
    "steel_raw": 1.85, "aluminum_raw": 8.24, "cement_clinker": 0.83,
    "iron_ore": 0.02, "coal_coke": 3.09, "limestone": 0.012,
    "ammonia": 2.16, "bauxite": 0.007, "scrap_metal": 0.42,
    # Cat 3 - Énergie amont
    "electricity_upstream": 0.108, "fuel_upstream": 0.59, "gas_upstream": 0.41,
    # Cat 4 & 9 - Transport
    "transport_truck": 0.096, "transport_rail": 0.028,
    "transport_ship": 0.016, "transport_air": 0.602,
    "transport_truck_out": 0.096, "transport_ship_out": 0.016,
    "transport_rail_out": 0.028,
    # Cat 5 - Déchets
    "waste_landfill": 0.586, "waste_incineration": 0.021, "waste_recycling": 0.010,
    # Cat 12 - Fin de vie
    "end_of_life_steel": 0.15, "end_of_life_aluminum": 0.30,
    "end_of_life_cement": 0.01, "end_of_life_landfill": 0.50,
}

SCOPE3_CATEGORIES = {
    1: "Matières premières achetées",
    3: "Énergie amont (hors S1/S2)",
    4: "Transport entrant",
    5: "Déchets de production",
    9: "Transport sortant",
    12: "Fin de vie produits vendus",
}


# ── POST /scope3/entries — Ajouter une entrée ──
@router.post("/entries")
async def create_scope3_entry(entry: dict):
    """Ajouter une entrée Scope 3 avec calcul automatique CO2"""
    
    source_type = entry.get("source_type")
    quantity = entry.get("quantity", 0)
    category = entry.get("category")
    
    # Validation catégorie
    if category not in SCOPE3_CATEGORIES:
        raise HTTPException(400, f"Catégorie {category} non supportée. Valides: {list(SCOPE3_CATEGORIES.keys())}")
    
    # Récupérer facteur
    factor = SCOPE3_FACTORS.get(source_type)
    if not factor:
        raise HTTPException(400, f"Type source '{source_type}' inconnu. Valides: {list(SCOPE3_FACTORS.keys())}")
    
    # Calcul CO2
    # Pour transport : quantity = t.km (poids × distance)
    if category in [4, 9] and entry.get("distance_km") and entry.get("weight_tonnes"):
        effective_quantity = entry["distance_km"] * entry["weight_tonnes"]
    else:
        effective_quantity = quantity
    
    co2_kg = effective_quantity * factor
    
    # Direction automatique
    direction = "upstream" if category <= 8 else "downstream"
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("""
        INSERT INTO scope3_entries 
        (category, category_name, direction, description, source_type,
         quantity, unit, emission_factor, co2_kg,
         distance_km, weight_tonnes, transport_mode, origin, destination,
         supplier_name, supplier_country, date, data_quality, source_document,
         period_quarter, period_year)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        RETURNING id
    """, (
        category, SCOPE3_CATEGORIES[category], direction,
        entry.get("description", ""),
        source_type, effective_quantity, entry.get("unit", ""),
        factor, co2_kg,
        entry.get("distance_km"), entry.get("weight_tonnes"),
        entry.get("transport_mode"), entry.get("origin"), entry.get("destination"),
        entry.get("supplier_name"), entry.get("supplier_country"),
        entry.get("date"), entry.get("data_quality", "estimated"),
        entry.get("source_document"),
        entry.get("period_quarter"), entry.get("period_year")
    ))
    
    new_id = cur.fetchone()["id"]
    conn.commit()
    cur.close()
    conn.close()
    
    return {
        "id": new_id,
        "co2_kg": round(co2_kg, 2),
        "co2_tonnes": round(co2_kg / 1000, 4),
        "emission_factor": factor,
        "category": category,
        "category_name": SCOPE3_CATEGORIES[category],
        "direction": direction,
        "message": f"✅ Entrée Scope 3 créée — {round(co2_kg, 2)} kg CO2"
    }


# ── GET /scope3/entries — Lister les entrées ──
@router.get("/entries")
async def list_scope3_entries(
    direction: Optional[str] = None,
    category: Optional[int] = None
):
    """Liste des entrées Scope 3 actives"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    query = "SELECT * FROM scope3_entries WHERE actif = true"
    params = []
    
    if direction:
        query += " AND direction = %s"
        params.append(direction)
    if category:
        query += " AND category = %s"
        params.append(category)
    
    query += " ORDER BY date DESC"
    cur.execute(query, params)
    
    rows = [dict(row) for row in cur.fetchall()]
    
    cur.close()
    conn.close()
    return rows


# ── GET /scope3/summary — Résumé Scope 3 ──
@router.get("/summary")
async def scope3_summary():
    """Résumé complet des émissions Scope 3"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Total par direction
    cur.execute("""
        SELECT direction, SUM(co2_kg) as total
        FROM scope3_entries WHERE actif = true
        GROUP BY direction
    """)
    direction_totals = {row["direction"]: float(row["total"]) for row in cur.fetchall()}

    # Total par catégorie
    cur.execute("""
        SELECT category, SUM(co2_kg) AS total
        FROM scope3_entries WHERE actif = true
        GROUP BY category ORDER BY category
    """)
    category_totals = {str(row["category"]): round(float(row["total"]), 2) for row in cur.fetchall()}

    # Qualité des données
    cur.execute("""
        SELECT data_quality, COUNT(*) AS cnt
        FROM scope3_entries WHERE actif = true
        GROUP BY data_quality
    """)
    quality = {row["data_quality"]: int(row["cnt"]) for row in cur.fetchall()}

    # Count
    cur.execute("SELECT COUNT(*) AS cnt FROM scope3_entries WHERE actif = true")
    count = cur.fetchone()["cnt"]
    
    upstream = direction_totals.get("upstream", 0) or 0
    downstream = direction_totals.get("downstream", 0) or 0
    total = upstream + downstream
    
    cur.close()
    conn.close()
    
    return {
        "total_co2_kg": round(total, 2),
        "total_co2_tonnes": round(total / 1000, 4),
        "upstream_co2_kg": round(upstream, 2),
        "upstream_co2_tonnes": round(upstream / 1000, 4),
        "downstream_co2_kg": round(downstream, 2),
        "downstream_co2_tonnes": round(downstream / 1000, 4),
        "by_category": category_totals,
        "entry_count": count,
        "data_quality_breakdown": quality
    }


# ── GET /scope3/factors — Facteurs disponibles ──
@router.get("/factors")
async def scope3_factors():
    """Liste tous les facteurs d'émission Scope 3 disponibles"""
    result = {}
    for cat_id, cat_name in SCOPE3_CATEGORIES.items():
        result[cat_id] = {
            "name": cat_name,
            "factors": {
                k: {"factor": v, "unit": "kg CO2/unité"}
                for k, v in SCOPE3_FACTORS.items()
            }
        }
    return result


# ── GET /scope3/categories — Catégories actives ──
@router.get("/categories")
async def scope3_categories():
    """Liste les catégories Scope 3 actives dans CarbonIQ"""
    return {
        "upstream": [
            {"id": 1, "name": "Matières premières achetées", "ghg": "Purchased goods & services"},
            {"id": 3, "name": "Énergie amont (hors S1/S2)", "ghg": "Fuel & energy-related"},
            {"id": 4, "name": "Transport entrant", "ghg": "Upstream transportation"},
            {"id": 5, "name": "Déchets de production", "ghg": "Waste generated in operations"},
        ],
        "downstream": [
            {"id": 9, "name": "Transport sortant", "ghg": "Downstream transportation"},
            {"id": 12, "name": "Fin de vie produits", "ghg": "End-of-life treatment"},
        ]
    }


# ── DELETE (soft) /scope3/entries/{id} ──
@router.post("/entries/{entry_id}/supprimer")
async def soft_delete_scope3(entry_id: int, body: dict):
    """Soft delete Scope 3 (ISO 14064 compliant)"""
    raison = body.get("raison")
    if not raison:
        raise HTTPException(400, "Raison obligatoire pour la traçabilité CBAM")
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("""
        UPDATE scope3_entries SET actif = false, raison = %s, updated_at = NOW()
        WHERE id = %s
    """, (raison, entry_id))
    
    # Journal
    cur.execute("""
        INSERT INTO journal_scope3 (scope3_entry_id, champ_modifie, ancienne_val, nouvelle_val, raison)
        VALUES (%s, 'actif', 'true', 'false', %s)
    """, (entry_id, raison))
    
    conn.commit()
    cur.close()
    conn.close()
    
    return {"message": f"Entrée {entry_id} désactivée", "raison": raison}