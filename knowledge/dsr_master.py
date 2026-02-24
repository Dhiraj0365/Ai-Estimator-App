# knowledge/dsr_master.py

from __future__ import annotations

"""
DSR / SoR master loader for the estimator.

This module:
- Loads CPWD (and later State) DSR/SoR data from CSV.
- Normalises field names.
- Derives item_key = "Description (code)".
- Guesses category, measure_type, measurement_rule, discipline when
  not explicitly provided.
- Exposes:
    CPWD_BASE_DSR_2023 : dict[item_key -> raw record dict]
    ITEMS              : dict[item_key -> core.models.Item]
    LOCATION_INDICES   : city -> cost index
    PHASE_GROUPS       : phase -> list[item_key]  (for UI selectbox)
"""

import pandas as pd
from pathlib import Path
from typing import Dict, Any

from core.models import Item


# =============================================================================
# LOCATION INDICES – you can extend/update these as needed
# =============================================================================

LOCATION_INDICES: Dict[str, float] = {
    "Delhi": 100.0,
    "Ghaziabad": 107.0,
    "Noida": 105.0,
    "Gurgaon": 110.0,
    "Mumbai": 135.5,
    "Pune": 128.0,
    "Bangalore": 116.0,
    "Chennai": 122.0,
    "Hyderabad": 118.0,
    "Kolkata": 112.0,
    "Lucknow": 102.0,
    "Kanpur": 101.0,
}


# =============================================================================
# Helper functions to classify items from DSR Code + Description
# =============================================================================

def _guess_category(code: str, desc: str) -> str:
    """
    Rough category guess based on DSR Code and some keyword hints.

    You can refine this mapping over time.
    """
    code = str(code).strip()
    d = desc.lower()

    # Earthwork (chapter 2.xxx etc.)
    if code.startswith("2.8.") or code.startswith("2.6.") or code.startswith("2.7.") or code.startswith("2.10."):
        return "earthwork"
    if code.startswith("2.1."):
        return "earthwork_surface"
    if code.startswith("2.16.") or code.startswith("2.20.") or code.startswith("2.22."):
        return "shoring"
    if code.startswith("2.25"):
        return "backfill"
    if code.startswith("2.31"):
        return "site_clearance"

    # Carriage / transport (chapter 1)
    if code.startswith("1.1") or code.startswith("1.2") or code.startswith("220") or code.startswith("22"):
        if "carriage" in d or "lead" in d:
            return "carriage"

    # Concrete (chapter 3)
    if code.startswith("3."):
        return "concrete"

    # Brickwork (chapter 4)
    if code.startswith("4."):
        return "brickwork"

    # Stone masonry (chapter 5)
    if code.startswith("5."):
        return "stone_masonry"

    # Plaster, DPC, finishing (chapter 6,7,9)
    if code.startswith("6."):
        return "plaster"
    if code.startswith("7."):
        return "dpc"
    if code.startswith("9."):
        if "floor" in d or "flooring" in d:
            return "flooring"
        return "finishing"

    # Painting (chapter 10)
    if code.startswith("10."):
        return "painting"

    # False ceiling (chapter 11)
    if code.startswith("11."):
        return "false_ceiling"

    # Tiles / stone (chapter 12)
    if code.startswith("12."):
        if "tile" in d or "tiles" in d:
            return "tiles"
        if "marble" in d or "granite" in d:
            return "stone_flooring"
        return "finishing"

    # Sanitary / CP fittings / pipes (chapters 13,14,15)
    if code.startswith("13."):
        return "sanitary"
    if code.startswith("14."):
        return "cp_fittings"
    if code.startswith("15."):
        return "pipes"

    # Steel, aluminium, doors, shutters (16–21)
    if code.startswith("16."):
        return "steel_work"
    if code.startswith("17."):
        return "aluminium_work"
    if code.startswith("18."):
        return "doors"
    if code.startswith("19."):
        return "rolling_shutters"
    if code.startswith("20."):
        return "ss_doors"
    if code.startswith("21."):
        return "ceilings"

    # Electrical / MEP (codes like 1.28.xx, 1.30.xx etc. at bottom)
    if code.startswith("1.28") or code.startswith("1.29") or code.startswith("1.30") or code.startswith("1.31"):
        return "electrical_switchgear"
    if code.startswith("1.32") or code.startswith("1.33") or code.startswith("1.34"):
        return "electrical_cables"
    if code.startswith("1.37") or code.startswith("1.38") or code.startswith("1.39") or code.startswith("1.40"):
        return "electrical_lighting"
    if code.startswith("1.41") or code.startswith("1.42") or code.startswith("1.43") or code.startswith("1.44"):
        return "electrical_fans"
    if code.startswith("2.1") and "earthing" in d:
        return "earthing"

    # High code numbers (87xx, 89xx, etc.) – special materials
    if code.startswith("879") or code.startswith("880") or code.startswith("881") or code.startswith("882") or code.startswith("883") or code.startswith("884"):
        return "ss_fittings"
    if code.startswith("895") or code.startswith("896") or code.startswith("897") or code.startswith("898") or code.startswith("899"):
        return "geosynthetics_formwork_special"

    return "misc"


