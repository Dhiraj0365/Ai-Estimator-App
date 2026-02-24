from __future__ import annotations

"""
Electrical Rules Engine – Basic Dependency & Sanity Checks

This module defines *electrical-only* validation / audit rules that work
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

CATEGORIES (as guessed in knowledge.dsr_master)
-----------------------------------------------
From the DSR code → category logic we set earlier, we will typically see:

- 'electrical_switchgear'  : DBs, MCBs, RCCBs, panels, etc.
- 'electrical_cables'      : LV cables, flexible cables.
- 'electrical_lighting'    : LED bulbs, tube lights, panel lights, street lights.
- 'electrical_fans'        : ceiling fans, exhaust fans, wall fans.
- 'earthing'               : GI/chemical earthing, lightning conductors, earth strips.

RULES IMPLEMENTED
-----------------
1. rule_elec_lighting_requires_cables
   - WARN if lighting fixtures exist but no electrical cables.

2. rule_elec_lighting_requires_switchgear
   - WARN if lighting fixtures exist but no switchgear/DBs/MCBs.

3. rule_elec_fans_require_cables
   - WARN if fans exist but no electrical cables.

4. rule_elec_switchgear_requires_earthing
   - WARN if there are DBs/switchgear but no earthing items.

5. rule_elec_phase_reasonable
   - WARN if significant electrical items exist in early phases
     (Substructure/Plinth) rather than Superstructure/Finishing.

Extend / add rules here as you refine your electrical modelling.
"""

from dataclasses import dataclass
from typing import List, Dict, Any, Callable, Sequence

from core.models import RuleResult, BOQLine


# =============================================================================
# Internal helper to normalise entries
# =============================================================================

@dataclass
class _NormElecItem:
    """Normalised view over BOQLine or dict entry for electrical rule checks."""
    id: int
    phase: str
    discipline: str
    category: str
    description: str
    code: str
    amount: float


