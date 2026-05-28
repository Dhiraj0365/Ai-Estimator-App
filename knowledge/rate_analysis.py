# knowledge/rate_analysis.py
"""
Rate Analysis Engine for CPWD / PWD style estimates.

This module defines:
- Data structures for rate analysis entries
- A small sample library of rate analyses (per unit of parent item)
- A compute_rate_analysis(...) function which:
  * prices materials using ITEMS and cost index
  * prices labour & plant using standard daywork rates
  * returns a full per-unit breakdown and totals

NOTE:
- All quantities below are EXAMPLE values; tune them against
  CPWD "Analysis of Rates" or your state's AoR.
- item_key values must exist in knowledge.dsr_master.ITEMS,
  or you can supply rate_override instead.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict, Optional, Any

from knowledge.dsr_master import ITEMS
from core.models import Item


# ---------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------


@dataclass
class MaterialComponent:
    """
    One material component in rate analysis per unit of parent item.

    qty_per_unit: quantity of this material required per 1 unit of
                  the parent DSR item (e.g. per 1 m³ RCC).
    item_key: key in ITEMS representing this material, e.g. "MAT_CEMENT_BAG".
              If None, rate_override must be supplied.
    rate_override: if not None, use this ₹/unit rate instead of looking up
                   ITEMS[item_key].rate_at_index(...).
    display_name: optional human-readable name (else taken from Item).
    unit: optional unit override for display (else from Item).
    """
    qty_per_unit: float
    item_key: Optional[str] = None
    rate_override: Optional[float] = None
    display_name: Optional[str] = None
    unit: Optional[str] = None

    def resolve_item(self) -> Optional[Item]:
        if self.item_key and self.item_key in ITEMS:
            return ITEMS[self.item_key]
        return None


@dataclass
class LabourComponent:
    """Labour component per unit of parent item."""
    role: str                 # e.g. "Mason"
    mandays_per_unit: float   # mandays needed per 1 unit


@dataclass
class PlantComponent:
    """Plant / equipment component per unit of parent item."""
    equipment: str            # e.g. "ConcreteMixer_0.2m3"
    hours_per_unit: float     # machine hours per 1 unit


@dataclass
class RateAnalysisEntry:
    """
    Full rate analysis for a DSR item (per unit).

    code: DSR code of the parent item, e.g. "5.22.1".
    description: human description.
    parent_unit: unit of the parent item (m3, m2, etc.).
    materials/labour/plant: lists of components per unit.
    reference: text reference to AoR / specs.
    """
    code: str
    description: str
    parent_unit: str
    materials: List[MaterialComponent]
    labour: List[LabourComponent]
    plant: List[PlantComponent]
    reference: str


# ---------------------------------------------------------------------
# Labour & plant base rates (₹ / manday or ₹ / hour)
# Adjust these to your department's standard daywork rates.
# ---------------------------------------------------------------------

LABOUR_RATES: Dict[str, float] = {
    "Mason": 800.0,          # ₹ / manday (example)
    "Mazdoor": 600.0,
    "BarBender": 850.0,
    "Carpenter": 850.0,
    "Painter": 800.0,
}

PLANT_RATES: Dict[str, float] = {
    "ConcreteMixer_0.2m3": 450.0,  # ₹ / hour
    "Vibrator": 150.0,
    "Crane_Small": 1500.0,
}


# ---------------------------------------------------------------------
# Sample rate analysis library – keyed by DSR CODE of PARENT item
# YOU MUST ALIGN codes with your actual DSR.
# ---------------------------------------------------------------------

RATE_ANALYSIS_BY_CODE: Dict[str, RateAnalysisEntry] = {

    # RCC M20 in beams/slabs etc. per 1 m3 of RCC
    # Example only – adjust quantities as per AoR.
    "5.22.1": RateAnalysisEntry(
        code="5.22.1",
        description="RCC work M20 in beams, suspended floors, roofs etc.",
        parent_unit="m3",
        materials=[
            MaterialComponent(
                qty_per_unit=7.0,
                item_key="MAT_CEMENT_BAG",
                display_name="Cement (bags)",
                unit="bag",
            ),
            MaterialComponent(
                qty_per_unit=0.44,
                item_key="MAT_SAND_M3",
                display_name="Sand",
                unit="m3",
            ),
            MaterialComponent(
                qty_per_unit=0.88,
                item_key="MAT_AGGREGATE_M3",
                display_name="Coarse aggregate",
                unit="m3",
            ),
            MaterialComponent(
                qty_per_unit=100.0,             # kg steel per m3 RCC – example
                item_key="STEEL_REINF_FE500",
                display_name="Reinforcement steel (Fe500)",
                unit="kg",
            ),
        ],
        labour=[
            LabourComponent("Mason", 0.25),
            LabourComponent("Mazdoor", 0.75),
            LabourComponent("BarBender", 0.20),
        ],
        plant=[
            PlantComponent("ConcreteMixer_0.2m3", 0.30),
            PlantComponent("Vibrator", 0.30),
        ],
        reference="CPWD AoR 2023 – RCC M20; IS 456:2000",
    ),

    # Brickwork in superstructure 230mm 1:6, per 1 m3
    "6.4.2": RateAnalysisEntry(
        code="6.4.2",
        description="Brick work in superstructure in cement mortar 1:6, 230mm thick",
        parent_unit="m3",
        materials=[
            MaterialComponent(
                qty_per_unit=500.0,
                item_key="MAT_BRICK_FPS",
                display_name="Bricks (FPS)",
                unit="nos",
            ),
            MaterialComponent(
                qty_per_unit=1.0,               # bag per m3 – example
                item_key="MAT_CEMENT_BAG",
                display_name="Cement (bags)",
                unit="bag",
            ),
            MaterialComponent(
                qty_per_unit=0.24,
                item_key="MAT_SAND_M3",
                display_name="Sand",
                unit="m3",
            ),
        ],
        labour=[
            LabourComponent("Mason", 0.35),
            LabourComponent("Mazdoor", 1.00),
        ],
        plant=[],
        reference="CPWD AoR 2023 – Brickwork; IS 2212",
    ),

    # 12mm plaster in 1:6, per 1 m2
    "13.4.1": RateAnalysisEntry(
        code="13.4.1",
        description="12mm cement plaster in 1:6 on brick/RCC, single coat",
        parent_unit="m2",
        materials=[
            MaterialComponent(
                qty_per_unit=0.09,             # bag/m2 – example
                item_key="MAT_CEMENT_BAG",
                display_name="Cement (bags)",
                unit="bag",
            ),
            MaterialComponent(
                qty_per_unit=0.003,            # m3/m2 – example
                item_key="MAT_SAND_M3",
                display_name="Sand",
                unit="m3",
            ),
        ],
        labour=[
            LabourComponent("Mason", 0.10),
            LabourComponent("Mazdoor", 0.20),
        ],
        plant=[],
        reference="CPWD AoR 2023 – Plaster; IS 1661",
    ),

    # Vitrified floor tiles in mortar, per 1 m2
    "11.41.2": RateAnalysisEntry(
        code="11.41.2",
        description="Vitrified floor tiles in cement mortar, 600×600mm",
        parent_unit="m2",
        materials=[
            MaterialComponent(
                qty_per_unit=1.05,             # including wastage
                item_key="MAT_TILE_VITRIFIED_M2",
                display_name="Vitrified tiles",
                unit="m2",
            ),
            MaterialComponent(
                qty_per_unit=0.08,             # bag/m2 – example
                item_key="MAT_CEMENT_BAG",
                display_name="Cement (bags)",
                unit="bag",
            ),
            MaterialComponent(
                qty_per_unit=0.002,            # m3/m2 – example
                item_key="MAT_SAND_M3",
                display_name="Sand",
                unit="m3",
            ),
        ],
        labour=[
            LabourComponent("Mason", 0.12),
            LabourComponent("Mazdoor", 0.18),
        ],
        plant=[],
        reference="CPWD AoR 2023 – Flooring; IS 1443",
    ),
}

RA_CODES = set(RATE_ANALYSIS_BY_CODE.keys())


# ---------------------------------------------------------------------
# Computation function
# ---------------------------------------------------------------------


def compute_rate_analysis(
    code: str,
    cost_index: float,
) -> Optional[Dict[str, Any]]:
    """
    Compute per-unit rate analysis for the DSR item with given code.

    Returns a dict with:
      - "materials": list of rows {name, unit, qty_per_unit, rate, amount}
      - "labour": list of rows {role, mandays_per_unit, rate, amount}
      - "plant": list of rows {equipment, hours_per_unit, rate, amount}
      - "total_material", "total_labour", "total_plant", "total_per_unit"
      - "entry": the RateAnalysisEntry itself

    If no entry found, returns None.
    """
    entry = RATE_ANALYSIS_BY_CODE.get(code)
    if not entry:
        return None

    # MATERIALS
    material_rows = []
    total_material = 0.0

    for comp in entry.materials:
        item = comp.resolve_item()
        if item is not None:
            rate = item.rate_at_index(cost_index)
            name = comp.display_name or item.description
            unit = comp.unit or item.unit
        else:
            rate = comp.rate_override or 0.0
            name = comp.display_name or (comp.item_key or "Material")
            unit = comp.unit or ""

        amount = comp.qty_per_unit * rate
        total_material += amount

        material_rows.append(
            {
                "name": name,
                "unit": unit,
                "qty_per_unit": comp.qty_per_unit,
                "rate": rate,
                "amount": amount,
            }
        )

    # LABOUR
    labour_rows = []
    total_labour = 0.0

    for lab in entry.labour:
        rate = LABOUR_RATES.get(lab.role, 0.0)
        amount = lab.mandays_per_unit * rate
        total_labour += amount

        labour_rows.append(
            {
                "role": lab.role,
                "mandays_per_unit": lab.mandays_per_unit,
                "rate": rate,
                "amount": amount,
            }
        )

    # PLANT
    plant_rows = []
    total_plant = 0.0

    for pl in entry.plant:
        rate = PLANT_RATES.get(pl.equipment, 0.0)
        amount = pl.hours_per_unit * rate
        total_plant += amount

        plant_rows.append(
            {
                "equipment": pl.equipment,
                "hours_per_unit": pl.hours_per_unit,
                "rate": rate,
                "amount": amount,
            }
        )

    total_per_unit = total_material + total_labour + total_plant

    return {
        "entry": entry,
        "materials": material_rows,
        "labour": labour_rows,
        "plant": plant_rows,
        "total_material": total_material,
        "total_labour": total_labour,
        "total_plant": total_plant,
        "total_per_unit": total_per_unit,
    }
