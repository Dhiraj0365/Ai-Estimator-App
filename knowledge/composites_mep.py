from __future__ import annotations

"""
MEP Work Packages (Composites) – Electrical, Plumbing, HVAC, Fire

This module defines *work packages* for common MEP operations, built on
top of:

- knowledge.dsr_master   → ITEMS (Item objects, CPWD/SoR)
- engines.elec_engine    → ElecEngine  (wiring & cables)
- engines.plumbing_engine→ PlumbingEngine (water & drainage)
- engines.hvac_engine    → HvacEngine  (ducting & CHW piping)
- engines.fire_engine    → FireEngine  (hydrants, sprinklers, alarm)
- core.models            → Item, BOQLine

Each package groups several DSR items (conduit, wires, fittings, fixtures,
ducting, etc.) into a **single logical unit** like:

- "Typical room lighting wiring"
- "Toilet block plumbing fixtures"
- "AHU zone ducting"
- "Floor fire alarm devices"

USAGE (example, UI or service layer):

    from knowledge.composites_mep import WORK_PACKAGES_MEP, expand_mep_package

    context = {
        "lighting_points": 8,
        "avg_run_ltg": 8.0,
        "vertical_drop": 3.0,
        "lighting_points_per_circuit": 8,
        "points_per_switchboard": 4,
    }

    lines = expand_mep_package(
        package_name="Typical room lighting wiring (conduit + wire + LEDs + switchboard)",
        context=context,
        phase="4️⃣ FINISHING",
        cost_index=110.0,
    )

    # 'lines' is a list[BOQLine]; caller assigns IDs and attaches to Project/SOQ.

NOTE:
- item_key strings MUST match keys in ITEMS (i.e. "Description (DSR Code)").
  Adjust them if your CSV descriptions differ.
- Quantity expressions are evaluated with `eval` in a controlled env that
  includes: context, ElecEngine, PlumbingEngine, HvacEngine, FireEngine,
  and Python math functions.
"""

from dataclasses import dataclass
from typing import List, Dict, Any, Optional

from engines.elec_engine import ElecEngine
from engines.plumbing_engine import PlumbingEngine
from engines.hvac_engine import HvacEngine
from engines.fire_engine import FireEngine
from knowledge.dsr_master import ITEMS
from core.models import Item, BOQLine


# =============================================================================
# Data structures
# =============================================================================

@dataclass
class MEPComponentLine:
    """
    One component of an MEP work package.

    Attributes
    ----------
    role         : str - logical role, e.g. "conduit", "lighting_wire",
                         "switchboard", "fixture_wc", "duct", etc.
    item_key     : str - key into ITEMS (Item objects).
    quantity_expr: str - Python expression evaluated against a context dict plus
                         helpers (ElecEngine, PlumbingEngine, etc.) to produce a
                         net quantity (float) in the DSR unit.
    notes        : str - engineering/audit notes (go into BOQLine.notes).
    """

    role: str
    item_key: str
    quantity_expr: str
    notes: str = ""


@dataclass
class MEPWorkPackage:
    """
    Logical MEP work package (e.g. typical room lighting, toilet plumbing).

    Attributes
    ----------
    name          : str   - user-facing name (used as key in WORK_PACKAGES_MEP).
    discipline    : str   - "electrical", "plumbing", "hvac", "fire".
    default_phase : str   - default phase for BOQ ("3️⃣ SUPERSTRUCTURE", "4️⃣ FINISHING").
    description   : str   - summary of what the package covers.
    components    : list[MEPComponentLine] - child DSR items and quantity rules.
    """

    name: str
    discipline: str
    default_phase: str
    description: str
    components: List[MEPComponentLine]


# =============================================================================
# Helper: safe eval environment
# =============================================================================