def _guess_type(unit: str) -> str:
    """Determine measure type from unit."""
    u = unit.strip().lower()
    if u in ("cum", "m3", "cu.m", "cu.m."):
        return "volume"
    if u in ("sqm", "m2", "sq.m", "sq.m."):
        return "area"
    if u in ("m", "metre", "meter", "100m"):
        return "length"
    if u in ("kg", "tonne", "quintal"):
        return "weight"
    # 1000 Nos, each, box, set, etc.
    return "each"


def _guess_measurement_rule(code: str, category: str, measure_type: str) -> str:
    """
    Decide which IS1200Engine method should be used for quantity computation
    (for items where you derive quantities from geometry).
    """
    # Earthwork trenches / pits
    if category.startswith("earthwork") and measure_type == "volume":
        return "trench_excavation"

    # Surface earthwork – often just area * depth, but we can treat as volume
    if category == "earthwork_surface":
        return "volume"

    # Brickwork walls (deductions for openings)
    if category == "brickwork" and measure_type == "volume":
        return "brickwork_wall"

    # Stone masonry – same idea
    if category == "stone_masonry" and measure_type == "volume":
        return "stone_masonry_wall"

    # Plaster / painting to walls
    if category in ("plaster", "painting") and measure_type == "area":
        return "wall_finish_area"

    # Tiles / flooring
    if category in ("tiles", "flooring", "stone_flooring") and measure_type == "area":
        return "floor_area"

    # False ceiling
    if category == "false_ceiling" and measure_type == "area":
        return "ceiling_finish_area"

    # Default: simple volume/area/length
    return "volume"


def _guess_discipline(category: str, code: str) -> str:
    """
    Rough discipline split: 'civil' vs 'electrical' vs 'mep'.
    """
    if category.startswith("electrical") or code.startswith("1.3") or code.startswith("1.4"):
        return "electrical"
    if category in ("pipes", "sanitary", "cp_fittings"):
        return "plumbing"
    # Most others: civil
    return "civil"


# =============================================================================
# Loader: from a SINGLE DSR CSV into CPWD_BASE_DSR_2023 and ITEMS
# =============================================================================

