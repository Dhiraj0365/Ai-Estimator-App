# engines/bbs_engine.py
"""
Simple Bar Bending Schedule (BBS) engine for RCC beams.

This version supports:
- Straight top & bottom bars (no curtailment / crank)
- Closed rectangular stirrups with constant spacing

Formulas are based on standard practice / SP-34:
- Unit weight of bar (kg/m) = d^2 / 162, where d is dia in mm.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict


@dataclass
class Bar:
    mark: str         # e.g. "B1", "T1", "S1"
    dia_mm: float
    count: int
    length_m: float   # length of one bar (centre-to-centre length)
    shape: str = "Straight"

    @property
    def unit_weight_kg_per_m(self) -> float:
        # IS standard: W = d^2 / 162, d in mm
        return (self.dia_mm ** 2) / 162.0

    @property
    def total_length_m(self) -> float:
        return self.count * self.length_m

    @property
    def weight_kg(self) -> float:
        return self.total_length_m * self.unit_weight_kg_per_m


def simple_beam_bbs(
    span_clear_m: float,
    beam_width_m: float,
    beam_depth_m: float,
    cover_m: float,
    bottom_dia_mm: float,
    bottom_count: int,
    top_dia_mm: float,
    top_count: int,
    dev_len_m: float,
    stirrup_dia_mm: float,
    stirrup_leg_count: int,
    stirrup_spacing_mm: float,
) -> List[Bar]:
    """
    Generate a simple BBS for a prismatic RCC beam with:
    - Straight top & bottom bars (full length)
    - Uniform stirrups

    All inputs in SI units except dia/spacing in mm.

    ASSUMPTIONS:
    - Development length dev_len_m is same for top & bottom, at both ends.
    - Stirrups are rectangular with given leg count (typically 4).
    - Hooks etc. are approximated via effective perimeter; this is a simple model.

    This is suitable for quick estimates; for final drawings, a full
    detailed BBS per member is still required.
    """

    bars: List[Bar] = []

    # 1. Main bottom bars – mark B1
    main_length_m = span_clear_m + 2.0 * dev_len_m
    bars.append(
        Bar(
            mark="B1",
            dia_mm=bottom_dia_mm,
            count=bottom_count,
            length_m=main_length_m,
            shape="Straight",
        )
    )

    # 2. Main top bars – mark T1
    bars.append(
        Bar(
            mark="T1",
            dia_mm=top_dia_mm,
            count=top_count,
            length_m=main_length_m,
            shape="Straight",
        )
    )

    # 3. Stirrups – mark S1
    # Effective stirrup dimensions (centre-line) roughly:
    core_width_m = beam_width_m - 2.0 * cover_m
    core_depth_m = beam_depth_m - 2.0 * cover_m

    # Basic perimeter
    stirrup_perimeter_m = 2.0 * (core_width_m + core_depth_m)

    # Very simple hook allowance (2 hooks × 8d) in metres
    hook_allowance_m = 2.0 * (8.0 * stirrup_dia_mm / 1000.0)
    stirrup_length_m = stirrup_perimeter_m + hook_allowance_m

    # Number of stirrups = span / spacing + 1
    n_stirrups = int(span_clear_m * 1000.0 / stirrup_spacing_mm) + 1
    bars.append(
        Bar(
            mark="S1",
            dia_mm=stirrup_dia_mm,
            count=n_stirrups,
            length_m=stirrup_length_m,
            shape="Closed stirrup",
        )
    )

    return bars


def summarise_bars_by_dia(bars: List[Bar]) -> Dict[float, float]:
    """
    Summarise total steel weight kg per bar diameter.
    Returns {dia_mm: total_weight_kg}.
    """
    summary: Dict[float, float] = {}
    for b in bars:
        summary[b.dia_mm] = summary.get(b.dia_mm, 0.0) + b.weight_kg
    return summary
