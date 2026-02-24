from __future__ import annotations

"""
Rules Runner – Aggregate all discipline-specific rule engines

This module provides a single entry point to run:

- Civil rules
- Electrical rules
- Plumbing rules
- Fire-fighting rules
- HVAC rules

against the current BOQ / SOQ list and return a combined list of
RuleResult objects.

It is UI-agnostic and can be used from:
- Streamlit app (Audit tab)
- CLI tools
- Tests

USAGE
-----

    from rules.rules_runner import run_all_rules

    # `items` can be a list[BOQLine] or list[dict] (legacy)
    results = run_all_rules(st.session_state.qto_items)

    for r in results:
        print(r.level, r.discipline, r.code, r.message)

You can also selectively include disciplines:

    results = run_all_rules(items, include_disciplines={"civil", "electrical"})
"""

from typing import List, Dict, Any, Optional, Sequence

from core.models import RuleResult

from rules.rules_civil import run_civil_rules
from rules.rules_elec import run_elec_rules
from rules.rules_plumbing import run_plumbing_rules
from rules.rules_fire import run_fire_rules
from rules.rules_hvac import run_hvac_rules


# =============================================================================
# Main aggregator
# =============================================================================

def run_all_rules(
    items: Sequence[Any],
    include_disciplines: Optional[set[str]] = None,
) -> List[RuleResult]:
    """
    Run all configured rule engines (civil, electrical, plumbing, fire, HVAC)
    on the given list of BOQLine / dicts and return a combined result list.

    Parameters
    ----------
    items : Sequence[Any]
        List of BOQLine or dict entries representing current BOQ/SOQ.
    include_disciplines : set[str] or None
        Optional filter for which disciplines to include. Discipline names:
            "civil", "electrical", "plumbing", "fire", "hvac"
        If None, all are run.

    Returns
    -------
    list[RuleResult]
    """
    if include_disciplines is not None:
        include_disciplines = {d.lower() for d in include_disciplines}

    all_results: List[RuleResult] = []

    # Civil
    if include_disciplines is None or "civil" in include_disciplines:
        try:
            all_results.extend(run_civil_rules(items))
        except Exception:
            # Fail-safe: ignore, continue with other disciplines
            pass

    # Electrical
    if include_disciplines is None or "electrical" in include_disciplines:
        try:
            all_results.extend(run_elec_rules(items))
        except Exception:
            pass

    # Plumbing
    if include_disciplines is None or "plumbing" in include_disciplines:
        try:
            all_results.extend(run_plumbing_rules(items))
        except Exception:
            pass

    # Fire
    if include_disciplines is None or "fire" in include_disciplines:
        try:
            all_results.extend(run_fire_rules(items))
        except Exception:
            pass

    # HVAC
    if include_disciplines is None or "hvac" in include_disciplines:
        try:
            all_results.extend(run_hvac_rules(items))
        except Exception:
            pass

    return all_results


# =============================================================================
# Optional helpers – grouping and summary
# =============================================================================

def group_results_by_discipline(results: List[RuleResult]) -> Dict[str, List[RuleResult]]:
    """
    Group RuleResult items by discipline.

    Returns
    -------
    dict : {discipline -> list[RuleResult]}
    """
    out: Dict[str, List[RuleResult]] = {}
    for r in results:
        d = (r.discipline or "unknown").lower()
        out.setdefault(d, []).append(r)
    return out


def group_results_by_level(results: List[RuleResult]) -> Dict[str, List[RuleResult]]:
    """
    Group RuleResult items by level ("ERROR", "WARNING", "INFO").

    Returns
    -------
    dict : {level -> list[RuleResult]}
    """
    out: Dict[str, List[RuleResult]] = {}
    for r in results:
        lvl = (r.level or "INFO").upper()
        out.setdefault(lvl, []).append(r)
    return out
```
