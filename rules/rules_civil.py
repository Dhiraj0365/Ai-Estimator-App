```python
# rules/rules_civil.py

from __future__ import annotations

"""
Civil Rules Engine – Sequencing, Dependencies, IS-Code Style Checks

This module defines *civil-only* validation / audit rules that work on the
current BOQ / SOQ and return a list of RuleResult objects.

It is UI-agnostic and can be used from:
- rules_runner.py
- Streamlit app (Abstract / Audit tab)
- Tests

INPUT
-----
We support both:
- List[core.models.BOQLine], or
- List[dict]  (legacy st.session_state.qto_items format)

Each rule receives this list and returns a list[RuleResult].

RULES IMPLEMENTED
-----------------
1. rule_phase_sequence
   - Warns if phases are "jumped" (e.g., SUPSTRUCT without SUBSTRUCT/PLINTH).
   - Warns if FINISHING present but no SUPERSTRUCTURE.

2. rule_finishing_requires_structure
   - Warns if finishing items exist (plaster/tiles/painting/flooring/etc.)
     but no structural items (concrete/brickwork/stone masonry) at all.

3. rule_plaster_requires_masonry_or_concrete
   - Warns if plaster items exist without any brickwork/stone/concrete.

4. rule_paint_requires_plaster_or_putty
   - Warns if painting items exist without any plaster/putty base.

5. rule_earthwork_requires_backfill
   - Warns if there is excavation earthwork but no backfill item.

6. rule_min_concrete_grade_for_rcc
   - Warns if items suggest RCC structural concrete below M20 for beams/slabs/
     columns (based on description) contrary to IS 456 typical practice.

Extend / add rules here as needed.
"""

from dataclasses import dataclass
from typing import List, Dict, Any, Callable, Sequence

from core.models import RuleResult, BOQLine


# =============================================================================
# Internal helpers
# =============================================================================

@dataclass
class _NormItem:
    """Normalised view over BOQLine or dict entry for rule checks."""
    id: int
    phase: str
    discipline: str
    category: str
    description: str
    code: str
    amount: float


def _normalise_items(items: Sequence[Any]) -> List[_NormItem]:
    """
    Convert list of BOQLine or dict entries into a list of _NormItem
    with safe default values.

    Supports:
    - core.models.BOQLine
    - dicts with keys: 'id', 'phase', 'discipline', 'category',
      'description' (or 'item'), 'dsr_code'/'code', 'amount'.
    """
    norm: List[_NormItem] = []
    for src in items:
        if isinstance(src, BOQLine):
            n = _NormItem(
                id=src.id,
                phase=str(src.phase or ""),
                discipline=str(src.discipline or "civil"),
                category=str(src.category or "").lower(),
                description=str(src.description or ""),
                code=str(src.item.code if src.item else ""),
                amount=float(src.amount or 0.0),
            )
        elif isinstance(src, dict):
            # Legacy dict format from older app
            desc = str(
                src.get("description")
                or src.get("item")
                or src.get("item_key")
                or ""
            )
            n = _NormItem(
                id=int(src.get("id", 0)),
                phase=str(src.get("phase", "")),
                discipline=str(src.get("discipline", "civil")),
                category=str(src.get("category", "")).lower(),
                description=desc,
                code=str(src.get("code") or src.get("dsr_code") or ""),
                amount=float(src.get("amount", 0.0) or 0.0),
            )
        else:
            # Unknown type – skip
            continue

        norm.append(n)
    return norm


# Map for phase sequencing checks
_PHASE_ORDER = {
    "1️⃣ SUBSTRUCTURE": 1,
    "2️⃣ PLINTH": 2,
    "3️⃣ SUPERSTRUCTURE": 3,
    "4️⃣ FINISHING": 4,
}


RuleFn = Callable[[Sequence[Any]], List[RuleResult]]


# =============================================================================
# Rule 1 – Phase sequence (Substructure → Plinth → Superstructure → Finishing)
# =============================================================================

def rule_phase_sequence(items: Sequence[Any]) -> List[RuleResult]:
    """
    Check that phases generally follow:
        1️⃣ SUBSTRUCTURE → 2️⃣ PLINTH → 3️⃣ SUPERSTRUCTURE → 4️⃣ FINISHING

    Flags:
    - WARNING if FINISHING exists but SUPERSTRUCTURE absent.
    - WARNING if SUPERSTRUCTURE exists but SUBSTRUCTURE/PLINTH entirely absent.
    - WARNING if there is a "jump" in phases (e.g. 1 & 3 but no 2).
    """
    norm = _normalise_items(items)
    if not norm:
        return []

    phases_present = {ni.phase for ni in norm if ni.phase}
    order_values = sorted({_PHASE_ORDER.get(p, 0) for p in phases_present if p in _PHASE_ORDER})

    results: List[RuleResult] = []

    # Jump check: if we have e.g. 1 and 3 but not 2
    if order_values:
        expected = set(range(min(order_values), max(order_values) + 1))
        if expected != set(order_values):
            results.append(
                RuleResult(
                    level="WARNING",
                    discipline="civil",
                    code="CIV-PHASE-001",
                    message=(
                        "Construction phases appear out of logical sequence. "
                        "Expected continuous sequence from Substructure → Plinth → "
                        "Superstructure → Finishing without skipping intermediate phases."
                    ),
                )
            )

    # Finishing without superstructure
    if "4️⃣ FINISHING" in phases_present and "3️⃣ SUPERSTRUCTURE" not in phases_present:
        results.append(
            RuleResult(
                level="WARNING",
                discipline="civil",
                code="CIV-PHASE-002",
                message="Finishing items exist but no Superstructure items are present.",
            )
        )

    # Superstructure without substructure/plinth
    if "3️⃣ SUPERSTRUCTURE" in phases_present and "1️⃣ SUBSTRUCTURE" not in phases_present:
        results.append(
            RuleResult(
                level="WARNING",
                discipline="civil",
                code="CIV-PHASE-003",
                message="Superstructure items exist but no Substructure items are present.",
            )
        )

    return results


# =============================================================================
# Rule 2 – Finishing requires structure (no plaster/tiles/paint only)
# =============================================================================

def rule_finishing_requires_structure(items: Sequence[Any]) -> List[RuleResult]:
    """
    Check that finishing items (plaster, tiles, flooring, painting, false ceiling)
    are not present *without* any structural/masonry items.

    Structural categories considered:
        'concrete', 'brickwork', 'stone_masonry', 'steel_work', 'aluminium_work'
    Finishing categories considered:
        'plaster', 'tiles', 'flooring', 'painting', 'false_ceiling', 'doors', 'rolling_shutters'
    """
    norm = _normalise_items(items)
    if not norm:
        return []

    struct_cats = {"concrete", "brickwork", "stone_masonry", "steel_work", "aluminium_work"}
    finish_cats = {
        "plaster",
        "tiles",
        "flooring",
        "painting",
        "false_ceiling",
        "doors",
        "rolling_shutters",
    }

    has_struct = any(ni.category in struct_cats for ni in norm)
    has_finish = any(ni.category in finish_cats for ni in norm)

    results: List[RuleResult] = []

    if has_finish and not has_struct:
        results.append(
            RuleResult(
                level="WARNING",
                discipline="civil",
                code="CIV-DEP-001",
                message=(
                    "Finishing items (plaster/tiles/painting/flooring) are present "
                    "but no structural/masonry items exist. "
                    "Check that brickwork/stone/RCC structure has been included."
                ),
            )
        )

    return results


# =============================================================================
# Rule 3 – Plaster requires masonry or concrete
# =============================================================================

def rule_plaster_requires_masonry_or_concrete(items: Sequence[Any]) -> List[RuleResult]:
    """
    Check that plaster items are not used without any brickwork, stone masonry, or
    RCC/concrete items.

    Categories:
        plaster  -> requires any of {brickwork, stone_masonry, concrete}
    """
    norm = _normalise_items(items)
    if not norm:
        return []

    has_plaster = any(ni.category == "plaster" for ni in norm)
    has_base = any(ni.category in {"brickwork", "stone_masonry", "concrete"} for ni in norm)

    results: List[RuleResult] = []

    if has_plaster and not has_base:
        results.append(
            RuleResult(
                level="WARNING",
                discipline="civil",
                code="CIV-DEP-002",
                message=(
                    "Plaster items are present but no brickwork/stone masonry/concrete "
                    "items exist. Plaster should have a masonry or RCC base as per "
                    "IS 2212 and good practice."
                ),
            )
        )

    return results


# =============================================================================
# Rule 4 – Painting requires plaster or putty
# =============================================================================

def rule_paint_requires_plaster_or_putty(items: Sequence[Any]) -> List[RuleResult]:
    """
    Check that wall painting items are not used without plaster/putty base.

    Categories:
        painting -> requires any of {plaster, finishing with 'putty' in description}
    """
    norm = _normalise_items(items)
    if not norm:
        return []

    has_paint = any(ni.category == "painting" for ni in norm)
    has_plaster = any(ni.category == "plaster" for ni in norm)
    has_putty = any("putty" in ni.description.lower() for ni in norm)

    results: List[RuleResult] = []

    if has_paint and not (has_plaster or has_putty):
        results.append(
            RuleResult(
                level="WARNING",
                discipline="civil",
                code="CIV-DEP-003",
                message=(
                    "Painting items are present but no plaster/putty base is present. "
                    "Normally walls should receive plaster and wall putty before "
                    "emulsion or distemper painting."
                ),
            )
        )

    return results


# =============================================================================
# Rule 5 – Earthwork requires backfill
# =============================================================================

def rule_earthwork_requires_backfill(items: Sequence[Any]) -> List[RuleResult]:
    """
    Check that if there is excavation earthwork, there is also at least one
    backfilling item.

    Categories:
        excavation: category == 'earthwork' or 'earthwork_surface'
        backfill  : category == 'backfill'
    """
    norm = _normalise_items(items)
    if not norm:
        return []

    has_excavation = any(ni.category in {"earthwork", "earthwork_surface"} for ni in norm)
    has_backfill = any(ni.category == "backfill" for ni in norm)

    results: List[RuleResult] = []

    if has_excavation and not has_backfill:
        results.append(
            RuleResult(
                level="WARNING",
                discipline="civil",
                code="CIV-DEP-004",
                message=(
                    "Earthwork excavation items exist but no backfill items are "
                    "present. Normally, filling with available/borrow earth around "
                    "foundations/plinth is required."
                ),
            )
        )

    return results


# =============================================================================
# Rule 6 – Minimum concrete grade for RCC (IS 456 guidance)
# =============================================================================

def rule_min_concrete_grade_for_rcc(items: Sequence[Any]) -> List[RuleResult]:
    """
    Check that RCC elements (beams, slabs, columns) are not specified with
    concrete grade below M20, based on item description.

    This is a heuristic rule:
        - We look for category 'concrete' and description containing 'M15'
          along with 'slab'/'beam'/'column'/'RCC'.
        - If found, we warn that IS 456 generally requires M20 for RCC in
          flexure (beams/slabs) and columns.
    """
    norm = _normalise_items(items)
    if not norm:
        return []

    results: List[RuleResult] = []

    for ni in norm:
        if ni.category != "concrete":
            continue
        desc = ni.description.lower()
        # detect grade
        if "m15" in desc and any(w in desc for w in ("slab", "beam", "column", "r.c.c", "rcc")):
            results.append(
                RuleResult(
                    level="WARNING",
                    discipline="civil",
                    code="CIV-RCC-001",
                    message=(
                        f"Concrete item '{ni.description}' appears to use grade M15 "
                        "for an RCC structural member (beam/slab/column). "
                        "IS 456 generally requires minimum M20 grade for RCC in "
                        "flexure and columns."
                    ),
                    context={"id": ni.id, "code": ni.code},
                )
            )

    return results


# =============================================================================
# Aggregate: list of all civil rules
# =============================================================================

ALL_CIVIL_RULES: List[RuleFn] = [
    rule_phase_sequence,
    rule_finishing_requires_structure,
    rule_plaster_requires_masonry_or_concrete,
    rule_paint_requires_plaster_or_putty,
    rule_earthwork_requires_backfill,
    rule_min_concrete_grade_for_rcc,
]


def run_civil_rules(items: Sequence[Any]) -> List[RuleResult]:
    """
    Convenience function to run all civil rules on a given list of BOQLine / dicts.

    Returns
    -------
    list[RuleResult]
    """
    all_results: List[RuleResult] = []
    for rule in ALL_CIVIL_RULES:
        try:
            all_results.extend(rule(items))
        except Exception:
            # Fail-safe: ignore rule failure, continue with others
            continue
    return all_results
```