def _normalise_elec_items(items: Sequence[Any]) -> List[_NormElecItem]:
    """
    Convert list of BOQLine or dict entries into a list of _NormElecItem,
    filtering to `discipline == 'electrical'` when possible.

    Supports:
    - core.models.BOQLine
    - dicts with keys: 'id', 'phase', 'discipline', 'category',
      'description' (or 'item'), 'dsr_code'/'code', 'amount'.
    """
    norm: List[_NormElecItem] = []
    for src in items:
        if isinstance(src, BOQLine):
            disc = str(src.discipline or "").lower()
            if disc and disc != "electrical":
                continue
            n = _NormElecItem(
                id=src.id,
                phase=str(src.phase or ""),
                discipline="electrical",
                category=str(src.category or "").lower(),
                description=str(src.description or ""),
                code=str(src.item.code if src.item else ""),
                amount=float(src.amount or 0.0),
            )
        elif isinstance(src, dict):
            disc = str(src.get("discipline", "")).lower() or "electrical"
            if disc != "electrical":
                continue
            desc = str(
                src.get("description")
                or src.get("item")
                or src.get("item_key")
                or ""
            )
            n = _NormElecItem(
                id=int(src.get("id", 0)),
                phase=str(src.get("phase", "")),
                discipline="electrical",
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
# Rule 1 – Lighting requires cables
# =============================================================================

def rule_elec_lighting_requires_cables(items: Sequence[Any]) -> List[RuleResult]:
    """
    If there are lighting fixtures (category 'electrical_lighting'), there
    should also be at least one cable item (category 'electrical_cables').

    This is a basic dependency check: LED lights without any cabling would
    be flagged by audit.
    """
    norm = _normalise_elec_items(items)
    if not norm:
        return []

    has_ltg = any(ni.category == "electrical_lighting" for ni in norm)
    has_cables = any(ni.category == "electrical_cables" for ni in norm)

    results: List[RuleResult] = []
    if has_ltg and not has_cables:
        results.append(
            RuleResult(
                level="WARNING",
                discipline="electrical",
                code="ELEC-DEP-001",
                message=(
                    "Lighting fixtures (LED bulbs/tube lights/panels) are present "
                    "but no electrical cable items are found. Normally, "
                    "wiring/cable items must be included for lighting circuits."
                ),
            )
        )

    return results


# =============================================================================
# Rule 2 – Lighting requires switchgear / DBs
# =============================================================================

def rule_elec_lighting_requires_switchgear(items: Sequence[Any]) -> List[RuleResult]:
    """
    If there are lighting fixtures, there should be at least one
    switchgear/DB/MCB item (category 'electrical_switchgear').

    Otherwise, we have lights with no originating DB/circuit protection.
    """
    norm = _normalise_elec_items(items)
    if not norm:
        return []

    has_ltg = any(ni.category == "electrical_lighting" for ni in norm)
    has_swgr = any(ni.category == "electrical_switchgear" for ni in norm)

    results: List[RuleResult] = []
    if has_ltg and not has_swgr:
        results.append(
            RuleResult(
                level="WARNING",
                discipline="electrical",
                code="ELEC-DEP-002",
                message=(
                    "Lighting fixtures are present but no switchgear/DB/MCB items "
                    "are present. Lighting circuits should be connected to "
                    "distribution boards with proper MCB protections."
                ),
            )
        )

    return results


# =============================================================================
# Rule 3 – Fans require cables
# =============================================================================

def rule_elec_fans_require_cables(items: Sequence[Any]) -> List[RuleResult]:
    """
    If there are ceiling/exhaust/wall/fresh-air fans (category 'electrical_fans'),
    check that at least one cable item exists.

    It's possible you treat some fan wiring as part of lighting, but this
    rule still catches the obvious missing wiring.
    """
    norm = _normalise_elec_items(items)
    if not norm:
        return []

    has_fans = any(ni.category == "electrical_fans" for ni in norm)
    has_cables = any(ni.category == "electrical_cables" for ni in norm)

    results: List[RuleResult] = []
    if has_fans and not has_cables:
        results.append(
            RuleResult(
                level="WARNING",
                discipline="electrical",
                code="ELEC-DEP-003",
                message=(
                    "Fans (ceiling/exhaust/wall) are present but no electrical "
                    "cable items exist. Fan circuits should include cabling."
                ),
            )
        )

    return results


# =============================================================================
# Rule 4 – Switchgear requires earthing
# =============================================================================

def rule_elec_switchgear_requires_earthing(items: Sequence[Any]) -> List[RuleResult]:
    """
    If there are DBs/switchgear items (category 'electrical_switchgear'),
    check that earthing items (category 'earthing') are present.

    This is a very high-level check. Earthing details (earthing strip size,
    earth pit count) are not validated here, just basic existence.
    """
    norm = _normalise_elec_items(items)
    if not norm:
        return []

    has_swgr = any(ni.category == "electrical_switchgear" for ni in norm)
    has_earth = any(ni.category == "earthing" for ni in norm)

    results: List[RuleResult] = []
    if has_swgr and not has_earth:
        results.append(
            RuleResult(
                level="WARNING",
                discipline="electrical",
                code="ELEC-DEP-004",
                message=(
                    "Electrical switchgear/DB items exist but no earthing items "
                    "are present. GI/chemical earthing and earth conductors "
                    "should be included as per IS 3043 / IE rules."
                ),
            )
        )

    return results


# =============================================================================
# Rule 5 – Phase reasonableness for electrical items
# =============================================================================

def rule_elec_phase_reasonable(items: Sequence[Any]) -> List[RuleResult]:
    """
    Check that significant electrical items (lighting, fans, DBs, cables)
    are not placed entirely in early phases (Substructure/Plinth).

    We expect most electrical items to be in:
        - "3️⃣ SUPERSTRUCTURE"  (riser conduits, shaft wiring)
        - "4️⃣ FINISHING"       (final wiring, fixtures, boards)

    WARN if:
    - majority of electrical amount by value is in phase '1️⃣ SUBSTRUCTURE'
      or '2️⃣ PLINTH' (likely miscoding).
    """
    norm = _normalise_elec_items(items)
    if not norm:
        return []

    # Aggregate amount by phase
    amount_by_phase: Dict[str, float] = {}
    for ni in norm:
        amount_by_phase[ni.phase] = amount_by_phase.get(ni.phase, 0.0) + ni.amount

    total = sum(amount_by_phase.values())
    if total <= 0.0:
        return []

    results: List[RuleResult] = []

    # If >50% of electrical value is in early phases, raise a warning
    early_phases = {"1️⃣ SUBSTRUCTURE", "2️⃣ PLINTH"}
    early_amount = sum(amount_by_phase.get(p, 0.0) for p in early_phases)
    early_share = early_amount / total if total > 0 else 0.0

    if early_share > 0.5:
        results.append(
            RuleResult(
                level="WARNING",
                discipline="electrical",
                code="ELEC-PHASE-001",
                message=(
                    "More than 50% of electrical BOQ value is assigned to "
                    "Substructure/Plinth phases. Typically, electrical work "
                    "should fall mostly under Superstructure/Finishing phases; "
                    "check phase assignments."
                ),
            )
        )

    return results


# =============================================================================
# Aggregate: list of all electrical rules
# =============================================================================

ALL_ELEC_RULES: List[RuleFn] = [
    rule_elec_lighting_requires_cables,
    rule_elec_lighting_requires_switchgear,
    rule_elec_fans_require_cables,
    rule_elec_switchgear_requires_earthing,
    rule_elec_phase_reasonable,
]


def run_elec_rules(items: Sequence[Any]) -> List[RuleResult]:
    """
    Convenience function to run all electrical rules on a given
    list of BOQLine / dicts.

    Returns
    -------
    list[RuleResult]
    """
    all_results: List[RuleResult] = []
    for rule in ALL_ELEC_RULES:
        try:
            all_results.extend(rule(items))
        except Exception:
            # Fail-safe: ignore individual rule failure and continue.
            continue
    return all_results
