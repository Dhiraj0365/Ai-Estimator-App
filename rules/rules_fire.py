from __future__ import annotations

"""
Fire-Fighting / Fire-Protection Rules Engine – Basic Dependency Checks

This module defines *fire-only* validation / audit rules that work
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

FIRE-RELATED ITEMS DETECTED BY DESCRIPTION
------------------------------------------
Because DSR codes & categories are not always cleanly separated for fire,
we primarily detect fire items from their **description** text:

- Fire mains / sprinklers / hydrants:
  descriptions containing:
    "hydrant", "sprinkler", "hose reel", "wet riser", "fire main"

- Fire pumps:
  "fire pump", "hydrant pump", "sprinkler pump", "jockey pump"

- Fire tanks:
  "fire water tank", "fire fighting tank"

- Fire alarm devices:
  "fire alarm panel", "smoke detector", "heat detector",
  "manual call point", "MCP", "hooter", "siren"

RULES IMPLEMENTED
-----------------
1. rule_fire_pipes_require_pump_and_or_tank
   - WARN if fire mains/sprinkler/hydrant pipes exist but *no* fire pump
     or fire water tank items are present.

2. rule_fire_alarm_requires_panel
   - WARN if fire alarm field devices (smoke/heat/MCP/hooter) exist but
     no "fire alarm panel" item is present.

3. rule_fire_alarm_requires_cables
   - WARN if fire alarm field devices exist but no "fire alarm cable" or
     general "cable" items exist in the BOQ at all.

4. rule_fire_phase_reasonable
   - WARN if most fire system value is in Substructure/Plinth rather than
     Superstructure/Finishing (typical mis-phasing).

You can extend this module with more rules (e.g., hydrant coverage per
floor area, sprinkler density check if design data is available).
"""

from dataclasses import dataclass
from typing import List, Dict, Any, Callable, Sequence

from core.models import RuleResult, BOQLine


# =============================================================================
# Internal helper to normalise entries
# =============================================================================

@dataclass
class _NormFireItem:
    """Normalised view over BOQLine or dict entry for fire rule checks."""
    id: int
    phase: str
    discipline: str
    category: str
    description: str
    code: str
    amount: float


