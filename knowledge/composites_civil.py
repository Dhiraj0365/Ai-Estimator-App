# knowledge/composites_civil.py

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
- "Isolated footing (excavation + PCC + concrete + formwork + backfill)"
- "Brick wall with plaster"
- "Floor tiles"
- "Painting"
- "RCC columns / beams / slabs"

Usage (UI-agnostic):

    from knowledge.composites_civil import WORK_PACKAGES_CIVIL, expand_work_package

    context = {...}
    lines = expand_work_package(
        package_name="Isolated footing (excavation + PCC + concrete + formwork + backfill)",
        context=context,
        phase="1️⃣ SUBSTRUCTURE",
        cost_index=110.0,
    )

    # 'lines' is a list[BOQLine]; caller assigns IDs and attaches to Project/SOQ.
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
    Logical civil work package (e.g., isolated footing, RCC columns).

    Attributes
    ----------
    name          : str   - user-facing name.
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
    try:
        import math
        env["math"] = math
    except ImportError:
        pass
    return env


# =============================================================================
# WORK PACKAGES – EARTHWORKS, FOUNDATIONS, SUPERSTRUCTURE & FINISHES
# =============================================================================
#
# IMPORTANT:
# item_key strings MUST match keys generated in CPWD_BASE_DSR_2023, which
# are of the form: "Description (DSR Code)" as loaded from your CSV.
#
# For simplicity, we use the short descriptions from your civil CSV, e.g.:
#   "Earthwork excavation foundation trench (2.8.1)"
#   "Surface excavation 30cm depth all soil (2.1.1)"
#   "PCC 1:5:10 foundation base (3.1.1)"
#   "PCC M20 grade nominal mix (3.5.1)"
#   "PCC M25 grade nominal mix (3.6.1)"
#   "Formwork for sides of columns (3.10.3)"
#   "Formwork for sides of beams (3.10.2)"
#   "Formwork for bottom of slabs (3.10.5)"
#   "Steel reinforcement for R.C.C. work Fe500 (5.0.1)"
#   etc.
# Ensure your CSV descriptions match these exactly.


# 1) SITE CLEARANCE & TOPSOIL STRIPPING
SITE_CLEARANCE_PACKAGE = WorkPackage(
    name="Site clearance & topsoil stripping",
    section="Earthworks & Foundations",
    default_phase="1️⃣ SUBSTRUCTURE",
    description="Clearing jungle/vegetation and stripping topsoil (surface excavation) for the building footprint.",
    components=[
        ComponentLine(
            role="clearing",
            item_key="Clearing jungle rank vegetation (2.31)",
            quantity_expr="site_area_sqm",  # DSR in sqm
            notes="Clearing jungle including uprooting of rank vegetation, grass, brushwood."
        ),
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
        ComponentLine(
            role="cut",
            item_key="Excavation mechanical all soil areas (2.6.1)",
            quantity_expr="cut_volume_cum",  # in m³
            notes="Bulk excavation over areas by mechanical means."
        ),
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
        ComponentLine(
            role="excavation",
            item_key="Earthwork excavation foundation trench (2.8.1)",
            quantity_expr="IS1200Engine.pit_excavation(L_exc, B_exc, D_exc)['net']",
            notes="Excavation in foundation trenches/pits as per IS 1200; includes getting out soil and disposal within specified lead."
        ),
        ComponentLine(
            role="pcc_blinding",
            item_key="PCC 1:5:10 foundation base (3.1.1)",
            quantity_expr="L_blind * B_blind * t_blind",
            notes="Plain cement concrete 1:5:10 as levelling course under footing."
        ),
        ComponentLine(
            role="concrete_footing",
            item_key="PCC M20 grade nominal mix (3.5.1)",
            quantity_expr="L_foot * B_foot * D_foot",
            notes="Footing concrete volume; using M20 grade as RCC concrete item."
        ),
        ComponentLine(
            role="formwork",
            item_key="Formwork for plain surfaces (3.10.1)",
            quantity_expr="IS1200Engine.formwork_column_area(L_foot, B_foot, D_foot)",
            notes="Approximate shuttering to vertical sides of footing."
        ),
        ComponentLine(
            role="backfill",
            item_key="Filling excavated earth trenches (2.25)",
            quantity_expr="backfill_volume_cum",
            notes="Backfilling with excavated soil in layers and compaction."
        ),
    ],
)


