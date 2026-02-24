# core/pricing.py

from __future__ import annotations

"""
Pricing utilities for the estimator.

This module centralises:
- Location index application (CPWD cost indices, State indices).
- Contingency / overhead / profit / escalation / tax layering on base DSR rates.
- Convenience helpers to price BOQ lines.
- Simple Monte-Carlo style risk envelope around a base amount.

It is intentionally UI-agnostic (no Streamlit imports) so it can be
used from CLI, tests, or any front end.
"""

from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional, List, Tuple

import numpy as np

from core.models import Item, BOQLine


# =============================================================================
# PriceBreakdown – breakdown of rate build-up
# =============================================================================

@dataclass
class PriceBreakdown:
    """
    Detailed rate build-up for one DSR/SoR item.

    All percentages are given as %, not fraction (e.g. 5.0 means 5%).

    Fields
    ------
    base_rate           : float - DSR/SoR rate at base index (e.g. Delhi 100).
    location_index      : float - cost index (100 = base, 110 = 10% higher).
    indexed_rate        : float - base_rate adjusted by location_index.
    contingency_pct     : float
    overhead_pct        : float
    profit_pct          : float
    escalation_pct      : float - total escalation % (already compounded for years).
    tax_pct             : float - e.g. GST or combined indirect tax %.
    # Derived:
    contingency_amount  : float
    overhead_amount     : float
    profit_amount       : float
    escalation_amount   : float
    tax_amount          : float
    final_rate          : float - fully loaded rate including all above.
    meta                : dict  - free-form additional info (e.g., years, base_date, target_date).
    """

    base_rate: float
    location_index: float
    indexed_rate: float

    contingency_pct: float = 0.0
    overhead_pct: float = 0.0
    profit_pct: float = 0.0
    escalation_pct: float = 0.0
    tax_pct: float = 0.0

    contingency_amount: float = 0.0
    overhead_amount: float = 0.0
    profit_amount: float = 0.0
    escalation_amount: float = 0.0
    tax_amount: float = 0.0

    final_rate: float = 0.0

    meta: Dict[str, Any] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# =============================================================================
# Basic helpers
# =============================================================================

def apply_location_index(base_rate: float, cost_index: float) -> float:
    """
    Apply a location cost index to a base rate.

    Example:
        base_rate = 100.0 (Delhi 100 index)
        cost_index = 110.0  →  rate = 110.0
    """
    return float(base_rate) * (float(cost_index) / 100.0)


def _apply_pct(base: float, pct: float) -> float:
    """Return base * (pct / 100.0)."""
    return float(base) * float(pct) / 100.0


# =============================================================================
# Rate build-up functions
# =============================================================================

def build_price_breakdown(
    base_rate: float,
    cost_index: float,
    contingency_pct: float = 0.0,
    overhead_pct: float = 0.0,
    profit_pct: float = 0.0,
    escalation_pct: float = 0.0,
    tax_pct: float = 0.0,
    meta: Optional[Dict[str, Any]] = None,
) -> PriceBreakdown:
    """
    Compute a fully loaded rate from a base DSR/SoR rate, applying:

    - Location index
    - Contingency (% of indexed rate)
    - Overheads (% of (indexed + contingency))
    - Profit (% of (indexed + contingency + overhead))
    - Escalation (% of subtotal so far)
    - Tax (% of subtotal so far)

    All % inputs are simple, not compounded here (except escalation for years
    if you precompute escalation_pct externally).

    Returns a PriceBreakdown object.
    """
    base_rate = float(base_rate)
    cost_index = float(cost_index)

    indexed = apply_location_index(base_rate, cost_index)

    # 1) Contingency on indexed rate
    cont_amt = _apply_pct(indexed, contingency_pct)
    after_cont = indexed + cont_amt

    # 2) Overheads on (indexed + contingency)
    oh_amt = _apply_pct(after_cont, overhead_pct)
    after_oh = after_cont + oh_amt

    # 3) Profit on (indexed + contingency + overhead)
    profit_amt = _apply_pct(after_oh, profit_pct)
    after_profit = after_oh + profit_amt

    # 4) Escalation on subtotal so far
    esc_amt = _apply_pct(after_profit, escalation_pct)
    after_esc = after_profit + esc_amt

    # 5) Tax (GST, etc.) on subtotal so far
    tax_amt = _apply_pct(after_esc, tax_pct)
    final_rate = after_esc + tax_amt

    return PriceBreakdown(
        base_rate=base_rate,
        location_index=cost_index,
        indexed_rate=indexed,
        contingency_pct=contingency_pct,
        overhead_pct=overhead_pct,
        profit_pct=profit_pct,
        escalation_pct=escalation_pct,
        tax_pct=tax_pct,
        contingency_amount=cont_amt,
        overhead_amount=oh_amt,
        profit_amount=profit_amt,
        escalation_amount=esc_amt,
        tax_amount=tax_amt,
        final_rate=final_rate,
        meta=meta or {},
    )


