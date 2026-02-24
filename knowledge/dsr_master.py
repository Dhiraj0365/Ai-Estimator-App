from __future__ import annotations

"""
DSR / SoR master loader for the estimator.

This module:
- Loads CPWD and (optionally) State SoR Civil + Electrical data from CSV.
- Normalises field names.
- Derives item_key = "Description (code)" when not provided.
- Guesses category, measure_type, measurement_rule, discipline when
  not explicitly provided.
- Exposes:
    CPWD_BASE_DSR_2023 : dict[item_key -> record]  (default CPWD source)
    ITEMS              : dict[item_key -> core.models.Item]
    RATE_SOURCES       : dict[source_name -> dict[item_key -> record]]
    LOCATION_INDICES   : city -> cost index
    PHASE_GROUPS       : phase -> list[item_key]  (for SOQ selectbox)

It is UI‑agnostic and can be imported from your Streamlit app and
composite modules.
"""

import pandas as pd
from pathlib import Path
from typing import Dict, Any

from core.models import Item


# =============================================================================
# LOCATION INDICES – adjust as needed
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

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


# =============================================================================
# Category / type / rule / discipline guessers
# =============================================================================

def _guess_category(code: str, desc: str) -> str:
    """
    Rough category guess based on DSR Code and some keyword hints.

    This is shared across CPWD/State SoR; refine as needed.
    """
    code = str(code).strip()
    d = desc.lower()

    # Earthwork (chapter 2)
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

    # Carriage / transport (1.x, 22xx, 23xx etc.)
    if code.startswith("1.1") or code.startswith("1.2") or code.startswith("22") or code.startswith("23"):
        if "carriage" in d or "lead" in d:
            return "carriage"

    # Concrete (chapter 3)
    if code.startswith("3."):
        return "concrete"

    # Brickwork (chapter 4)
    if code.startswith("4."):
        return "brickwork"

    # Stone masonry (chapter 5) vs Fire alarm (also 5.x in E&M)
    if code.startswith("5."):
        if "detector" in d or "alarm" in d or "hooter" in d or "panel" in d:
            return "fire_alarm"
        return "stone_masonry"

    # Plaster, DPC, flooring (6,7,9)
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

    # Sanitary / CP fittings / pipes (13,14,15)
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

    # Electrical (1.xx family)
    if code.startswith("1.28") or code.startswith("1.29") or code.startswith("1.30") or code.startswith("1.31"):
        return "electrical_switchgear"
    if code.startswith("1.32") or code.startswith("1.33") or code.startswith("1.34"):
        return "electrical_cables"
    if code.startswith("1.37") or code.startswith("1.38") or code.startswith("1.39") or code.startswith("1.40"):
        return "electrical_lighting"
    if code.startswith("1.41") or code.startswith("1.42") or code.startswith("1.43") or code.startswith("1.44"):
        return "electrical_fans"

    # Earthing / lightning
    if "earthing" in d or "earth electrode" in d or "lightning conductor" in d:
        return "earthing"

    # Fire alarm (if code not matched)
    if "fire alarm" in d or "smoke detector" in d or "heat detector" in d or "hooter" in d or "mcp" in d:
        return "fire_alarm"

    # Special fittings & geosynthetics
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

    # Surface earthwork
    if category == "earthwork_surface":
        return "volume"

    # Brickwork walls (deductions for openings)
    if category == "brickwork" and measure_type == "volume":
        return "brickwork_wall"

    # Stone masonry – same as brick, if needed
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

    # Default
    return "volume"


def _guess_discipline(category: str, code: str) -> str:
    """
    Rough discipline split: 'civil' vs 'electrical' vs 'plumbing' vs 'fire' vs 'hvac'.
    """
    category = category.lower()
    code = code.strip()

    if category.startswith("electrical"):
        return "electrical"
    if category in ("pipes", "sanitary", "cp_fittings"):
        return "plumbing"
    if category in ("fire_alarm",):
        return "electrical"  # fire alarm is usually under electrical contract
    # Most others: civil
    return "civil"


# =============================================================================
# Generic CSV loader
# =============================================================================

