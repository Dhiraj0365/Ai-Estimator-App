from __future__ import annotations

"""
HVAC Rules Engine – Basic Dependency & Sanity Checks

This module defines *HVAC-only* validation / audit rules that work
on the current BOQ / SOQ and return a list of RuleResult objects.

It is UI-agnostic and can be used from:
- rules_runner.py
- Streamlit app (Audit tab)
- Tests

INPUT
-----
Supports both:
- List[core.models.BOQLine], or
- List[dict]  (legacy st.session_state.qto_items format)

Each rule receives this list and returns a list[RuleResult].

HVAC-RELATED ITEMS DETECTED BY DESCRIPTION
------------------------------------------
Because DSR codes & categories for HVAC are not always standalone, we
mostly detect HVAC items from **description** text:

Ducting / terminals:
    "duct", "ducting", "grille", "diffuser", "damper"

Equipment:
    "AHU", "air handling unit", "FCU", "fan coil", "VRF", "VRV",
    "chiller", "cassette", "split AC", "inline fan", "axial fan",
    "propeller fan", "volume control damper", "fire damper"

Chilled water / refrigerant pipes:
    "chilled water pipe", "CHW pipe", "refrigerant pipe", "condenser water pipe"

ELECTRICAL POWER FOR HVAC:
We don’t deep-check power sizing, but we check for presence of *some*
electrical cables/switchgear when large HVAC equipment is present.

RULES IMPLEMENTED
-----------------
1. rule_hvac_ducts_require_air_movers
   - WARN if GI ducting / diffusers / dampers exist but **no** AHUs/fans
     (air movers) appear in the BOQ.

2. rule_hvac_equipment_requires_power
   - WARN if major HVAC equipment (AHUs, chillers, VRF units, cassette/split AC)
     exist but **no** electrical cables/switchgear exist in the whole BOQ.

3. rule_hvac_phase_reasonable
   - WARN if the majority of HVAC value is assigned to Substructure/Plinth
     instead of Superstructure/Finishing (typical mis-phasing).

You can extend this module with more rules (e.g., AHU airflow vs ducting area,
pipe vs AHU count) as design data becomes available.
"""

from dataclasses import dataclass
from typing import List, Dict, Any, Callable, Sequence

from core.models import RuleResult, BOQLine


# =============================================================================
# Internal helper to normalise entries
# =============================================================================

@dataclass
class _NormHvacItem:
    """Normalised view over BOQLine or dict entry for HVAC rule checks."""
    id: int
    phase: str
    discipline: str
    category: str
    description: str
    code: str
    amount: float


def _normalise_hvac_items(items: Sequence[Any]) -> List[_NormHvacItem]:
    """
    Convert list of BOQLine or dict entries into a list of _NormHvacItem.

    We do *not* filter by discipline here because in your current data,
    many HVAC items are classified with 'civil' discipline or 'misc'
    category. Instead, we inspect descriptions for HVAC-related keywords.

    Supports:
    - core.models.BOQLine
    - dicts with keys: 'id', 'phase', 'discipline', 'category',
      'description' (or 'item'), 'dsr_code'/'code', 'amount'.
    """
    norm: List[_NormHvacItem] = []
    for src in items:
        if isinstance(src, BOQLine):
            n = _NormHvacItem(
                id=src.id,
                phase=str(src.phase or ""),
                discipline=str(src.discipline or "").lower() or "civil",
                category=str(src.category or "").lower(),
                description=str(src.description or ""),
                code=str(src.item.code if src.item else ""),
                amount=float(src.amount or 0.0),
            )
        elif isinstance(src, dict):
            desc = str(
                src.get("description")
                or src.get("item")
                or src.get("item_key")
                or ""
            )
            n = _NormHvacItem(
                id=int(src.get("id", 0)),
                phase=str(src.get("phase", "")),
                discipline=str(src.get("discipline", "civil")).lower(),
                category=str(src.get("category", "")).lower(),
                description=desc,
                code=str(src.get("code") or src.get("dsr_code") or ""),
                amount=float(src.get("amount", 0.0) or 0.0),
            )
        else:
            continue

        norm.append(n)

    return norm


RuleFn = Callable[[Sequence[Any]], List[RuleResult]]


# =============================================================================
# Keyword-based detection helpers
# =============================================================================

def _is_duct_item(ni: _NormHvacItem) -> bool:
    """Detect ducting/terminal items by description."""
    d = ni.description.lower()
    # We consider ducts/ducting, diffusers, grilles, dampers as HVAC duct system
    return any(
        kw in d
        for kw in (
            "duct", "ducting", "gi duct", "grille", "diffuser",
            "damper", "vcd", "fire damper", "volume control damper",
        )
    )


def _is_air_mover(ni: _NormHvacItem) -> bool:
    """Detect AHUs, FCUs, fans etc. (air movers)."""
    d = ni.description.lower()
    return any(
        kw in d
        for kw in (
            "ahu",
            "air handling unit",
            "fan coil",
            "fcu",
            "inline fan",
            "axial flow fan",
            "propeller fan",
            "cassette type",
            "cassette ac",
            "split ac",
            "vrf outdoor",
            "vrf indoor",
            "vrv",
            "ventilation fan",
        )
    )


def _is_major_hvac_equipment(ni: _NormHvacItem) -> bool:
    """Detect major HVAC equipment requiring dedicated power & piping."""
    d = ni.description.lower()
    return any(
        kw in d
        for kw in (
            "ahu",
            "air handling unit",
            "chiller",
            "vrf",
            "vrv",
            "cassette type",
            "cassette ac",
            "split ac",
            "fc u",  # FCU (variations)
            "fan coil",
        )
    )


