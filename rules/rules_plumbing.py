from __future__ import annotations

"""
Plumbing Rules Engine – Basic Dependency & Sanity Checks

This module defines *plumbing-only* validation / audit rules that work
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

- 'pipes'        : PVC/SWR/CI/HDPE pipes (water & drainage).
- 'sanitary'     : WCs, basins, urinals, sinks, traps, floor traps, gully traps.
- 'cp_fittings'  : C.P. brass taps, mixers, valves, etc.

RULES IMPLEMENTED
-----------------
1. rule_plumb_fixtures_require_drain_pipes
   - WARN if sanitary fixtures exist but no drainage pipe items (SWR/PVC/CI).

2. rule_plumb_fixtures_require_traps
   - WARN if fixtures (WCs, basins, sinks) exist but there are no traps/floor traps/
     nahani traps/gully traps.

3. rule_plumb_pipes_require_fixtures_or_outlets
   - WARN if there are many plumbing pipes but almost no fixtures/outlets (sanitary
     or CP fittings) – suggests incomplete BOQ.

4. rule_plumb_phase_reasonable
   - WARN if most plumbing value is in Substructure/Plinth instead of
     Superstructure/Finishing (typical mis-phasing).

You can extend this module with more rules (e.g., minimum pipe diameters,
vent stacks, etc.) as your model matures.
"""

from dataclasses import dataclass
from typing import List, Dict, Any, Callable, Sequence

from core.models import RuleResult, BOQLine


# =============================================================================
# Internal helper to normalise entries
# =============================================================================

@dataclass
class _NormPlumbItem:
    """Normalised view over BOQLine or dict entry for plumbing rule checks."""
    id: int
    phase: str
    discipline: str
    category: str
    description: str
    code: str
    amount: float


