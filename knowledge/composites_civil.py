from __future__ import annotations

"""
Civil Work Packages (Composites) – CPWD DSR 2023

This module defines *work packages* for common civil operations, built on
top of:

- knowledge.dsr_master   → CPWD_BASE_DSR_2023, ITEMS
- engines.is1200_civil   → IS1200Engine (IS 1200 measurement rules)
- core.models            → Item, BOQLine

Each package groups several DSR items (excavation, PCC, concrete,
brickwork, plaster, tiles, paint, etc.) into a **single logical unit**
like:

- "Site clearance & topsoil stripping"
- "Bulk earthworks (cut & fill)"
- "Isolated footing (excavation + PCC + RCC + formwork + backfill)"
- "Brick wall + plaster"
- "Floor tiles"
- "Painting"

Usage pattern (UI-agnostic):

    from knowledge.composites_civil import WORK_PACKAGES_CIVIL, expand_work_package

    context = {
        "L_foot": 2.0,
        "B_foot": 2.0,
        "D_foot": 0.5,
        "L_exc": 2.4,
        "B_exc": 2.4,
        "D_exc": 0.7,
        "L_blind": 2.2,
        "B_blind": 2.2,
        "t_blind": 0.05,
        "backfill_volume_cum": 4.0,
    }

    lines = expand_work_package(
        package_name="Isolated footing (excavation + PCC + concrete + formwork + backfill)",
        context=context,
        phase="1️⃣ SUBSTRUCTURE",
        cost_index=110.0,
    )

    # 'lines' is a list[BOQLine]; the caller can assign IDs and add to a Project or SOQ.

Note:
- Quantity expressions use Python `eval` over a safe environment that
  includes: context variables, IS1200Engine, and basic math functions.
- If a DSR item_key referenced in a package is NOT present in
  CPWD_BASE_DSR_2023, that component is silently skipped (so you can
  add/adjust your CSV without breaking everything).
"""

from dataclasses import dataclass
from typing import List, Dict, Any, Optional

from engines.is1200_civil import IS1200Engine
from knowledge.dsr_master import CPWD_BASE_DSR_2023, ITEMS
from core.models import Item, BOQLine


# =============================================================================
# Data structures
# =============================================================================

@dataclass
class ComponentLine:
    """
    One component of a work package.

    Attributes
    ----------
    role        : str  - logical role, e.g. "excavation", "pcc", "rcc_concrete",
                         "formwork", "backfill", "brickwork", "plaster", etc.
    item_key    : str  - key into CPWD_BASE_DSR_2023 / ITEMS
    quantity_expr : str - Python expression evaluated with a context dict and
                          helpers (IS1200Engine, max, min, etc.) to produce
                          a *net* quantity (float) in the DSR unit.
    notes       : str  - engineering/audit notes (go into BOQLine.notes).
    """

    role: str
    item_key: str
    quantity_expr: str
    notes: str = ""


@dataclass
class WorkPackage:
    """
    Logical civil work package (e.g., isolated footing, site clearance).

    Attributes
    ----------
    name          : str   - user-facing name (used as key in WORK_PACKAGES_CIVIL).
    section       : str   - high-level WBS section (e.g. "Earthworks & Foundations").
    default_phase : str   - default phase label for BOQ ("1️⃣ SUBSTRUCTURE", etc.).
    description   : str   - summary of what the package covers.
    components    : list[ComponentLine] - child DSR items and quantity rules.
    """

    name: str
    section: str
    default_phase: str
    description: str
    components: List[ComponentLine]


# =============================================================================
# Helper: safe eval environment
# =============================================================================