def _is_electrical_cable_or_switchgear(ni: _NormHvacItem) -> bool:
    """Broad detection of electrical cables/switchgear in BOQ."""
    d = ni.description.lower()
    # We look for generic 'cable', 'db', 'panel', 'mccb', 'switchboard', etc.
    if "cable" in d:
        return True
    if any(kw in d for kw in ("distribution board", "mcb", "db ", " db", "panel", "lt panel", "apfc panel")):
        return True
    return False


def _is_hvac_related(ni: _NormHvacItem) -> bool:
    """Determine if an item is likely HVAC-related at all."""
    return _is_duct_item(ni) or _is_air_mover(ni) or _is_major_hvac_equipment(ni)


# =============================================================================
# Rule 1 – Ducts require air movers (AHUs/fans)
# =============================================================================

def rule_hvac_ducts_require_air_movers(items: Sequence[Any]) -> List[RuleResult]:
    """
    If GI ducts/grilles/diffusers are present, there should be at least one
    air mover (AHU, FCU, inline/axial/propeller fan).

    This is a dependency check: ducting without any AHU/fan is incomplete.
    """
    norm = _normalise_hvac_items(items)
    if not norm:
        return []

    has_ducts = any(_is_duct_item(ni) for ni in norm)
    has_air_movers = any(_is_air_mover(ni) for ni in norm)

    results: List[RuleResult] = []
    if has_ducts and not has_air_movers:
        results.append(
            RuleResult(
                level="WARNING",
                discipline="hvac",
                code="HVAC-DEP-001",
                message=(
                    "Ducting/terminal items (ducts, grilles, diffusers, dampers) "
                    "are present but no AHU/FCU/fan items are found. "
                    "HVAC ductwork should normally be connected to air handling "
                    "units or fans providing airflow."
                ),
            )
        )

    return results


# =============================================================================
# Rule 2 – Major HVAC equipment requires electrical power
# =============================================================================

def rule_hvac_equipment_requires_power(items: Sequence[Any]) -> List[RuleResult]:
    """
    If major HVAC equipment (AHUs, chillers, VRF units, cassette/split AC)
    exist, there should be at least some electrical cable/switchgear items
    in the whole BOQ.

    This is a high-level dependency check: it does not verify exact sizing,
    just basic presence of power supply infrastructure.
    """
    norm = _normalise_hvac_items(items)
    if not norm:
        return []

    has_equipment = any(_is_major_hvac_equipment(ni) for ni in norm)

    # Look across ALL items (not just hvac) for cables/switchgear via description
    has_power = any(_is_electrical_cable_or_switchgear(ni) for ni in norm)

    results: List[RuleResult] = []
    if has_equipment and not has_power:
        results.append(
            RuleResult(
                level="WARNING",
                discipline="hvac",
                code="HVAC-DEP-002",
                message=(
                    "Major HVAC equipment (AHUs/chillers/VRF/split/cassette AC) "
                    "is present but no electrical cable/switchgear items are found. "
                    "HVAC equipment typically requires dedicated power feeds and "
                    "switchgear; please include appropriate electrical items."
                ),
            )
        )

    return results


# =============================================================================
# Rule 3 – Phase reasonableness for HVAC
# =============================================================================

def rule_hvac_phase_reasonable(items: Sequence[Any]) -> List[RuleResult]:
    """
    Check that HVAC items (ducting, fans, AHUs, chillers, etc.) are not
    placed entirely in early phases (Substructure/Plinth).

    We expect most HVAC items to be in:
        - "3️⃣ SUPERSTRUCTURE"  (main ducts, risers, plantrooms)
        - "4️⃣ FINISHING"       (terminals, final connections, split units)

    WARN if:
    - majority of HVAC value by amount is in '1️⃣ SUBSTRUCTURE'
      or '2️⃣ PLINTH'.
    """
    norm = _normalise_hvac_items(items)
    if not norm:
        return []

    # Only consider items that appear HVAC-related
    hvac_items = [ni for ni in norm if _is_hvac_related(ni)]
    if not hvac_items:
        return []

    amount_by_phase: Dict[str, float] = {}
    for ni in hvac_items:
        amount_by_phase[ni.phase] = amount_by_phase.get(ni.phase, 0.0) + ni.amount

    total = sum(amount_by_phase.values())
    if total <= 0.0:
        return []

    early_phases = {"1️⃣ SUBSTRUCTURE", "2️⃣ PLINTH"}
    early_amount = sum(amount_by_phase.get(p, 0.0) for p in early_phases)
    early_share = early_amount / total if total > 0 else 0.0

    results: List[RuleResult] = []
    if early_share > 0.5:
        results.append(
            RuleResult(
                level="WARNING",
                discipline="hvac",
                code="HVAC-PHASE-001",
                message=(
                    "More than 50% of HVAC BOQ value is assigned to "
                    "Substructure/Plinth phases. Typically, HVAC works "
                    "are executed mostly during Superstructure and Finishing; "
                    "please verify phase assignments for ducting and equipment."
                ),
            )
        )

    return results


# =============================================================================
# Aggregate: list of all HVAC rules
# =============================================================================

ALL_HVAC_RULES: List[RuleFn] = [
    rule_hvac_ducts_require_air_movers,
    rule_hvac_equipment_requires_power,
    rule_hvac_phase_reasonable,
]


def run_hvac_rules(items: Sequence[Any]) -> List[RuleResult]:
    """
    Convenience function to run all HVAC rules on a given
    list of BOQLine / dicts.

    Returns
    -------
    list[RuleResult]
    """
    all_results: List[RuleResult] = []
    for rule in ALL_HVAC_RULES:
        try:
            all_results.extend(rule(items))
        except Exception:
            # Fail-safe: ignore individual rule failure and continue.
            continue
    return all_results