# 4) RCC COLUMNS (CONCRETE + STEEL + FORMWORK)
RCC_COLUMNS_PACKAGE = WorkPackage(
    name="RCC columns (concrete + steel + formwork, per floor)",
    section="Superstructure",
    default_phase="3️⃣ SUPERSTRUCTURE",
    description="RCC columns for one floor including concrete, reinforcement and formwork.",
    components=[
        ComponentLine(
            role="column_concrete",
            item_key="PCC M25 grade nominal mix (3.6.1)",
            quantity_expr="b_col * d_col * h_col * n_cols",
            notes="RCC column concrete volume (treat 3.6.1 as structural M25 concrete)."
        ),
        ComponentLine(
            role="column_reinforcement",
            item_key="Steel reinforcement for R.C.C. work Fe500 (5.0.1)",
            quantity_expr="IS1200Engine.steel_from_kg_per_cum(b_col * d_col * h_col * n_cols, steel_kg_per_cum_col)['net']",
            notes="Column reinforcement based on kg/m³ assumption (default ~160 kg/m³)."
        ),
        ComponentLine(
            role="column_formwork",
            item_key="Formwork for sides of columns (3.10.3)",
            quantity_expr="IS1200Engine.formwork_column_area(b_col, d_col, h_col) * n_cols",
            notes="Formwork to all faces of RCC columns."
        ),
    ],
)


# 5) RCC BEAMS (CONCRETE + STEEL + FORMWORK)
RCC_BEAMS_PACKAGE = WorkPackage(
    name="RCC beams (concrete + steel + formwork, per floor)",
    section="Superstructure",
    default_phase="3️⃣ SUPERSTRUCTURE",
    description="RCC beams for one floor including concrete, reinforcement and formwork.",
    components=[
        ComponentLine(
            role="beam_concrete",
            item_key="PCC M25 grade nominal mix (3.6.1)",
            quantity_expr="L_beam * b_beam * d_beam * n_beams",
            notes="RCC beam concrete volume (treat 3.6.1 as structural M25 concrete)."
        ),
        ComponentLine(
            role="beam_reinforcement",
            item_key="Steel reinforcement for R.C.C. work Fe500 (5.0.1)",
            quantity_expr="IS1200Engine.steel_from_kg_per_cum(L_beam * b_beam * d_beam * n_beams, steel_kg_per_cum_beam)['net']",
            notes="Beam reinforcement based on kg/m³ assumption (default ~120 kg/m³)."
        ),
        ComponentLine(
            role="beam_formwork",
            item_key="Formwork for sides of beams (3.10.2)",
            quantity_expr="IS1200Engine.formwork_beam_area(b_beam, d_beam, L_beam) * n_beams",
            notes="Formwork to 3 faces of RCC beams (bottom + 2 sides)."
        ),
    ],
)


# 6) RCC SLAB (CONCRETE + STEEL + FORMWORK)
RCC_SLAB_PACKAGE = WorkPackage(
    name="RCC slab (concrete + steel + formwork)",
    section="Superstructure",
    default_phase="3️⃣ SUPERSTRUCTURE",
    description="RCC slab including concrete, reinforcement and soffit formwork.",
    components=[
        ComponentLine(
            role="slab_concrete",
            item_key="PCC M20 grade nominal mix (3.5.1)",
            quantity_expr="L_slab * B_slab * t_slab * n_slabs",
            notes="Slab concrete volume; using M20 as slab concrete item."
        ),
        ComponentLine(
            role="slab_reinforcement",
            item_key="Steel reinforcement for R.C.C. work Fe500 (5.0.1)",
            quantity_expr="IS1200Engine.steel_from_kg_per_cum(L_slab * B_slab * t_slab * n_slabs, steel_kg_per_cum_slab)['net']",
            notes="Slab reinforcement based on kg/m³ assumption (default ~100 kg/m³)."
        ),
        ComponentLine(
            role="slab_formwork",
            item_key="Formwork for bottom of slabs (3.10.5)",
            quantity_expr="IS1200Engine.formwork_slab_area(L_slab, B_slab) * n_slabs",
            notes="Formwork to slab soffit area."
        ),
    ],
)


