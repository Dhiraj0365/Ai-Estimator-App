# engines/bbs_engine.py
"""
Simple Bar Bending Schedule (BBS) engine for RCC beams.

This module is designed for QUICK ESTIMATION, not for detailed
reinforcement design drawings. It assumes:

- A single prismatic RCC beam.
- Straight top and bottom bars (no cranking / curtailment).
- Uniform closed stirrups over the full clear span.

Formulas:

- Unit weight of a bar (kg/m) = d² / 162  (IS practice; d in mm)
- Main bar length (m) = clear_span + 2 × development_length
- Stirrups:
    * Effective core width  = beam_width  – 2 × cover
    * Effective core depth  = beam_depth – 2 × cover
    * Centre-line perimeter = 2 × (core_width + core_depth)
    * Hook allowance        ≈ 2 × 8d (two hooks), d in m
    * Stirrup length (m)    = perimeter + hook_allowance
    * Number of stirrups    = int(clear_span_mm / spacing_mm) + 1

You already restrict inputs in the UI so spacing_mm > 0 etc.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict


@dataclass
class Bar:
    """
    One BBS bar mark.

    mark      : Bar mark (e.g. B1, T1, S1).
    dia_mm    : Bar diameter in mm.
    count     : Number of bars of this mark.
    length_m  : Length of ONE bar (in metres), centre-to-centre.
    shape     : Text description ("Straight", "Closed stirrup", etc.).
    """
    mark: str
    dia_mm: float
    count: int
    length_m: float
    shape: str = "Straight"

    @property
    def unit_weight_kg_per_m(self) -> float:
        """Unit weight (kg/m) using W = d² / 162, d in mm."""
        return (self.dia_mm ** 2) / 162.0

    @property
    def total_length_m(self) -> float:
        """Total length of all bars of this mark (m)."""
        return self.count * self.length_m

    @property
    def weight_kg(self) -> float:
        """Total weight (kg) of all bars of this mark."""
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
    stirrup_leg_count: int,   # kept for future refinement; not used directly here
    stirrup_spacing_mm: float,
) -> List[Bar]:
    """
    Generate a simple BBS for a single RCC beam.

    Parameters
    ----------
    span_clear_m : clear span between supports (m)
    beam_width_m : overall beam width (m)
    beam_depth_m : overall beam depth (m)
    cover_m      : clear concrete cover to main bars (m)
    bottom_dia_mm: bottom main bar diameter (mm)
    bottom_count : number of bottom main bars
    top_dia_mm   : top main bar diameter (mm)
    top_count    : number of top main bars
    dev_len_m    : development length at each end (m)
    stirrup_dia_mm    : stirrup bar diameter (mm)
    stirrup_leg_count : number of legs (typically 4) – reserved for future
    stirrup_spacing_mm: spacing of stirrups (mm)

    Returns
    -------
    List[Bar]
        BBS entries for bottom bars (B1), top bars (T1), and stirrups (S1).

    Notes
    -----
    - This function is intentionally simple, for estimation.
    - For detailed design, bar curtailment, anchorage bends, etc.,
      a full detailing package is required.
    """

    bars: List[Bar] = []

    # ---------------------------
    # 1. Main bottom bars (B1)
    # ---------------------------
    main_length_m = span_clear_m + 2.0 * dev_len_m
    bars.append(
        Bar(
            mark="B1",
            dia_mm=bottom_dia_mm,
            count=bottom_count,
            length_m=main_length_m,
            shape="Straight main bar (bottom)",
        )
    )

    # ---------------------------
    # 2. Main top bars (T1)
    # ---------------------------
    bars.append(
        Bar(
            mark="T1",
            dia_mm=top_dia_mm,
            count=top_count,
            length_m=main_length_m,
            shape="Straight main bar (top)",
        )
    )

    # ---------------------------
    # 3. Stirrups (S1)
    # ---------------------------
    # Effective core dimensions (centre line of stirrup)
    core_width_m = beam_width_m - 2.0 * cover_m
    core_depth_m = beam_depth_m - 2.0 * cover_m
    if core_width_m <= 0 or core_depth_m <= 0:
        # Degenerate geometry; return main bars only
        return bars

    # Centre-line perimeter
    stirrup_perimeter_m = 2.0 * (core_width_m + core_depth_m)

    # Basic hook allowance ≈ 2 × 8d (two hooks), d in m
    d_m = stirrup_dia_mm / 1000.0
    hook_allowance_m = 2.0 * (8.0 * d_m)
    stirrup_length_m = stirrup_perimeter_m + hook_allowance_m

    # Number of stirrups along the clear span
    if stirrup_spacing_mm <= 0:
        # safety fallback
        n_stirrups = 0
    else:
        n_stirrups = int(span_clear_m * 1000.0 / stirrup_spacing_mm) + 1

    if n_stirrups > 0:
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

    Parameters
    ----------
    bars : List[Bar]

    Returns
    -------
    Dict[float, float]
        Mapping {dia_mm: total_weight_kg}.
    """
    summary: Dict[float, float] = {}
    for b in bars:
        summary[b.dia_mm] = summary.get(b.dia_mm, 0.0) + b.weight_kg
    return summary