def _normalise_plumb_items(items: Sequence[Any]) -> List[_NormPlumbItem]:
    """
    Convert list of BOQLine or dict entries into a list of _NormPlumbItem,
    filtering to `discipline == 'plumbing'` OR category one of plumbing
    categories when discipline is not set.

    Supports:
    - core.models.BOQLine
    - dicts with keys: 'id', 'phase', 'discipline', 'category',
      'description' (or 'item'), 'dsr_code'/'code', 'amount'.
    """
    norm: List[_NormPlumbItem] = []
    for src in items:
        if isinstance(src, BOQLine):
            disc = (src.discipline or "").lower()
            cat = (src.category or "").lower()
            # Accept lines explicitly marked as plumbing, or that have classic
            # plumbing categories even if discipline not set.
            if disc not in ("", "plumbing") and cat not in {"pipes", "sanitary", "cp_fittings"}:
                continue
            n = _NormPlumbItem(
                id=src.id,
                phase=str(src.phase or ""),
                discipline="plumbing",
                category=cat,
                description=str(src.description or ""),
                code=str(src.item.code if src.item else ""),
                amount=float(src.amount or 0.0),
            )
        elif isinstance(src, dict):
            disc = str(src.get("discipline", "")).lower()
            cat = str(src.get("category", "")).lower()
            if disc not in ("", "plumbing") and cat not in {"pipes", "sanitary", "cp_fittings"}:
                continue
            desc = str(
                src.get("description")
                or src.get("item")
                or src.get("item_key")
                or ""
            )
            n = _NormPlumbItem(
                id=int(src.get("id", 0)),
                phase=str(src.get("phase", "")),
                discipline="plumbing",
                category=cat,
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
# Rule 1 – Sanitary fixtures require drainage pipes
# =============================================================================

def rule_plumb_fixtures_require_drain_pipes(items: Sequence[Any]) -> List[RuleResult]:
    """
    If there are sanitary fixtures (WCs, basins, urinals, sinks, etc.
    category 'sanitary'), check that at least one drainage pipe item
    (category 'pipes' with SWR/PVC/CI description) is present.

    This catches BOQs where fixtures are listed but drainage pipework
    is completely missing.
    """
    norm = _normalise_plumb_items(items)
    if not norm:
        return []

    # Determine fixtures and drainage pipes
    has_fixtures = any(ni.category == "sanitary" for ni in norm)

    def _is_drain_pipe(ni: _NormPlumbItem) -> bool:
        if ni.category != "pipes":
            return False
        d = ni.description.lower()
        return any(word in d for word in ("swr", "soil", "waste", "drain", "p.v.c", "pvc"))

    has_drain_pipes = any(_is_drain_pipe(ni) for ni in norm)

    results: List[RuleResult] = []
    if has_fixtures and not has_drain_pipes:
        results.append(
            RuleResult(
                level="WARNING",
                discipline="plumbing",
                code="PLUMB-DEP-001",
                message=(
                    "Sanitary fixtures (WCs/basins/urinals/sinks) are present but "
                    "no drainage pipe items (SWR/PVC/soil/waste) are found. "
                    "Drainage pipework for soil/waste should be included."
                ),
            )
        )

    return results


# =============================================================================
# Rule 2 – Fixtures require traps / floor traps
# =============================================================================

def rule_plumb_fixtures_require_traps(items: Sequence[Any]) -> List[RuleResult]:
    """
    If there are fixtures (WCs, basins, sinks, etc.), check that some trap
    items exist:

    - Floor traps
    - Nahani traps
    - Gully traps
    - Bottle traps / bottle waste for basins/sinks

    Detection via description text; categories remain 'sanitary'.
    """
    norm = _normalise_plumb_items(items)
    if not norm:
        return []

    # Fixtures that normally need traps
    def _is_fixture(ni: _NormPlumbItem) -> bool:
        if ni.category != "sanitary":
            return False
        d = ni.description.lower()
        return any(
            word in d
            for word in ("w.c", "wc", "closet", "wash basin", "lavatory", "sink", "urinal")
        )

    has_fixtures = any(_is_fixture(ni) for ni in norm)

    # Trap presence by description
    def _is_trap(ni: _NormPlumbItem) -> bool:
        if ni.category != "sanitary" and ni.category != "pipes":
            return False
        d = ni.description.lower()
        return any(word in d for word in ("trap", "gully trap", "nahani", "floor trap", "bottle trap"))

    has_traps = any(_is_trap(ni) for ni in norm)

    results: List[RuleResult] = []
    if has_fixtures and not has_traps:
        results.append(
            RuleResult(
                level="WARNING",
                discipline="plumbing",
                code="PLUMB-DEP-002",
                message=(
                    "Sanitary fixtures (WCs/basins/sinks/urinals) are present "
                    "but no trap items (floor traps, nahani traps, gully traps, "
                    "bottle traps) are present. Fixture outlets should normally "
                    "include appropriate traps as per plumbing practice."
                ),
            )
        )

    return results


# =============================================================================
# Rule 3 – Pipes require fixtures or outlets
# =============================================================================

def rule_plumb_pipes_require_fixtures_or_outlets(items: Sequence[Any]) -> List[RuleResult]:
    """
    If there is a substantial amount of piping but almost no sanitary/CP
    fixtures, raise a warning.

    This indicates the BOQ might list main piping but forget fixtures/taps.
    """
    norm = _normalise_plumb_items(items)
    if not norm:
        return []

    amount_pipes = sum(ni.amount for ni in norm if ni.category == "pipes")
    amount_fixtures = sum(ni.amount for ni in norm if ni.category in {"sanitary", "cp_fittings"})

    total = amount_pipes + amount_fixtures
    if total <= 0.0:
        return []

    share_pipes = amount_pipes / total if total > 0 else 0.0

    results: List[RuleResult] = []

    # If >75% of plumbing value is pipes and fixtures are almost absent
    if share_pipes > 0.75 and amount_fixtures < 0.1 * amount_pipes:
        results.append(
            RuleResult(
                level="WARNING",
                discipline="plumbing",
                code="PLUMB-DEP-003",
                message=(
                    "Plumbing BOQ is dominated by pipe items with very few "
                    "sanitary fixtures or CP fittings. Check that WCs, basins, "
                    "sinks, urinals, taps, valves etc. have been included."
                ),
            )
        )

    return results


# =============================================================================
# Rule 4 – Phase reasonableness for plumbing
# =============================================================================

def rule_plumb_phase_reasonable(items: Sequence[Any]) -> List[RuleResult]:
    """
    Check that plumbing items are not placed entirely in early phases
    (Substructure/Plinth).

    We expect most plumbing items to be in:
        - "3️⃣ SUPERSTRUCTURE"  (vertical risers, shafts)
        - "4️⃣ FINISHING"       (fixtures, branch pipes, CP fittings)

    WARN if:
    - majority of plumbing value by amount is in '1️⃣ SUBSTRUCTURE'
      or '2️⃣ PLINTH'.
    """
    norm = _normalise_plumb_items(items)
    if not norm:
        return []

    amount_by_phase: Dict[str, float] = {}
    for ni in norm:
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
                discipline="plumbing",
                code="PLUMB-PHASE-001",
                message=(
                    "More than 50% of plumbing BOQ value is assigned to "
                    "Substructure/Plinth phases. Typically, plumbing work "
                    "should fall mostly under Superstructure/Finishing phases; "
                    "check phase assignments."
                ),
            )
        )

    return results


# =============================================================================
# Aggregate: list of all plumbing rules
# =============================================================================

ALL_PLUMB_RULES: List[RuleFn] = [
    rule_plumb_fixtures_require_drain_pipes,
    rule_plumb_fixtures_require_traps,
    rule_plumb_pipes_require_fixtures_or_outlets,
    rule_plumb_phase_reasonable,
]


def run_plumbing_rules(items: Sequence[Any]) -> List[RuleResult]:
    """
    Convenience function to run all plumbing rules on a given
    list of BOQLine / dicts.

    Returns
    -------
    list[RuleResult]
    """
    all_results: List[RuleResult] = []
    for rule in ALL_PLUMB_RULES:
        try:
            all_results.extend(rule(items))
        except Exception:
            # Fail-safe: ignore individual rule failure and continue.
            continue
    return all_results
```