def _build_eval_env(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build an evaluation environment for quantity expressions.

    Includes:
    - All context keys/values.
    - IS1200Engine
    - Basic Python math functions.
    """
    env: Dict[str, Any] = {}
    env.update(context)
    env.update(
        {
            "IS1200Engine": IS1200Engine,
            "max": max,
            "min": min,
            "abs": abs,
            "round": round,
        }
    )
    try:  # optional math
        import math

        env["math"] = math
    except ImportError:
        pass
    return env


# =============================================================================
# WORK PACKAGES – EARTHWORKS, FOUNDATIONS, BASIC SUPERSTRUCTURE & FINISH
# =============================================================================
#
# IMPORTANT:
# item_key strings MUST match keys generated in CPWD_BASE_DSR_2023, which
# are of the form: "Description (DSR Code)" as loaded from your CSV.
#
# For simplicity, we use the "short" descriptions from the later part of
# your dataset (around ids 1040+), e.g.:
#
#   "Earthwork excavation foundation trench (2.8.1)"
#   "Surface excavation 30cm depth all soil (2.1.1)"
#   "PCC 1:5:10 foundation base (3.1.1)"
#   "Brickwork FB non modular foundation (4.1.1)"
#   "RR masonry foundation uncoursed (5.1.1)"
#   "12mm cement plaster 1:6 fair face (6.1.1)"
#   "Premium acrylic emulsion painting (10.1.1)"
#   "Vitrified floor tiles 600x600mm (12.1.1)"
#
# Make sure your CSV has these descriptions exactly, or adjust the keys below.


# 1) SITE CLEARANCE & TOPSOIL STRIPPING
SITE_CLEARANCE_PACKAGE = WorkPackage(
    name="Site clearance & topsoil stripping",
    section="Earthworks & Foundations",
    default_phase="1️⃣ SUBSTRUCTURE",
    description="Clearing jungle/vegetation and stripping topsoil (surface excavation) for the building footprint.",
    components=[
        # Clearing jungle / vegetation
        ComponentLine(
            role="clearing",
            item_key="Clearing jungle rank vegetation (2.31)",
            quantity_expr="site_area_sqm",  # DSR in sqm
            notes="Clearing jungle including uprooting of rank vegetation, grass, brushwood."
        ),
        # Topsoil stripping (surface excavation 30cm)
        ComponentLine(
            role="topsoil_stripping",
            item_key="Surface excavation 30cm depth all soil (2.1.1)",
            quantity_expr="site_area_sqm",  # DSR is per sqm, depth built-in
            notes="Topsoil/surface excavation up to 0.30 m depth."
        ),
    ],
)


# 2) BULK EARTHWORKS (CUT & FILL TO FORMATION LEVEL)
BULK_EARTHWORKS_PACKAGE = WorkPackage(
    name="Bulk earthworks (cut & fill to formation)",
    section="Earthworks & Foundations",
    default_phase="1️⃣ SUBSTRUCTURE",
    description="Bulk cut & fill to form building platform, including filling with excavated earth.",
    components=[
        # CUT – large-area excavation
        ComponentLine(
            role="cut",
            item_key="Excavation mechanical all soil areas (2.6.1)",
            quantity_expr="cut_volume_cum",  # in m³
            notes="Bulk excavation over areas by mechanical means."
        ),
        # FILL – filling with available excavated earth
        ComponentLine(
            role="fill_with_excavated_earth",
            item_key="Filling excavated earth trenches (2.25)",
            quantity_expr="fill_volume_cum",
            notes="Filling with available excavated earth in layers, in plinth / around foundations."
        ),
    ],
)


# 3) ISOLATED FOOTING (EXCAVATION + PCC + CONCRETE + FORMWORK + BACKFILL)
ISOLATED_FOOTING_PACKAGE = WorkPackage(
    name="Isolated footing (excavation + PCC + concrete + formwork + backfill)",
    section="Earthworks & Foundations",
    default_phase="1️⃣ SUBSTRUCTURE",
    description="Complete cycle for one isolated footing: pit excavation, PCC blinding, footing concrete, formwork, and backfilling.",
    components=[
        # Excavation (pit)
        ComponentLine(
            role="excavation",
            item_key="Earthwork excavation foundation trench (2.8.1)",
            quantity_expr="IS1200Engine.pit_excavation(L_exc, B_exc, D_exc)['net']",
            notes="Excavation in foundation trenches/pits as per IS 1200; includes getting out soil and disposal within specified lead."
        ),
        # PCC blinding
        ComponentLine(
            role="pcc_blinding",
            item_key="PCC 1:5:10 foundation base (3.1.1)",
            quantity_expr="L_blind * B_blind * t_blind",
            notes="Plain cement concrete 1:5:10 as levelling course under footing."
        ),
        # Footing concrete – here using a higher grade cement concrete (user may change item_key to exact RCC item)
        ComponentLine(
            role="concrete_footing",
            item_key="PCC M20 grade nominal mix (3.5.1)",
            quantity_expr="L_foot * B_foot * D_foot",
            notes="Footing concrete volume; replace with exact RCC item if available in DSR."
        ),
        # Formwork to footing sides
        ComponentLine(
            role="formwork",
            item_key="Formwork for plain surfaces (3.10.1)",
            quantity_expr="IS1200Engine.formwork_column_area(L_foot, B_foot, D_foot)",
            notes="Approximate shuttering to vertical sides of footing."
        ),
        # Backfilling around footing
        ComponentLine(
            role="backfill",
            item_key="Filling excavated earth trenches (2.25)",
            quantity_expr="backfill_volume_cum",
            notes="Filling with excavated earth in layers, watered and rammed."
        ),
    ],
)


# 4) BRICK WALL (PLINTH / SUPERSTRUCTURE) + INTERNAL PLASTER
BRICKWALL_PLASTER_PACKAGE = WorkPackage(
    name="Brick wall with plaster (one side)",
    section="Superstructure",
    default_phase="3️⃣ SUPERSTRUCTURE",
    description="Brick masonry wall with 12 mm plaster on one face.",
    components=[
        # Brickwork volume: L * t * H
        ComponentLine(
            role="brickwork",
            item_key="Brickwork superstructure FB bricks (4.1.2)",  # superstructure brickwork
            quantity_expr="L_wall * t_wall * H_wall",
            notes="Brickwork in superstructure; thickness in metres (e.g., 0.23 for 230mm)."
        ),
        # Plaster on one side (L * H)
        ComponentLine(
            role="plaster_one_side",
            item_key="12mm cement plaster 1:6 fair face (6.1.1)",
            quantity_expr="L_wall * H_wall",
            notes="12 mm cement-sand plaster on one face of wall."
        ),
    ],
)


# 5) FLOOR TILING – VITRIFIED TILES
FLOOR_TILES_PACKAGE = WorkPackage(
    name="Vitrified floor tiles 600x600mm (with 3% wastage)",
    section="Finishing",
    default_phase="4️⃣ FINISHING",
    description="Floor tiling in vitrified tiles 600x600mm, including 3% wastage.",
    components=[
        ComponentLine(
            role="floor_tiling",
            item_key="Vitrified floor tiles 600x600mm (12.1.1)",
            # Use IS1200Engine.floor_area_with_wastage: returns dict
            quantity_expr="IS1200Engine.floor_area_with_wastage(L_room, B_room, wastage_factor)['net']",
            notes="Vitrified tiles including 3% wastage; L_room & B_room in m, wastage_factor e.g. 1.03."
        ),
    ],
)


# 6) WALL PAINTING – INTERNAL EMULSION
INTERNAL_PAINTING_PACKAGE = WorkPackage(
    name="Internal wall painting (putty + acrylic emulsion)",
    section="Finishing",
    default_phase="4️⃣ FINISHING",
    description="Internal wall system: putty + acrylic emulsion paint, both sides of wall.",
    components=[
        # Putty (use 10.5.1 Wall care putty)
        ComponentLine(
            role="putty",
            item_key="Wall care putty painting prep (10.5.1)",
            quantity_expr="IS1200Engine.wall_finish_area(L_wall, H_wall, sides)['net']",
            notes="Wall care putty on both sides; sides usually 2 for a partition."
        ),
        # Acrylic emulsion paint
        ComponentLine(
            role="acrylic_paint",
            item_key="Premium acrylic emulsion painting (10.1.1)",
            quantity_expr="IS1200Engine.wall_finish_area(L_wall, H_wall, sides)['net']",
            notes="Premium acrylic emulsion on prepared wall surfaces."
        ),
    ],
)


WORK_PACKAGES_CIVIL: Dict[str, WorkPackage] = {
    SITE_CLEARANCE_PACKAGE.name: SITE_CLEARANCE_PACKAGE,
    BULK_EARTHWORKS_PACKAGE.name: BULK_EARTHWORKS_PACKAGE,
    ISOLATED_FOOTING_PACKAGE.name: ISOLATED_FOOTING_PACKAGE,
    BRICKWALL_PLASTER_PACKAGE.name: BRICKWALL_PLASTER_PACKAGE,
    FLOOR_TILES_PACKAGE.name: FLOOR_TILES_PACKAGE,
    INTERNAL_PAINTING_PACKAGE.name: INTERNAL_PAINTING_PACKAGE,
}


# =============================================================================
# EXPANSION FUNCTION – convert a WorkPackage into BOQLines
# =============================================================================

def expand_work_package(
    package_name: str,
    context: Dict[str, Any],
    phase: Optional[str],
    cost_index: float,
) -> List[BOQLine]:
    """
    Expand a work package into BOQLine objects.

    Parameters
    ----------
    package_name : str
        Key in WORK_PACKAGES_CIVIL.
    context : dict
        Dictionary of geometric/other inputs used in quantity_expr:
        Examples for different packages:

        - Site clearance:
            {"site_area_sqm": 500.0}

        - Bulk earthworks:
            {"cut_volume_cum": 300.0, "fill_volume_cum": 200.0}

        - Isolated footing:
            {
              "L_exc": 2.4, "B_exc": 2.4, "D_exc": 0.7,
              "L_blind": 2.2, "B_blind": 2.2, "t_blind": 0.05,
              "L_foot": 2.0, "B_foot": 2.0, "D_foot": 0.5,
              "backfill_volume_cum": 3.0
            }

        - Brick wall + plaster:
            {"L_wall": 4.0, "H_wall": 3.0, "t_wall": 0.23}

        - Floor tiles:
            {"L_room": 5.0, "B_room": 4.0, "wastage_factor": 1.03}

        - Painting:
            {"L_wall": 5.0, "H_wall": 3.0, "sides": 2}

    phase : str or None
        BOQ phase label. If None, package.default_phase is used.
    cost_index : float
        Location cost index, e.g. 100.0 for base, 110.0 for 10% higher.

    Returns
    -------
    list[BOQLine]
        BOQLine entries with id=0 (caller should assign IDs).
    """
    if package_name not in WORK_PACKAGES_CIVIL:
        raise KeyError(f"Unknown work package: {package_name}")

    pkg = WORK_PACKAGES_CIVIL[package_name]
    eff_phase = phase or pkg.default_phase
    env = _build_eval_env(context)
    lines: List[BOQLine] = []

    for comp in pkg.components:
        # Check if DSR item exists
        if comp.item_key not in ITEMS:
            # Item not present; skip silently to avoid breaking estimates
            continue

        item: Item = ITEMS[comp.item_key]

        # Evaluate quantity expression
        try:
            qty_val = eval(comp.quantity_expr, {}, env)
        except Exception:
            # Skip this component if evaluation fails; caller can log separately
            continue

        try:
            qty = float(qty_val)
        except (TypeError, ValueError):
            continue

        if qty <= 0.0:
            continue

        # Simple pricing: location index only (contingency/overheads/profit can be added later)
        rate = item.rate_at_index(cost_index)
        amount = qty * rate

        # Try to infer basic geometry (non-critical; for MB, etc.)
        length = float(
            context.get(
                "L_wall",
                context.get("L_foot", context.get("L_room", context.get("L", 0.0))),
            )
        )
        breadth = float(
            context.get(
                "B_wall",
                context.get("B_foot", context.get("B_room", context.get("B", 0.0))),
            )
        )
        depth = float(
            context.get(
                "D_foot", context.get("D_exc", context.get("D", 0.0))
            )
        )
        height = float(
            context.get(
                "H_wall", context.get("H", 0.0)
            )
        )

        meta = {
            "package_name": pkg.name,
            "component_role": comp.role,
        }

        line = BOQLine.from_item(
            line_id=0,  # caller should assign an actual ID
            item=item,
            phase=eff_phase,
            quantity=qty,
            rate=rate,
            amount=amount,
            source=f"package: {pkg.name}",
            notes=comp.notes,
            length=length,
            breadth=breadth,
            depth=depth,
            height=height,
            meta=meta,
        )
        lines.append(line)

    return lines
```
