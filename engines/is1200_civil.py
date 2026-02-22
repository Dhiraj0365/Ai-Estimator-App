# engines/is1200_civil.py

"""
IS 1200 Measurement Engine – Building Works (Civil)

This module provides reusable helpers for civil quantity calculation
aligned with IS 1200 style measurement, suitable for CPWD/State SoR
estimation and MB preparation.

Scope (major building works):
- Earthwork (trenches, pits, backfill)
- Concrete & RCC (generic volumes, isolated footings)
- Masonry (brick/stone walls with opening deductions)
- Plaster / Paint (wall & ceiling finishes with IS-1200 style rules)
- Flooring / Tiling (floor areas with cut-outs)
- Formwork / Shuttering (columns, beams, slabs)
- Reinforcement helpers (kg from volume or bar dia/spacing)

Design goals:
- Technically sound, audit-friendly quantities.
- Conservative, IS-style measurement rules:
  * No negative quantities.
  * Reasonable handling of small vs large openings.
  * Rounding consistent with typical practice.
- Backward compatible with your existing Streamlit app, which calls:
  * IS1200Engine.volume(...)
  * IS1200Engine.wall_finish_area(...)
  * IS1200Engine.formwork_column_area(...)
  * IS1200Engine.formwork_beam_area(...)
  * IS1200Engine.formwork_slab_area(...)

NOTE:
This is not a legal or exhaustive reproduction of IS 1200; it encodes
widely used CPWD/IS-style measurement logic for common building items.
If you need to tune thresholds (e.g. opening limits), change the
default parameters.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Dict, Optional


# ---------------------------------------------------------------------------
# Internal helper dataclass for consistent results
# ---------------------------------------------------------------------------

@dataclass
class MeasureResult:
    """Container for a measurement computation."""

    gross: float
    deductions: float = 0.0
    additions: float = 0.0
    unit: str = ""
    meta: Dict[str, float | str] = field(default_factory=dict)

    def to_dict(self, round_to: int = 3) -> Dict[str, float | str]:
        """Convert to dict (gross, deductions, additions, net, ...)."""
        g = round(self.gross, round_to)
        d = round(self.deductions, round_to)
        a = round(self.additions, round_to)
        n = round(max(g - d + a, 0.0), round_to)
        out: Dict[str, float | str] = {
            "gross": g,
            "deductions": d,
            "additions": a,
            "net": n,
        }
        out.update(self.meta)
        return out


def _round_for_unit(value: float, unit: str) -> float:
    """
    IS‑1200 style rounding (approximate):
    - Linear (m): 2 decimals
    - Area (sqm): 2 decimals
    - Volume (cum): 3 decimals
    - Weight (kg): 2 decimals
    Default: 3 decimals
    """
    unit = unit.lower().strip()
    if unit in ("m", "rm", "rmt"):
        return round(value, 2)
    if unit in ("sqm", "m2", "sq.m", "sq.m."):
        return round(value, 2)
    if unit in ("cum", "m3", "cu.m", "cu.m."):
        return round(value, 3)
    if unit in ("kg", "kilogram", "kilograms"):
        return round(value, 2)
    return round(value, 3)


def _normalise_openings(openings: Optional[List[Dict]]) -> List[Dict]:
    """
    Normalise openings to a uniform structure:
    each opening: {"w": width, "h": height, "n": count}
    """
    if not openings:
        return []
    out: List[Dict] = []
    for o in openings:
        if not isinstance(o, dict):
            continue
        w = float(o.get("w", 0.0))
        h = float(o.get("h", 0.0))
        n = float(o.get("n", 1.0))
        if w <= 0 or h <= 0 or n <= 0:
            continue
        out.append({"w": w, "h": h, "n": n})
    return out


# ---------------------------------------------------------------------------
# Public Engine
# ---------------------------------------------------------------------------

class IS1200Engine:
    """
    Core IS‑1200 style calculation helpers for civil building works.

    All methods (except some formwork helpers) return dictionaries with at least:
    - gross
    - deductions
    - additions
    - net

    Backward compatibility:
    - volume(...)
    - wall_finish_area(...)
    - formwork_column_area(...)
    - formwork_beam_area(...)
    - formwork_slab_area(...)
    """

    # ---------------------------------------------------------------------
    # GENERIC VOLUME – EARTHWORK, CONCRETE, BRICKWORK
    # ---------------------------------------------------------------------
    @staticmethod
    def volume(
        L: float,
        B: float,
        D: float,
        deductions: float = 0.0,
        unit: str = "cum",
    ) -> Dict[str, float]:
        """
        Generic rectangular volume: L × B × D minus explicit deductions.

        Used for:
        - Earthwork (simple vertical sides)
        - PCC / RCC members where no complex shape is needed
        - Brickwork block volume (if you don't need opening logic)

        Parameters
        ----------
        L, B, D : float
            Length, breadth, depth (m).
        deductions : float, optional
            Deductions in m³ (already combined).
        unit : str
            Output unit (default 'cum').

        Returns
        -------
        dict
            {gross, deductions, additions, net, pct}
        """
        L = max(L, 0.0)
        B = max(B, 0.0)
        D = max(D, 0.0)
        gross = L * B * D
        deductions = max(deductions, 0.0)

        gross_r = _round_for_unit(gross, unit)
        ded_r = _round_for_unit(deductions, unit)
        net_r = _round_for_unit(max(gross_r - ded_r, 0.0), unit)
        pct = round((ded_r / gross_r * 100.0), 2) if gross_r > 0 else 0.0

        return {
            "gross": gross_r,
            "deductions": ded_r,
            "additions": 0.0,
            "net": net_r,
            "pct": pct,
        }

    # ---------------------------------------------------------------------
    # EARTHWORK – TRENCH & PIT EXCAVATION, BACKFILL
    # ---------------------------------------------------------------------
    @staticmethod
    def trench_excavation(
        length: float,
        breadth_bottom: float,
        depth: float,
        side_slope_h_over_v: float = 0.0,
        deductions: float = 0.0,
        unit: str = "cum",
    ) -> Dict[str, float]:
        """
        Earthwork in excavation for trenches/foundations (IS 1200 Part 1 style).

        If side_slope_h_over_v > 0, uses average breadth as per side slopes:
            top_breadth = breadth_bottom + 2 * side_slope * depth
            avg_breadth = (breadth_bottom + top_breadth) / 2

        For vertical sides, side_slope_h_over_v = 0.

        Returns
        -------
        dict : {gross, deductions, additions, net}
        """
        length = max(length, 0.0)
        breadth_bottom = max(breadth_bottom, 0.0)
        depth = max(depth, 0.0)

        if side_slope_h_over_v > 0.0:
            top_b = breadth_bottom + 2.0 * side_slope_h_over_v * depth
            avg_b = (breadth_bottom + top_b) / 2.0
            gross = length * avg_b * depth
        else:
            gross = length * breadth_bottom * depth

        mr = MeasureResult(gross=gross, deductions=max(deductions, 0.0), unit=unit)
        return mr.to_dict(round_to=3)

    @staticmethod
    def pit_excavation(
        length_bottom: float,
        breadth_bottom: float,
        depth: float,
        side_slope_h_over_v: float = 0.0,
        unit: str = "cum",
    ) -> Dict[str, float]:
        """
        Pit excavation (isolated footing pits, sumps, etc.).

        Same concept as trench, but for a single rectangular pit.
        """
        length_bottom = max(length_bottom, 0.0)
        breadth_bottom = max(breadth_bottom, 0.0)
        depth = max(depth, 0.0)

        if side_slope_h_over_v > 0.0:
            top_L = length_bottom + 2.0 * side_slope_h_over_v * depth
            top_B = breadth_bottom + 2.0 * side_slope_h_over_v * depth
            avg_L = (length_bottom + top_L) / 2.0
            avg_B = (breadth_bottom + top_B) / 2.0
            gross = avg_L * avg_B * depth
        else:
            gross = length_bottom * breadth_bottom * depth

        mr = MeasureResult(gross=gross, deductions=0.0, unit=unit)
        return mr.to_dict(round_to=3)

    @staticmethod
    def backfill(
        length: float,
        breadth: float,
        height: float,
        compaction_factor: float = 1.0,
        unit: str = "cum",
    ) -> Dict[str, float]:
        """
        Backfilling around foundations / in plinth.

        gross = length × breadth × height
        additions: factor for compaction allowance (e.g. 1.05 for 5% extra)

        Returns dict {gross, deductions, additions, net}
        """
        length = max(length, 0.0)
        breadth = max(breadth, 0.0)
        height = max(height, 0.0)
        gross = length * breadth * height

        extra = 0.0
        if compaction_factor > 1.0:
            extra = gross * (compaction_factor - 1.0)

        mr = MeasureResult(gross=gross, additions=extra, unit=unit)
        return mr.to_dict(round_to=3)

    # ---------------------------------------------------------------------
    # RCC / CONCRETE – ISOLATED FOOTINGS, GENERIC
    # ---------------------------------------------------------------------
    @staticmethod
    def isolated_footing_volume(
        L: float,
        B: float,
        D: float,
        pedestal_L: float = 0.0,
        pedestal_B: float = 0.0,
        pedestal_H: float = 0.0,
        deductions: float = 0.0,
        unit: str = "cum",
    ) -> Dict[str, float]:
        """
        RCC volume of isolated footing + pedestal, if provided.

        Parameters
        ----------
        L, B, D : footing length, breadth, depth (m)
        pedestal_L, pedestal_B, pedestal_H : pedestal size (m)
        deductions : volume deductions (e.g. pockets, bolts) if any
        """
        v_foot = max(L, 0.0) * max(B, 0.0) * max(D, 0.0)
        v_ped = max(pedestal_L, 0.0) * max(pedestal_B, 0.0) * max(pedestal_H, 0.0)
        gross = v_foot + v_ped
        mr = MeasureResult(gross=gross, deductions=max(deductions, 0.0), unit=unit)
        return mr.to_dict(round_to=3)

    # ---------------------------------------------------------------------
    # BRICKWORK / MASONRY – WALL VOLUME WITH OPENING DEDUCTIONS
    # ---------------------------------------------------------------------
    @staticmethod
    def brickwork_wall(
        length: float,
        thickness: float,
        height: float,
        openings: Optional[List[Dict]] = None,
        small_opening_limit: float = 0.10,   # sqm (typical IS‑1200 threshold)
        unit: str = "cum",
    ) -> Dict[str, float]:
        """
        Brick masonry in wall.

        - Gross = length × thickness × height
        - No deduction for individual openings up to small_opening_limit
          (IS 1200 Part 5: small apertures).
        - Full deduction for larger openings: area × thickness.

        openings: list of dicts {"w": width_m, "h": height_m, "n": count}
        """
        length = max(length, 0.0)
        thickness = max(thickness, 0.0)
        height = max(height, 0.0)

        gross = length * thickness * height

        norm_openings = _normalise_openings(openings)
        ded = 0.0
        for o in norm_openings:
            area_one = o["w"] * o["h"]
            n = o["n"]
            if area_one <= small_opening_limit:
                # No deduction (small openings)
                continue
            ded += area_one * thickness * n

        mr = MeasureResult(gross=gross, deductions=ded, unit=unit)
        return mr.to_dict(round_to=3)

    @staticmethod
    def stone_masonry_wall(
        length: float,
        thickness: float,
        height: float,
        openings: Optional[List[Dict]] = None,
        small_opening_limit: float = 0.10,
        unit: str = "cum",
    ) -> Dict[str, float]:
        """
        Stone masonry wall (same logic as brickwork for openings).
        """
        return IS1200Engine.brickwork_wall(
            length=length,
            thickness=thickness,
            height=height,
            openings=openings,
            small_opening_limit=small_opening_limit,
            unit=unit,
        )

    # ---------------------------------------------------------------------
    # PLASTER / PAINT – WALL FINISH AREA WITH OPENINGS
    # ---------------------------------------------------------------------
    @staticmethod
    def wall_finish_area(
        length: float,
        height: float,
        sides: int = 2,
        openings: Optional[List[Dict]] = None,
        small_opening_limit: float = 0.50,   # no deduction
        medium_opening_limit: float = 3.00,  # deduct one face only
        unit: str = "sqm",
    ) -> Dict[str, float]:
        """
        Wall surface area for plaster/putty/painting as per IS‑1200 style.

        Simplified rule set (commonly used in practice):
        - Gross area = length × height × sides.
        - For each opening (area A per face):
          * A <= small_opening_limit  → no deduction for opening or jambs.
          * small_opening_limit < A <= medium_opening_limit
                → deduct A for ONE face only (for both‑side finish).
          * A > medium_opening_limit → deduct A × sides (full opening on all sides).

        openings: list of dicts {"w": width_m, "h": height_m, "n": count}
        """
        length = max(length, 0.0)
        height = max(height, 0.0)
        sides = max(int(sides), 0)

        gross = length * height * sides

        norm_openings = _normalise_openings(openings)
        ded = 0.0

        for o in norm_openings:
            A_one = o["w"] * o["h"]  # area on one face
            n = o["n"]

            if A_one <= small_opening_limit:
                # No deduction
                continue
            elif A_one <= medium_opening_limit:
                # Deduct one face only (per opening group)
                ded += A_one * n
            else:
                # Deduct for all sides
                ded += A_one * sides * n

        mr = MeasureResult(gross=gross, deductions=ded, unit=unit)
        return mr.to_dict(round_to=2)

    @staticmethod
    def ceiling_finish_area(
        length: float,
        breadth: float,
        openings: Optional[List[Dict]] = None,
        small_opening_limit: float = 0.50,
        unit: str = "sqm",
    ) -> Dict[str, float]:
        """
        Ceiling plaster/paint area.

        Gross = length × breadth.
        Deductions only for large openings (e.g. big skylights).
        """
        length = max(length, 0.0)
        breadth = max(breadth, 0.0)
        gross = length * breadth

        norm_openings = _normalise_openings(openings)
        ded = 0.0
        for o in norm_openings:
            A_one = o["w"] * o["h"]
            n = o["n"]
            if A_one > small_opening_limit:
                ded += A_one * n

        mr = MeasureResult(gross=gross, deductions=ded, unit=unit)
        return mr.to_dict(round_to=2)

    # ---------------------------------------------------------------------
    # FLOORING / TILING AREA
    # ---------------------------------------------------------------------
    @staticmethod
    def floor_area(
        length: float,
        breadth: float,
        cutouts: Optional[List[Dict]] = None,
        unit: str = "sqm",
    ) -> Dict[str, float]:
        """
        Floor / roof / tile area.

        Gross = length × breadth (single side).
        cutouts: list of {"w": width_m, "h": height_m, "n": count}
        """
        length = max(length, 0.0)
        breadth = max(breadth, 0.0)
        gross = length * breadth

        norm_cutouts = _normalise_openings(cutouts)
        ded = 0.0
        for c in norm_cutouts:
            ded += c["w"] * c["h"] * c["n"]

        mr = MeasureResult(gross=gross, deductions=ded, unit=unit)
        return mr.to_dict(round_to=2)

    @staticmethod
    def floor_area_with_wastage(
        length: float,
        breadth: float,
        wastage_factor: float = 1.03,
        cutouts: Optional[List[Dict]] = None,
        unit: str = "sqm",
    ) -> Dict[str, float]:
        """
        Flooring area with wastage factor (e.g. 3–5% for tiles/stone).

        net_base = length × breadth – cutouts
        additions = net_base × (wastage_factor – 1)
        """
        base = IS1200Engine.floor_area(length, breadth, cutouts, unit=unit)
        net_base = base["net"]
        extra = 0.0
        if wastage_factor > 1.0:
            extra = net_base * (wastage_factor - 1.0)

        mr = MeasureResult(
            gross=base["gross"],
            deductions=base["deductions"],
            additions=extra,
            unit=unit,
        )
        return mr.to_dict(round_to=2)

    # ---------------------------------------------------------------------
    # RCC FORMWORK AREAS (BACKWARD-COMPATIBLE FLOAT RETURN)
    # ---------------------------------------------------------------------
    @staticmethod
    def formwork_column_area(
        L: float,
        B: float,
        H: float,
        unit: str = "sqm",
    ) -> float:
        """
        Formwork for column – area of four faces.

        Approx as: 2 × (L + B) × H

        NOTE:
        Returns a float (area in sqm) for backward compatibility with
        your existing Streamlit code.
        """
        L = max(L, 0.0)
        B = max(B, 0.0)
        H = max(H, 0.0)
        area = 2.0 * (L + B) * H
        return _round_for_unit(area, unit)

    @staticmethod
    def formwork_beam_area(
        breadth: float,
        depth: float,
        length: float,
        unit: str = "sqm",
    ) -> float:
        """
        Formwork for beam – 3 exposed sides (bottom + 2 sides).

        Approx as: (2 × depth + breadth) × length
        """
        breadth = max(breadth, 0.0)
        depth = max(depth, 0.0)
        length = max(length, 0.0)
        area = (2.0 * depth + breadth) * length
        return _round_for_unit(area, unit)

    @staticmethod
    def formwork_slab_area(
        length: float,
        breadth: float,
        unit: str = "sqm",
    ) -> float:
        """
        Formwork for slab – soffit area.

        Approx as: length × breadth
        """
        length = max(length, 0.0)
        breadth = max(breadth, 0.0)
        area = length * breadth
        return _round_for_unit(area, unit)

    # ---------------------------------------------------------------------
    # STAIRCASE (BASIC) – WAIST SLAB + STEPS
    # ---------------------------------------------------------------------
    @staticmethod
    def staircase_waist_slab_volume(
        flight_length: float,
        width: float,
        waist_thickness: float,
        landings_volume: float = 0.0,
        unit: str = "cum",
    ) -> Dict[str, float]:
        """
        Approximate volume of staircase waist slab (excluding steps).

        volume_waist = flight_length × width × waist_thickness
        total = volume_waist + landings_volume
        """
        flight_length = max(flight_length, 0.0)
        width = max(width, 0.0)
        waist_thickness = max(waist_thickness, 0.0)
        landings_volume = max(landings_volume, 0.0)

        v_waist = flight_length * width * waist_thickness
        gross = v_waist + landings_volume

        mr = MeasureResult(gross=gross, deductions=0.0, unit=unit)
        return mr.to_dict(round_to=3)

    # ---------------------------------------------------------------------
    # REINFORCEMENT UTILITIES (HELPERS)
    # ---------------------------------------------------------------------
    @staticmethod
    def steel_from_kg_per_cum(
        concrete_volume_cum: float,
        kg_per_cum: float,
        unit: str = "kg",
    ) -> Dict[str, float]:
        """
        Convenience function for RCC estimation when you use
        empirical kg of steel per cubic metre of RCC.

        Parameters
        ----------
        concrete_volume_cum : float
            Net concrete volume in m³.
        kg_per_cum : float
            Assumed steel consumption in kg/m³.

        Returns
        -------
        dict : {gross, deductions, additions, net}
               (all values same, in kg)
        """
        concrete_volume_cum = max(concrete_volume_cum, 0.0)
        kg_per_cum = max(kg_per_cum, 0.0)
        wt = concrete_volume_cum * kg_per_cum
        mr = MeasureResult(gross=wt, deductions=0.0, unit=unit)
        return mr.to_dict(round_to=2)

    @staticmethod
    def steel_from_bars(
        dia_mm: float,
        length_m: float,
        count: int,
        unit: str = "kg",
    ) -> Dict[str, float]:
        """
        Weight of reinforcement bars given diameter, length and count.

        Uses standard approximation:
            weight_per_m (kg/m) ≈ dia_mm² / 162

        total_kg = (dia_mm² / 162) × length_m × count
        """
        dia_mm = max(dia_mm, 0.0)
        length_m = max(length_m, 0.0)
        count = max(int(count), 0)

        if dia_mm <= 0 or length_m <= 0 or count <= 0:
            mr = MeasureResult(gross=0.0, deductions=0.0, unit=unit)
            return mr.to_dict(round_to=2)

        wt_per_m = (dia_mm ** 2) / 162.0
        total = wt_per_m * length_m * count

        mr = MeasureResult(gross=total, deductions=0.0, unit=unit)
        return mr.to_dict(round_to=2)

    @staticmethod
    def steel_slab_single_layer(
        slab_length: float,
        slab_width: float,
        bar_dia_mm: float,
        spacing_mm: float,
        unit: str = "kg",
    ) -> Dict[str, float]:
        """
        Approximate steel weight for one layer of slab reinforcement
        with parallel bars at uniform spacing.

        Method:
        - Number of bars ≈ floor((slab_width / spacing) + 1)
        - Each bar length ≈ slab_length
        - weight from steel_from_bars()

        NOTE:
        This is a very simplified helper for quick estimation;
        actual detailing may differ.
        """
        slab_length = max(slab_length, 0.0)
        slab_width = max(slab_width, 0.0)
        spacing_mm = max(spacing_mm, 1.0)

        # how many spaces across width
        n_bars = int(slab_width * 1000.0 // spacing_mm) + 1
        if n_bars <= 0:
            mr = MeasureResult(gross=0.0, deductions=0.0, unit=unit)
            return mr.to_dict(round_to=2)

        steel = IS1200Engine.steel_from_bars(
            dia_mm=bar_dia_mm,
            length_m=slab_length,
            count=n_bars,
            unit=unit,
        )
        return steel


# ---------------------------------------------------------------------------
# Simple self-test when run directly
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Volume test:", IS1200Engine.volume(5, 2, 0.3))
    print(
        "Trench:",
        IS1200Engine.trench_excavation(10, 1, 1.5, side_slope_h_over_v=0.5),
    )
    print(
        "Brickwork:",
        IS1200Engine.brickwork_wall(
            length=5,
            thickness=0.23,
            height=3,
            openings=[{"w": 1.0, "h": 2.1, "n": 1}],
        ),
    )
    print(
        "Wall finish:",
        IS1200Engine.wall_finish_area(
            length=5,
            height=3,
            sides=2,
            openings=[{"w": 1.2, "h": 1.5, "n": 2}],
        ),
    )
    print(
        "Floor with wastage:",
        IS1200Engine.floor_area_with_wastage(4, 3, wastage_factor=1.03),
    )
    print("Formwork column area:", IS1200Engine.formwork_column_area(0.3, 0.4, 3.0))
    print(
        "Steel from bars:",
        IS1200Engine.steel_from_bars(dia_mm=12, length_m=6, count=10),
    )