def _normalise_fire_items(items: Sequence[Any]) -> List[_NormFireItem]:
    """
    Convert list of BOQLine or dict entries into a list of _NormFireItem.

    We do NOT restrict by discipline here because in your current data,
    some fire items are classified as 'stone_masonry' or 'electrical'
    by code; instead we rely mostly on description keywords.

    Supports:
    - core.models.BOQLine
    - dicts with keys: 'id', 'phase', 'discipline', 'category',
      'description' (or 'item'), 'dsr_code'/'code', 'amount'.
    """
    norm: List[_NormFireItem] = []
    for src in items:
        if isinstance(src, BOQLine):
            n = _NormFireItem(
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
            n = _NormFireItem(
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

def _is_fire_pipe(ni: _NormFireItem) -> bool:
    """Detect hydrant/sprinkler/hose-reel pipe items by description."""
    d = ni.description.lower()
    if any(word in d for word in ("hydrant", "sprinkler", "hose reel", "wet riser", "fire main")):
        return True
    # Many fire pipes use same DSR as regular pipes – category 'pipes'
    # plus 'fire' / 'hydrant' / 'sprinkler' hints in description.
    if ni.category == "pipes" and "fire" in d:
        return True
    return False


def _is_fire_pump(ni: _NormFireItem) -> bool:
    """Detect fire pumps by description."""
    d = ni.description.lower()
    return any(
        word in d
        for word in (
            "fire pump",
            "hydrant pump",
            "sprinkler pump",
            "jockey pump",
            "fire-fighting pump",
        )
    )


def _is_fire_tank(ni: _NormFireItem) -> bool:
    """Detect fire water tanks by description."""
    d = ni.description.lower()
    # Strict: both 'fire' & 'tank' present
    return "tank" in d and "fire" in d


def _is_fire_alarm_panel(ni: _NormFireItem) -> bool:
    """Detect fire alarm panels by description."""
    d = ni.description.lower()
    return "fire alarm panel" in d or ("fire alarm" in d and "panel" in d)


def _is_fire_alarm_device(ni: _NormFireItem) -> bool:
    """Detect field fire alarm devices (smoke, heat, MCP, hooter)."""
    d = ni.description.lower()
    return any(
        kw in d
        for kw in (
            "smoke detector",
            "heat detector",
            "manual call point",
            "mcp",
            "hooter",
            "siren",
            "sounder",
        )
    )


def _is_cable(ni: _NormFireItem) -> bool:
    """Broad cable detection (for fire alarm cabling rule)."""
    d = ni.description.lower()
    if "cable" in d:
        return True
    # Some DSR codes use 'wire' for small signal cables
    if "wire" in d and "copper" in d:
        return True
    return False


# =============================================================================
# Rule 1 – Fire pipes require pump and/or tank
# =============================================================================

def rule_fire_pipes_require_pump_and_or_tank(items: Sequence[Any]) -> List[RuleResult]:
    """
    If hydrant / sprinkler / fire main pipes exist, check that there is at least
    a fire pump OR a dedicated fire water tank in the BOQ.

    This is a high-level completeness check; actual sizing is handled by
    design, but at least one pump/tank item should be visible for audit.
    """
    norm = _normalise_fire_items(items)
    if not norm:
        return []

    has_fire_pipes = any(_is_fire_pipe(ni) for ni in norm)
    has_fire_pump = any(_is_fire_pump(ni) for ni in norm)
    has_fire_tank = any(_is_fire_tank(ni) for ni in norm)

    results: List[RuleResult] = []
    if has_fire_pipes and not (has_fire_pump or has_fire_tank):
        results.append(
            RuleResult(
                level="WARNING",
                discipline="civil",  # may be split later into 'fire'
                code="FIRE-DEP-001",
                message=(
                    "Hydrant/sprinkler/fire-main piping items are present but no "
                    "fire pump or dedicated fire water tank items are found. "
                    "Fire-fighting systems normally require at least one fire "
                    "pump-set and adequate fire water storage."
                ),
            )
        )

    return results


# =============================================================================
# Rule 2 – Fire alarm devices require panels
# =============================================================================

def rule_fire_alarm_requires_panel(items: Sequence[Any]) -> List[RuleResult]:
    """
    If any field fire alarm devices (smoke/heat detectors, MCPs, hooters) are
    present, there should be at least one fire alarm panel.

    This catches BOQs where detectors and MCPs are listed but the control
    panel itself is missing.
    """
    norm = _normalise_fire_items(items)
    if not norm:
        return []

    has_devices = any(_is_fire_alarm_device(ni) for ni in norm)
    has_panel = any(_is_fire_alarm_panel(ni) for ni in norm)

    results: List[RuleResult] = []
    if has_devices and not has_panel:
        results.append(
            RuleResult(
                level="WARNING",
                discipline="electrical",
                code="FIRE-ALARM-001",
                message=(
                    "Fire alarm field devices (smoke/heat detectors, MCPs, hooters) "
                    "are present but no fire alarm panel item is found. "
                    "A fire alarm system should include a main panel/control unit."
                ),
            )
        )

    return results


# =============================================================================
# Rule 3 – Fire alarm devices require cabling
# =============================================================================

def rule_fire_alarm_requires_cables(items: Sequence[Any]) -> List[RuleResult]:
    """
    If fire alarm devices exist, there should be at least some cable items
    in the BOQ. This is a coarse check and does not ensure FRLS specifics.

    We look for:
        - any _is_fire_alarm_device(...)
        - any _is_cable(...)
    """
    norm = _normalise_fire_items(items)
    if not norm:
        return []

    has_devices = any(_is_fire_alarm_device(ni) for ni in norm)
    has_cables = any(_is_cable(ni) for ni in norm)

    results: List[RuleResult] = []
    if has_devices and not has_cables:
        results.append(
            RuleResult(
                level="WARNING",
                discipline="electrical",
                code="FIRE-ALARM-002",
                message=(
                    "Fire alarm devices (smoke/heat/MCP/hooter) are present but "
                    "no cable items appear in the BOQ. Fire alarm systems "
                    "require suitable cabling for detection and signaling."
                ),
            )
        )

    return results


# =============================================================================
# Rule 4 – Phase reasonableness for fire systems
# =============================================================================

def rule_fire_phase_reasonable(items: Sequence[Any]) -> List[RuleResult]:
    """
    Check that fire system components are not placed entirely in early phases
    (Substructure/Plinth).

    We expect most fire system items to be in:
        - "3️⃣ SUPERSTRUCTURE"  (mains & risers)
        - "4️⃣ FINISHING"       (heads, devices, valve fittings)

    WARN if:
    - majority of value for fire-relevant items (pipes, pumps, fire alarm
      devices, etc.) is in '1️⃣ SUBSTRUCTURE' or '2️⃣ PLINTH'.
    """
    norm = _normalise_fire_items(items)
    if not norm:
        return []

    # Determine "fire-relevant" entries
    fire_related: List[_NormFireItem] = []
    for ni in norm:
        if _is_fire_pipe(ni) or _is_fire_pump(ni) or _is_fire_tank(ni) or _is_fire_alarm_device(ni) or _is_fire_alarm_panel(ni):
            fire_related.append(ni)

    if not fire_related:
        return []

    amount_by_phase: Dict[str, float] = {}
    for ni in fire_related:
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
                discipline="civil",
                code="FIRE-PHASE-001",
                message=(
                    "More than 50% of fire system BOQ value is assigned to "
                    "Substructure/Plinth phases. Typically, fire mains, "
                    "sprinklers, hydrants, and alarm devices should be "
                    "associated mostly with Superstructure/Finishing phases; "
                    "check phase assignments."
                ),
            )
        )

    return results


# =============================================================================
# Aggregate: list of all fire rules
# =============================================================================

ALL_FIRE_RULES: List[RuleFn] = [
    rule_fire_pipes_require_pump_and_or_tank,
    rule_fire_alarm_requires_panel,
    rule_fire_alarm_requires_cables,
    rule_fire_phase_reasonable,
]


def run_fire_rules(items: Sequence[Any]) -> List[RuleResult]:
    """
    Convenience function to run all fire rules on a given
    list of BOQLine / dicts.

    Returns
    -------
    list[RuleResult]
    """
    all_results: List[RuleResult] = []
    for rule in ALL_FIRE_RULES:
        try:
            all_results.extend(rule(items))
        except Exception:
            # Fail-safe: ignore individual rule failure and continue.
            continue
    return all_results
```