def escalation_percent_for_years(
    annual_pct: float,
    years: float,
    compound: bool = True,
) -> float:
    """
    Compute a total escalation percentage over a given number of years.

    If compound=True:
        total = ((1 + annual_pct/100) ** years - 1) * 100

    Else:
        total = annual_pct * years

    Returns a % (not factor).
    """
    annual = float(annual_pct)
    years = float(years)

    if years <= 0.0 or annual <= 0.0:
        return 0.0

    if compound:
        factor = (1.0 + annual / 100.0) ** years - 1.0
        return factor * 100.0
    else:
        return annual * years


# =============================================================================
# Item & BOQLine pricing helpers
# =============================================================================

def effective_rate_for_item(
    item: Item,
    cost_index: float,
    contingency_pct: float = 0.0,
    overhead_pct: float = 0.0,
    profit_pct: float = 0.0,
    escalation_pct: float = 0.0,
    tax_pct: float = 0.0,
    meta: Optional[Dict[str, Any]] = None,
) -> PriceBreakdown:
    """
    Convenience wrapper around build_price_breakdown for an Item.

    Example:
        bd = effective_rate_for_item(item, 110.0, contingency_pct=3, overhead_pct=10, profit_pct=10)
        rate_to_use = bd.final_rate
    """
    return build_price_breakdown(
        base_rate=item.base_rate,
        cost_index=cost_index,
        contingency_pct=contingency_pct,
        overhead_pct=overhead_pct,
        profit_pct=profit_pct,
        escalation_pct=escalation_pct,
        tax_pct=tax_pct,
        meta=meta,
    )


def price_boq_line(
    item: Item,
    quantity: float,
    cost_index: float,
    contingency_pct: float = 0.0,
    overhead_pct: float = 0.0,
    profit_pct: float = 0.0,
    escalation_pct: float = 0.0,
    tax_pct: float = 0.0,
    phase: str = "",
    source: str = "single_item",
    notes: str = "",
    length: float = 0.0,
    breadth: float = 0.0,
    depth: float = 0.0,
    height: float = 0.0,
    extra_meta: Optional[Dict[str, Any]] = None,
) -> Tuple[BOQLine, PriceBreakdown]:
    """
    Produce a BOQLine and corresponding PriceBreakdown for a given Item and quantity.

    This is a one-stop helper if you want to price and create a BOQ line in one step.

    NOTE:
    - You still need to assign a line ID externally (e.g. via Project.next_line_id()).
    """
    qb = effective_rate_for_item(
        item=item,
        cost_index=cost_index,
        contingency_pct=contingency_pct,
        overhead_pct=overhead_pct,
        profit_pct=profit_pct,
        escalation_pct=escalation_pct,
        tax_pct=tax_pct,
        meta=extra_meta,
    )

    qty = float(quantity)
    rate = qb.final_rate
    amount = qty * rate

    line = BOQLine.from_item(
        line_id=0,  # caller should update ID (e.g., after calling Project.next_line_id())
        item=item,
        phase=phase or "",
        quantity=qty,
        rate=rate,
        amount=amount,
        source=source,
        notes=notes,
        length=length,
        breadth=breadth,
        depth=depth,
        height=height,
        meta=extra_meta or {},
    )
    return line, qb


# =============================================================================
# Monte Carlo risk envelope
# =============================================================================

def monte_carlo_amount(
    base_amount: float,
    n: int = 1000,
    risk_scenarios: Optional[List[Tuple[float, float]]] = None,
    seed: int = 42,
) -> Dict[str, float]:
    """
    Simple Monte-Carlo style risk analysis around a base amount.

    Parameters
    ----------
    base_amount : float
        Deterministic base estimate (e.g., total project cost).
    n : int
        Number of simulation runs.
    risk_scenarios : list of (probability, impact_pct)
        Each tuple:
            probability (0–1), impact_pct (>0) as +% cost if event occurs.
        Example:
            [(0.30, 0.10), (0.20, 0.20)]
            means: 30% chance of +10%, 20% chance of +20%.
    seed : int
        Random seed for repeatability.

    Returns
    -------
    dict with keys: p10, p50, p90
    """
    base = float(base_amount)
    if base <= 0.0 or n <= 0:
        return {"p10": 0.0, "p50": 0.0, "p90": 0.0}

    if risk_scenarios is None:
        # Default scenarios similar to what you used in the app
        risk_scenarios = [
            (0.30, 0.12),
            (0.25, 0.15),
            (0.20, 0.25),
        ]

    sims = np.full(n, base, dtype=np.float64)
    rng = np.random.default_rng(seed)

    for prob, impact_pct in risk_scenarios:
        prob = float(prob)
        impact = float(impact_pct)
        mask = rng.random(n) < prob
        sims[mask] *= (1.0 + impact)

    return {
        "p10": float(np.percentile(sims, 10)),
        "p50": float(np.percentile(sims, 50)),
        "p90": float(np.percentile(sims, 90)),
    }
