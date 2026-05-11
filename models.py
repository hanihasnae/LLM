# ══════════════════════════════════════════
# AJOUTER dans models.py
# ══════════════════════════════════════════

from pydantic import BaseModel, Field
from typing import Optional
from datetime import date

# ── Schéma de saisie Scope 3 ──
class Scope3EntryCreate(BaseModel):
    category: int = Field(..., description="Catégorie GHG Protocol: 1,3,4,5,9,12")
    direction: str = Field(..., description="'upstream' ou 'downstream'")
    description: str = Field(..., description="Description de l'entrée")
    source_type: str = Field(..., description="Type: steel_raw, transport_truck, etc.")
    quantity: float = Field(..., gt=0)
    unit: str
    date: date
    
    # Optionnels
    distance_km: Optional[float] = None
    weight_tonnes: Optional[float] = None
    transport_mode: Optional[str] = None
    origin: Optional[str] = None
    destination: Optional[str] = None
    supplier_name: Optional[str] = None
    supplier_country: Optional[str] = None
    data_quality: str = "estimated"
    source_document: Optional[str] = None

class Scope3EntryResponse(BaseModel):
    id: int
    category: int
    category_name: str
    direction: str
    description: str
    source_type: str
    quantity: float
    unit: str
    emission_factor: float
    co2_kg: float
    date: date
    data_quality: str
    supplier_name: Optional[str] = None
    transport_mode: Optional[str] = None
    origin: Optional[str] = None
    destination: Optional[str] = None

class Scope3Summary(BaseModel):
    total_co2_kg: float
    total_co2_tonnes: float
    upstream_co2_kg: float
    downstream_co2_kg: float
    by_category: dict        # { "1": 1234.5, "4": 567.8, ... }
    entry_count: int
    data_quality_breakdown: dict  # { "measured": 5, "estimated": 12, "default": 3 }

# ── Mapping catégories ──
SCOPE3_CATEGORIES = {
    1:  {"name": "Matières premières achetées",   "direction": "upstream",   "ghg_name": "Purchased goods & services"},
    3:  {"name": "Énergie amont (hors S1/S2)",    "direction": "upstream",   "ghg_name": "Fuel & energy-related activities"},
    4:  {"name": "Transport entrant",             "direction": "upstream",   "ghg_name": "Upstream transportation"},
    5:  {"name": "Déchets de production",         "direction": "upstream",   "ghg_name": "Waste generated in operations"},
    9:  {"name": "Transport sortant",             "direction": "downstream", "ghg_name": "Downstream transportation"},
    12: {"name": "Fin de vie produits vendus",    "direction": "downstream", "ghg_name": "End-of-life treatment"},
}