def _build_eval_env(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build an evaluation environment for quantity expressions.

    Includes:
    - All context keys/values.
    - ElecEngine, PlumbingEngine, HvacEngine, FireEngine.
    - Basic Python math functions.
    """
    env: Dict[str, Any] = {}
    env.update(context)
    env.update(
        {
            "ElecEngine": ElecEngine,
            "PlumbingEngine": PlumbingEngine,
            "HvacEngine": HvacEngine,
            "FireEngine": FireEngine,
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
# WORK PACKAGES – ELECTRICAL, PLUMBING, HVAC, FIRE
# =============================================================================
#
# IMPORTANT:
# item_key strings MUST match what your DSR CSV created:
#   item_key = "Description (DSR Code)"
#
# Below we use item_key strings that correspond to typical rows from the
# sample you provided. If any of these don't exist in your CSV, either:
#   - Adjust the item_key here to match your actual Description text, or
#   - Add/rename items in your CSV to match these keys.
# =============================================================================

# -------------------------------------------------------------------------
# 1) ELECTRICAL – TYPICAL ROOM LIGHTING WIRING
# -------------------------------------------------------------------------
#
# Context required:
#   lighting_points          : int   - number of lighting points (incl. fans if desired)
#   avg_run_ltg              : float - average horizontal run per point (m)
#   vertical_drop            : float - typical vertical drop per point (m)
#   lighting_points_per_circuit : int - max points per lighting circuit
#   points_per_switchboard   : int   - how many points per 6M switchboard (rule of thumb)
#
# Quantities:
#   - Conduit 20mm heavy gauge: length from ElecEngine.point_wiring_estimate
#   - 2-core 1.5sqmm cable    : same wiring result
#   - LED bulbs 9W            : one per point
#   - 6-module switchboard    : ceil(points / points_per_switchboard)

ELECTRICAL_LIGHTING_PACKAGE = MEPWorkPackage(
    name="Typical room lighting wiring (conduit + wire + LEDs + switchboard)",
    discipline="electrical",
    default_phase="4️⃣ FINISHING",
    description="Lighting points wiring in PVC conduit with 2-core copper cable, LED bulbs, and 6M switchboard.",
    components=[
        # Conduit 20mm heavy gauge
        MEPComponentLine(
            role="conduit_20mm",
            item_key="PVC conduit 20mm heavy gauge (1.32.1)",
            quantity_expr=(
                "ElecEngine.point_wiring_estimate("
                "lighting_points, avg_run_ltg, vertical_drop, lighting_points_per_circuit"
                ").conduit_length_m"
            ),
            notes="PVC conduit 20mm heavy gauge for lighting circuit wiring."
        ),
        # Lighting wires (2-core 1.5 sqmm)
        MEPComponentLine(
            role="ltg_wire_2c_1p5",
            item_key="Copper PVC insulated cable 2 core 1.5sqmm (1.33.1)",
            quantity_expr=(
                "ElecEngine.point_wiring_estimate("
                "lighting_points, avg_run_ltg, vertical_drop, lighting_points_per_circuit"
                ").wire_length_m"
            ),
            notes="2-core 1.5 sqmm copper PVC insulated cable for lighting."
        ),
        # LED bulbs – one per point
        MEPComponentLine(
            role="led_bulb_9w",
            item_key="LED bulb 9W B22 6500K (1.37.1)",
            quantity_expr="lighting_points",
            notes="One LED bulb 9W per lighting point."
        ),
        # 6 module switchboard – simple rule: ceil(points / points_per_switchboard)
        MEPComponentLine(
            role="switchboard_6M",
            item_key="6 Module switch board flush (1.28.1)",
            quantity_expr="math.ceil(lighting_points / max(points_per_switchboard, 1))",
            notes="Number of 6-module switchboards based on lighting points."
        ),
    ],
)


# -------------------------------------------------------------------------
# 2) PLUMBING – TOILET BLOCK PLUMBING FIXTURES
# -------------------------------------------------------------------------
#
# Context required:
#   toilet_blocks           : int   - number of toilet blocks
#   wc_per_block           : int   - WCs per toilet block
#   basins_per_block       : int
#   urinals_per_block      : int
#   floor_traps_per_block  : int
#   nahani_traps_per_block : int
#
# Quantities derived via PlumbingEngine.fixture_group(...)

PLUMBING_TOILET_FIXTURES_PACKAGE = MEPWorkPackage(
    name="Toilet block plumbing fixtures (WC + basin + urinal + traps)",
    discipline="plumbing",
    default_phase="4️⃣ FINISHING",
    description="Sanitary fixtures and traps for typical toilet blocks.",
    components=[
        # WCs – European type
        MEPComponentLine(
            role="wc_european",
            item_key="European WC vitreous china (13.2.1)",
            quantity_expr=(
                "PlumbingEngine.fixture_group("
                "wc_per_block, toilet_blocks, basins_per_block, "
                "urinals_per_block, 0, floor_traps_per_block, nahani_traps_per_block"
                ").wc_count"
            ),
            notes="European type WCs per fixture group."
        ),
        # Wash basins
        MEPComponentLine(
            role="wash_basin",
            item_key="Wash basin CI brackets vitreous (13.42.1)",
            quantity_expr=(
                "PlumbingEngine.fixture_group("
                "wc_per_block, toilet_blocks, basins_per_block, "
                "urinals_per_block, 0, floor_traps_per_block, nahani_traps_per_block"
                ").basin_count"
            ),
            notes="Wash basins with CI brackets."
        ),
        # Urinals (full length)
        MEPComponentLine(
            role="urinal_full",
            item_key="Urinal full length vitreous (13.7.1)",
            quantity_expr=(
                "PlumbingEngine.fixture_group("
                "wc_per_block, toilet_blocks, basins_per_block, "
                "urinals_per_block, 0, floor_traps_per_block, nahani_traps_per_block"
                ").urinal_count"
            ),
            notes="Full-length urinals."
        ),
        # Floor traps
        MEPComponentLine(
            role="floor_trap",
            item_key="P.V.C. floor trap 150x150mm (15.8.1)",
            quantity_expr=(
                "PlumbingEngine.fixture_group("
                "wc_per_block, toilet_blocks, basins_per_block, "
                "urinals_per_block, 0, floor_traps_per_block, nahani_traps_per_block"
                ").floor_trap_count"
            ),
            notes="PVC floor traps 150x150mm."
        ),
        # Nahani traps
        MEPComponentLine(
            role="nahani_trap",
            item_key="P.V.C. nahani trap 100x75mm (13.16.1)",
            quantity_expr=(
                "PlumbingEngine.fixture_group("
                "wc_per_block, toilet_blocks, basins_per_block, "
                "urinals_per_block, 0, floor_traps_per_block, nahani_traps_per_block"
                ").nahani_trap_count"
            ),
            notes="PVC nahani traps 100x75mm."
        ),
    ],
)


# -------------------------------------------------------------------------
# 3) HVAC – AHU ZONE DUCTING (GI DUCTING AREA)
# -------------------------------------------------------------------------
#
# Context required:
#   supply_cmh            : float - supply air flow for zone (m³/h)
#   main_duct_length_m    : float
#   branch_duct_length_m  : float
#
# Quantities:
#   - GI ducting: duct surface area from HvacEngine.duct_run_estimate()

HVAC_AHU_DUCTING_PACKAGE = MEPWorkPackage(
    name="AHU zone ducting (GI sheet metal)",
    discipline="hvac",
    default_phase="3️⃣ SUPERSTRUCTURE",
    description="GI ducting for an AHU zone, using supply CMH and assumed velocities.",
    components=[
        MEPComponentLine(
            role="gi_ducting",
            item_key="Ducting GI 600x600mm (114.1)",
            quantity_expr=(
                "HvacEngine.duct_run_estimate("
                "supply_cmh, main_duct_length_m, branch_duct_length_m"
                ").duct_surface_area_sqm"
            ),
            notes="Approximate GI duct sheet area from supply airflow and duct lengths."
        ),
    ],
)


# -------------------------------------------------------------------------
# 4) FIRE – FLOOR FIRE ALARM DEVICES
# -------------------------------------------------------------------------
#
# Context required:
#   smoke_detectors : int
#   heat_detectors  : int
#   mcps            : int   - manual call points
#   hooters         : int   - sounders/hooter
#
# Quantities mapped directly.

FIRE_ALARM_FLOOR_PACKAGE = MEPWorkPackage(
    name="Fire alarm devices for floor (smoke + heat + MCP + hooter)",
    discipline="fire",
    default_phase="4️⃣ FINISHING",
    description="Conventional fire alarm devices for a typical floor.",
    components=[
        MEPComponentLine(
            role="smoke_detector",
            item_key="Smoke detector conventional (5.2.1)",
            quantity_expr="smoke_detectors",
            notes="Smoke detectors per floor."
        ),
        MEPComponentLine(
            role="heat_detector",
            item_key="Heat detector rate of rise type (5.3.1)",
            quantity_expr="heat_detectors",
            notes="Heat detectors per floor."
        ),
        MEPComponentLine(
            role="mcp",
            item_key="Manual call point weather proof (5.4.1)",
            quantity_expr="mcps",
            notes="Manual call points."
        ),
        MEPComponentLine(
            role="hooter",
            item_key="Hooter siren 24V DC 100dB (5.5.1)",
            quantity_expr="hooters",
            notes="Alarm sounders/hooters."
        ),
    ],
)


WORK_PACKAGES_MEP: Dict[str, MEPWorkPackage] = {
    ELECTRICAL_LIGHTING_PACKAGE.name: ELECTRICAL_LIGHTING_PACKAGE,
    PLUMBING_TOILET_FIXTURES_PACKAGE.name: PLUMBING_TOILET_FIXTURES_PACKAGE,
    HVAC_AHU_DUCTING_PACKAGE.name: HVAC_AHU_DUCTING_PACKAGE,
    FIRE_ALARM_FLOOR_PACKAGE.name: FIRE_ALARM_FLOOR_PACKAGE,
}


# =============================================================================
# EXPANSION FUNCTION – convert an MEPWorkPackage into BOQLines
# =============================================================================

def expand_mep_package(
    package_name: str,
    context: Dict[str, Any],
    phase: Optional[str],
    cost_index: float,
) -> List[BOQLine]:
    """
    Expand an MEP work package into a list of BOQLine objects.

    Parameters
    ----------
    package_name : str
        Key in WORK_PACKAGES_MEP.
    context : dict
        Geometric/usage inputs required by quantity expressions; see
        each package definition's docstring/comment for required keys.
    phase : str or None
        BOQ phase label. If None, package.default_phase is used.
    cost_index : float
        Location cost index, e.g. 100.0 for base, 110.0 for 10% higher.

    Returns
    -------
    list[BOQLine]
        BOQLine entries with id=0 (caller should assign IDs).
    """
    if package_name not in WORK_PACKAGES_MEP:
        raise KeyError(f"Unknown MEP work package: {package_name}")

    pkg = WORK_PACKAGES_MEP[package_name]
    eff_phase = phase or pkg.default_phase
    env = _build_eval_env(context)
    lines: List[BOQLine] = []

    for comp in pkg.components:
        # Check if DSR item exists
        if comp.item_key not in ITEMS:
            # If not present, skip silently – user may adjust item_key or CSV.
            continue

        item: Item = ITEMS[comp.item_key]

        # Evaluate quantity expression
        try:
            qty_val = eval(comp.quantity_expr, {}, env)
        except Exception:
            # Skip this component if evaluation fails; caller can log in UI.
            continue

        try:
            qty = float(qty_val)
        except (TypeError, ValueError):
            continue

        if qty <= 0.0:
            continue

        rate = item.rate_at_index(cost_index)
        amount = qty * rate

        # For MEP, geometry (length/breadth/depth/height) is generally not
        # captured at BOQ line level; keep 0.0 but could be filled from context.
        meta = {
            "package_name": pkg.name,
            "discipline": pkg.discipline,
            "component_role": comp.role,
        }

        line = BOQLine.from_item(
            line_id=0,  # caller assigns actual id
            item=item,
            phase=eff_phase,
            quantity=qty,
            rate=rate,
            amount=amount,
            source=f"mep_package: {pkg.name}",
            notes=comp.notes,
            length=0.0,
            breadth=0.0,
            depth=0.0,
            height=0.0,
            meta=meta,
        )
        lines.append(line)

    return lines
```