# 7) BRICK WALL (PLINTH / SUPERSTRUCTURE) + INTERNAL PLASTER (ONE SIDE)
BRICKWALL_PLASTER_PACKAGE = WorkPackage(
    name="Brick wall with plaster (one side)",
    section="Superstructure",
    default_phase="3️⃣ SUPERSTRUCTURE",
    description="Brick masonry wall with 12 mm plaster on one face.",
    components=[
        ComponentLine(
            role="brickwork",
            item_key="Brickwork superstructure FB bricks (4.1.2)",
            quantity_expr="L_wall * t_wall * H_wall",
            notes="Brickwork in superstructure; thickness in metres (e.g., 0.23 for 230mm)."
        ),
        ComponentLine(
            role="plaster_one_side",
            item_key="12mm cement plaster 1:6 fair face (6.1.1)",
            quantity_expr="L_wall * H_wall",
            notes="12 mm cement-sand plaster on one face of wall."
        ),
    ],
)


# 8) FLOOR TILING – VITRIFIED TILES
FLOOR_TILES_PACKAGE = WorkPackage(
    name="Vitrified floor tiles 600x600mm (with 3% wastage)",
    section="Finishing",
    default_phase="4️⃣ FINISHING",
    description="Floor tiling in vitrified tiles 600x600mm, including 3% wastage.",
    components=[
        ComponentLine(
            role="floor_tiling",
            item_key="Vitrified floor tiles 600x600mm (12.1.1)",
            quantity_expr="IS1200Engine.floor_area_with_wastage(L_room, B_room, wastage_factor)['net']",
            notes="Vitrified tiles including 3% wastage; L_room & B_room in m, wastage_factor e.g. 1.03."
        ),
    ],
)


# 9) WALL PAINTING – INTERNAL
INTERNAL_PAINTING_PACKAGE = WorkPackage(
    name="Internal wall painting (putty + acrylic emulsion)",
    section="Finishing",
    default_phase="4️⃣ FINISHING",
    description="Internal wall system: putty + acrylic emulsion paint, both sides of wall.",
    components=[
        ComponentLine(
            role="putty",
            item_key="Wall care putty painting prep (10.5.1)",
            quantity_expr="IS1200Engine.wall_finish_area(L_wall, H_wall, sides)['net']",
            notes="Wall care putty on both sides; sides usually 2 for a partition."
        ),
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
    RCC_COLUMNS_PACKAGE.name: RCC_COLUMNS_PACKAGE,
    RCC_BEAMS_PACKAGE.name: RCC_BEAMS_PACKAGE,
    RCC_SLAB_PACKAGE.name: RCC_SLAB_PACKAGE,
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
        Contains all variables referenced in quantity_expr.
    phase : str or None
        BOQ phase label. If None, package.default_phase is used.
    cost_index : float
        Location cost index, e.g. 100.0 for base, 110.0 for 10% higher.

    Returns
    -------
    list[BOQLine]
    """
    if package_name not in WORK_PACKAGES_CIVIL:
        raise KeyError(f"Unknown work package: {package_name}")

    pkg = WORK_PACKAGES_CIVIL[package_name]
    eff_phase = phase or pkg.default_phase
    env = _build_eval_env(context)
    lines: List[BOQLine] = []

    for comp in pkg.components:
        if comp.item_key not in ITEMS:
            # item not present in DSR data; skip
            continue

        item: Item = ITEMS[comp.item_key]

        try:
            qty_val = eval(comp.quantity_expr, {}, env)
        except Exception:
            # skip this component if evaluation fails
            continue

        try:
            qty = float(qty_val)
        except (TypeError, ValueError):
            continue

        if qty <= 0.0:
            continue

        rate = item.rate_at_index(cost_index)
        amount = qty * rate

        # Basic geometry inference for MB: not critical but useful
        length = float(
            context.get(
                "L_wall",
                context.get(
                    "L_foot",
                    context.get(
                        "L_room",
                        context.get(
                            "L_slab",
                            context.get("L_beam", context.get("L", 0.0)),
                        ),
                    ),
                ),
            )
        )
        breadth = float(
            context.get(
                "B_wall",
                context.get(
                    "B_foot",
                    context.get(
                        "B_room",
                        context.get("B_slab", context.get("b_beam", context.get("B", 0.0))),
                    ),
                ),
            )
        )
        depth = float(
            context.get(
                "D_foot",
                context.get(
                    "D_exc",
                    context.get("d_beam", context.get("t_slab", context.get("D", 0.0))),
                ),
            )
        )
        height = float(
            context.get(
                "H_wall",
                context.get("h_col", context.get("H", 0.0)),
            )
        )

        meta = {
            "package_name": pkg.name,
            "component_role": comp.role,
        }

        line = BOQLine.from_item(
            line_id=0,  # caller assigns actual ID
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