def _load_dsr_csv(csv_name: str, default_discipline: str) -> Dict[str, Dict[str, Any]]:
    """
    Load a DSR/SoR CSV from data/ folder.

    Supports TWO styles:

    1) RAW 5-column CPWD/SoR format:
        S.No, DSR Code, Description, Unit, Rate
       → we derive:
        item_key, category, type, measurement_rule, discipline

    2) Enriched format with explicit columns:
        item_key, code, description, unit, rate,
        category, type, measurement_rule, discipline

    Returns a dict:
        { item_key: {code, description, unit, rate,
                     category, type, measurement_rule, discipline} }
    """
    path = DATA_DIR / csv_name
    if not path.exists():
        # Optional source – simply return empty
        return {}

    df = pd.read_csv(path)
    cols_lower = {c.lower().strip(): c for c in df.columns}

    # Enriched case: has item_key column
    if "item_key" in cols_lower:
        key_col = cols_lower["item_key"]
        code_col = cols_lower.get("code")
        desc_col = cols_lower.get("description")
        unit_col = cols_lower.get("unit")
        rate_col = cols_lower.get("rate")
        cat_col = cols_lower.get("category")
        type_col = cols_lower.get("type")
        rule_col = cols_lower.get("measurement_rule")
        disc_col = cols_lower.get("discipline")

        items: Dict[str, Dict[str, Any]] = {}
        for _, row in df.iterrows():
            item_key = str(row[key_col]).strip()
            if not item_key:
                continue
            code = str(row[code_col]).strip() if code_col else ""
            desc = str(row[desc_col]).strip() if desc_col else ""
            unit = str(row[unit_col]).strip() if unit_col else ""
            rate = float(row[rate_col]) if rate_col else 0.0

            category = str(row[cat_col]).strip() if cat_col else _guess_category(code, desc)
            mtype = str(row[type_col]).strip() if type_col else _guess_type(unit)
            mrule = str(row[rule_col]).strip() if rule_col else _guess_measurement_rule(code, category, mtype)
            disc = str(row[disc_col]).strip() if disc_col else _guess_discipline(category, code)

            items[item_key] = {
                "code": code,
                "description": desc,
                "unit": unit,
                "rate": rate,
                "category": category,
                "type": mtype,
                "measurement_rule": mrule,
                "discipline": disc or default_discipline,
            }
        return items

    # RAW CPWD-style case: 5 columns
    code_col = cols_lower.get("dsr code", cols_lower.get("code"))
    desc_col = cols_lower.get("description")
    unit_col = cols_lower.get("unit")
    rate_col = cols_lower.get("rate")

    if not code_col or not desc_col or not unit_col or not rate_col:
        raise ValueError(
            f"{csv_name} must contain either 'item_key' or at least "
            "'DSR Code', 'Description', 'Unit', 'Rate'. Found: {list(df.columns)}"
        )

    items: Dict[str, Dict[str, Any]] = {}
    for _, row in df.iterrows():
        code = str(row[code_col]).strip()
        desc = str(row[desc_col]).strip()
        unit = str(row[unit_col]).strip()
        rate = float(row[rate_col])

        if not code or not desc:
            continue

        item_key = f"{desc} ({code})"

        category = _guess_category(code, desc)
        mtype = _guess_type(unit)
        mrule = _guess_measurement_rule(code, category, mtype)
        disc = _guess_discipline(category, code)

        items[item_key] = {
            "code": code,
            "description": desc,
            "unit": unit,
            "rate": rate,
            "category": category,
            "type": mtype,
            "measurement_rule": mrule,
            "discipline": disc or default_discipline,
        }

    return items


# =============================================================================
# Load all available sources
# =============================================================================

# CPWD – Civil + Electrical
CPWD_DSR_CIVIL_2023: Dict[str, Dict[str, Any]] = _load_dsr_csv(
    "cpwd_dsr_civil_2023.csv", default_discipline="civil"
)
CPWD_DSR_ELECT_2023: Dict[str, Dict[str, Any]] = _load_dsr_csv(
    "cpwd_dsr_elect_2023.csv", default_discipline="electrical"
)

CPWD_ALL_2023: Dict[str, Dict[str, Any]] = {
    **CPWD_DSR_CIVIL_2023,
    **CPWD_DSR_ELECT_2023,
}

# OPTIONAL: State SoR (Civil + Electrical) – only used if CSVs exist
STATE_SOR_CIVIL_2023: Dict[str, Dict[str, Any]] = _load_dsr_csv(
    "state_sor_civil_2023.csv", default_discipline="civil"
)
STATE_SOR_ELECT_2023: Dict[str, Dict[str, Any]] = _load_dsr_csv(
    "state_sor_elect_2023.csv", default_discipline="electrical"
)

STATE_SOR_ALL_2023: Dict[str, Dict[str, Any]] = {
    **STATE_SOR_CIVIL_2023,
    **STATE_SOR_ELECT_2023,
} if STATE_SOR_CIVIL_2023 or STATE_SOR_ELECT_2023 else {}


# RATE SOURCES – master datasets keyed by name
RATE_SOURCES: Dict[str, Dict[str, Dict[str, Any]]] = {
    "CPWD DSR 2023 (Civil + Elect)": CPWD_ALL_2023,
}
if STATE_SOR_ALL_2023:
    RATE_SOURCES["State SoR 2023 (Civil + Elect)"] = STATE_SOR_ALL_2023


# DEFAULT SOURCE – used everywhere in app unless you add a selector
CPWD_BASE_DSR_2023: Dict[str, Dict[str, Any]] = CPWD_ALL_2023

# Build Item objects for CPWD base source
ITEMS: Dict[str, Item] = {
    key: Item.from_dsr_record(key, rec)
    for key, rec in CPWD_BASE_DSR_2023.items()
}


# =============================================================================
# PHASE GROUPS – for SOQ UI (use item_key strings)
# =============================================================================

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

# Filter PHASE_GROUPS to only include keys that actually exist in DSR
for phase, keys in list(PHASE_GROUPS.items()):
    PHASE_GROUPS[phase] = [k for k in keys if k in CPWD_BASE_DSR_2023]