def load_cpwd_dsr_2023(csv_name: str = "cpwd_dsr_2023.csv") -> Dict[str, Dict[str, Any]]:
    """
    Load CPWD DSR (Civil + MEP) from a CSV kept in data/cpwd_dsr_2023.csv.

    Expected minimal columns (matching what you pasted):

        S.No, DSR Code, Description, Unit, Rate

    Optional extra columns (ignored or used if present):
        category, type, measurement_rule, discipline, item_key

    We normalise to:
        item_key, code, description, unit, rate, category, type,
        measurement_rule, discipline
    """
    data_path = Path(__file__).resolve().parent.parent / "data" / csv_name
    df = pd.read_csv(data_path)

    # Try to detect column names in a robust way
    cols = {c.lower().strip(): c for c in df.columns}

    code_col = cols.get("dsr code", cols.get("code"))
    desc_col = cols.get("description")
    unit_col = cols.get("unit")
    rate_col = cols.get("rate")

    if not code_col or not desc_col or not unit_col or not rate_col:
        raise ValueError(
            f"CSV {csv_name} must contain at least columns: 'DSR Code', 'Description', 'Unit', 'Rate'. "
            f"Found columns: {list(df.columns)}"
        )

    # Optional existing classification columns
    item_key_col = cols.get("item_key")
    cat_col = cols.get("category")
    type_col = cols.get("type")
    rule_col = cols.get("measurement_rule")
    disc_col = cols.get("discipline")

    items: Dict[str, Dict[str, Any]] = {}

    for _, row in df.iterrows():
        code = str(row[code_col]).strip()
        desc = str(row[desc_col]).strip()
        unit = str(row[unit_col]).strip()
        rate = float(row[rate_col])

        if not code or not desc:
            continue

        # item_key: from column if present, else Description (code)
        if item_key_col:
            item_key = str(row[item_key_col]).strip()
        else:
            item_key = f"{desc} ({code})"

        # category
        if cat_col:
            category = str(row[cat_col]).strip()
        else:
            category = _guess_category(code, desc)

        # type
        if type_col:
            measure_type = str(row[type_col]).strip()
        else:
            measure_type = _guess_type(unit)

        # measurement_rule
        if rule_col:
            measurement_rule = str(row[rule_col]).strip()
        else:
            measurement_rule = _guess_measurement_rule(code, category, measure_type)

        # discipline
        if disc_col:
            discipline = str(row[disc_col]).strip()
        else:
            discipline = _guess_discipline(category, code)

        items[item_key] = {
            "code": code,
            "description": desc,
            "unit": unit,
            "rate": rate,
            "category": category,
            "type": measure_type,
            "measurement_rule": measurement_rule,
            "discipline": discipline,
        }

    return items


# Load on import
CPWD_BASE_DSR_2023: Dict[str, Dict[str, Any]] = load_cpwd_dsr_2023()

# Build Item objects for easier use
ITEMS: Dict[str, Item] = {
    key: Item.from_dsr_record(key, rec)
    for key, rec in CPWD_BASE_DSR_2023.items()
}


# =============================================================================
# PHASE GROUPS – minimal, using your actual simplified foundation/finish items
# =============================================================================
# These are used by the UI selectbox in SOQ Tab. You can expand over time.
#
# They rely on the simplified descriptions that appear near the end of your
# dataset, e.g.:
#   1040,2.8.1,"Earthwork excavation foundation trench",cum,260.30
#   1043,3.1.1,"PCC 1:5:10 foundation base",cum,4205.45
#   1044,4.1.1,"Brickwork FB non modular foundation",cum,5234.60
#   1046,6.1.1,"12mm cement plaster 1:6 fair face",sqm,185.40
#   1049,12.1.1,"Vitrified floor tiles 600x600mm",sqm,1245.60
#   1048,10.1.1,"Premium acrylic emulsion painting",sqm,156.80
#
# Loader will have created item_keys like:
#   "Earthwork excavation foundation trench (2.8.1)"
#   "PCC 1:5:10 foundation base (3.1.1)"
#   ...


PHASE_GROUPS: Dict[str, list[str]] = {
    "1️⃣ SUBSTRUCTURE": [
        "Earthwork excavation foundation trench (2.8.1)",
        "Surface excavation 30cm depth all soil (2.1.1)",
        "PCC 1:5:10 foundation base (3.1.1)",
        "Brickwork FB non modular foundation (4.1.1)",
        "RR masonry foundation uncoursed (5.1.1)",
        "Filling excavated earth trenches (2.25)",
        "Clearing jungle rank vegetation (2.31)",
    ],
    "2️⃣ PLINTH": [
        "Damp proof course 50mm thick (7.1.1)",
        "Integral water proofing compound (7.2.1)",
    ],
    "3️⃣ SUPERSTRUCTURE": [
        "Brickwork superstructure FB bricks (4.1.2)",
        "Ashlar stone superstructure (5.2.1)",
        "12mm cement plaster 1:6 fair face (6.1.1)",
        "15mm cement plaster 1:6 walls (6.1.2)",
    ],
    "4️⃣ FINISHING": [
        "Vitrified floor tiles 600x600mm (12.1.1)",
        "Ceramic wall tiles 450x300mm (12.2.1)",
        "Premium acrylic emulsion painting (10.1.1)",
        "Plastic emulsion paint walls (10.2.1)",
        "Wall care putty painting prep (10.5.1)",
    ],
}

# Filter PHASE_GROUPS to only include keys that actually exist in data
for phase, keys in list(PHASE_GROUPS.items()):
    PHASE_GROUPS[phase] = [
        k for k in keys if k in CPWD_BASE_DSR_2023
    ]
