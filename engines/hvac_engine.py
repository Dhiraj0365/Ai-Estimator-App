"""
HVAC Estimation Engine (Air Conditioning & Ventilation)

This module provides *estimation-level* helpers for HVAC quantities.
It is NOT a full psychrometric or duct design tool; it encodes common
CPWD / NBC / ASHRAE-style assumptions used by estimators:

- Airflow (CMH / CFM) from room area, height, and air changes or L/s·m².
- Approximate duct lengths and sheet-metal surface areas from airflow and
  assumed velocities/aspect ratios.
- Approximate chilled water / refrigerant pipe lengths and insulation areas.

You typically use these in composites_mep.py to translate building data:

    "Zone A: 200 m² office, 3 m height, 8 ACH"
        → supply airflow
        → duct sqm for GI ducting item
        → insulation sqm
        → CHW pipe length and insulation

All functions are UI-agnostic (no Streamlit), suitable for tests or any
front-end. The numbers are *rules of thumb* and should be calibrated with
your own practice and past jobs.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional


# =============================================================================
# Result dataclasses
# =============================================================================

@dataclass
class AirFlowResult:
    """
    Airflow and load summary for a single zone.

    Attributes
    ----------
    area_sqm        : float - zone floor area.
    height_m        : float - average ceiling height.
    volume_cum      : float - area * height.
    ach             : float - air changes per hour (if used).
    supply_cmh      : float - supply air flow in m³/h.
    supply_cfm      : float - supply air flow in CFM (approx: CMH / 1.699).
    meta            : dict  - includes method used, L/s·m², people, etc.
    """

    area_sqm: float
    height_m: float
    volume_cum: float
    ach: float
    supply_cmh: float
    supply_cfm: float
    meta: Dict[str, Any] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DuctRunResult:
    """
    Duct run quantity summary (for GI ducting & insulation).

    Attributes
    ----------
    total_duct_length_m    : float  - main + branches.
    main_duct_length_m     : float
    branch_duct_length_m   : float
    duct_surface_area_sqm  : float  - approximate total sheet-metal area (outer).
    insulation_area_sqm    : float  - area to be insulated (often same as duct area).
    unit_length            : str    - "m".
    unit_area              : str    - "sqm".
    meta                   : dict   - assumptions (velocity, aspect ratio, etc.).
    """

    total_duct_length_m: float
    main_duct_length_m: float
    branch_duct_length_m: float
    duct_surface_area_sqm: float
    insulation_area_sqm: float
    unit_length: str = "m"
    unit_area: str = "sqm"
    meta: Dict[str, Any] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class HvacPipeRunResult:
    """
    Chilled water / condenser water / refrigerant pipe run summary.

    Attributes
    ----------
    total_length_m       : float - total pipe length including wastage.
    header_length_m      : float - mains (plantroom to riser, etc.).
    riser_length_m       : float - total riser length (sum of risers).
    branch_length_m      : float - branches to AHUs/FCUs/VRF IDs.
    insulation_area_sqm  : float - external surface to be insulated (approx).
    unit_length          : str   - "m".
    unit_area            : str   - "sqm".
    meta                 : dict  - diameters, zones, wastage, etc.
    """

    total_length_m: float
    header_length_m: float
    riser_length_m: float
    branch_length_m: float
    insulation_area_sqm: float
    unit_length: str = "m"
    unit_area: str = "sqm"
    meta: Dict[str, Any] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# =============================================================================
# Engine
# =============================================================================

class HvacEngine:
    """
    HVAC estimation helpers.

    These methods implement *simple but practical* estimation rules.
    You should refine constants to your normal design guidelines
    (velocities, aspect ratios, branch factors, wastage, etc.).

    Unit conventions:
    - Air volume: m³ (cum)
    - Airflow: CMH (m³/h) and CFM
    - Duct area: m² of sheet metal (outer surface)
    - Pipe insulation area: m² (external surface)
    """

    # ---------------------------------------------------------------------
    # 1. Airflow from area & height (ACH or L/s·m²)
    # ---------------------------------------------------------------------
    @staticmethod
    def airflow_from_ach(
        area_sqm: float,
        height_m: float,
        ach: float,
        meta: Optional[Dict[str, Any]] = None,
    ) -> AirFlowResult:
        """
        Compute supply air volume from area, height, and Air Changes per Hour.

        Definitions:
        - Room volume = area_sqm × height_m  (m³)
        - ACH = air changes per hour
        - Supply CMH = ACH × volume

        Supply CFM is approximated by:
            CFM ≈ CMH / 1.699

        Parameters
        ----------
        area_sqm : float
        height_m : float
        ach      : float

        Returns
        -------
        AirFlowResult
        """
        area_sqm = max(float(area_sqm), 0.0)
        height_m = max(float(height_m), 0.0)
        ach = max(float(ach), 0.0)

        volume = area_sqm * height_m
        cmh = ach * volume
        cfm = cmh / 1.699 if cmh > 0 else 0.0

        meta_out = {"method": "ACH", "ach": ach}
        if meta:
            meta_out.update(meta)

        return AirFlowResult(
            area_sqm=area_sqm,
            height_m=height_m,
            volume_cum=round(volume, 2),
            ach=ach,
            supply_cmh=round(cmh, 1),
            supply_cfm=round(cfm, 1),
            meta=meta_out,
        )

    @staticmethod
    def airflow_from_lps_per_sqm(
        area_sqm: float,
        height_m: float,
        lps_per_sqm: float,
        meta: Optional[Dict[str, Any]] = None,
    ) -> AirFlowResult:
        """
        Compute airflow from area and L/s·m² (litres per second per m²),
        typical for office/commercial occupancy-based ventilation.

        Steps:
        - L/s = lps_per_sqm × area_sqm
        - m³/h (CMH) = (L/s × 3.6)
        - ACH = CMH / volume (m³)

        Returns
        -------
        AirFlowResult
        """
        area_sqm = max(float(area_sqm), 0.0)
        height_m = max(float(height_m), 0.0)
        lps_per_sqm = max(float(lps_per_sqm), 0.0)

        volume = area_sqm * height_m
        lps = lps_per_sqm * area_sqm
        cmh = lps * 3.6
        ach = (cmh / volume) if volume > 0 else 0.0
        cfm = cmh / 1.699 if cmh > 0 else 0.0

        meta_out = {"method": "LPS_PER_SQM", "lps_per_sqm": lps_per_sqm}
        if meta:
            meta_out.update(meta)

        return AirFlowResult(
            area_sqm=area_sqm,
            height_m=height_m,
            volume_cum=round(volume, 2),
            ach=round(ach, 2),
            supply_cmh=round(cmh, 1),
            supply_cfm=round(cfm, 1),
            meta=meta_out,
        )

    # ---------------------------------------------------------------------
    # 2. Duct quantity estimation
    # ---------------------------------------------------------------------
    @staticmethod
    def duct_run_estimate(
        supply_cmh: float,
        main_duct_length_m: float,
        branch_duct_length_m: float,
        main_velocity_mps: float = 5.0,
        branch_velocity_mps: float = 3.0,
        main_aspect_ratio: float = 2.0,     # width:height
        branch_aspect_ratio: float = 1.5,
        wastage_factor: float = 1.10,
        meta: Optional[Dict[str, Any]] = None,
    ) -> DuctRunResult:
        """
        Estimate duct surface area (sheet metal) from airflow & assumed velocity.

        Simplified method:

        - For main duct:
            Q_main (m³/s) = supply_cmh / 3600
            A_main = Q_main / main_velocity_mps     [m² cross-section]
            From aspect ratio (W/H = main_aspect_ratio), derive:
                H = sqrt(A / AR)
                W = AR * H
            Perimeter_main = 2 × (W + H)
            Surface_main ≈ perimeter_main × main_duct_length_m

        - For branches:
            Approximate branch air as same as main / (some diversity). For
            simplicity, we assume branches share similar cross-section as main,
            or we reduce area by factor (e.g., 0.7). Here we use a branch factor
            to adjust. For more detail, you'd pass branch_cmh explicitly.

        - Total duct area = (main area + branch area) × wastage_factor

        NOTE:
        This is a **rough estimation** to get GI ducting sqm. For actual
        duct design, detailed static calculations and stepwise sizing are
        needed.

        Parameters
        ----------
        supply_cmh : float
            Total supply air flow for the run (m³/h).
        main_duct_length_m : float
        branch_duct_length_m : float
        main_velocity_mps : float
        branch_velocity_mps : float
        main_aspect_ratio : float
        branch_aspect_ratio : float
        wastage_factor : float
            Additional factor for extra length, changes in size, etc.

        Returns
        -------
        DuctRunResult
        """
        supply_cmh = max(float(supply_cmh), 0.0)
        main_duct_length_m = max(float(main_duct_length_m), 0.0)
        branch_duct_length_m = max(float(branch_duct_length_m), 0.0)
        main_velocity_mps = max(float(main_velocity_mps), 0.1)
        branch_velocity_mps = max(float(branch_velocity_mps), 0.1)
        main_aspect_ratio = max(float(main_aspect_ratio), 0.1)
        branch_aspect_ratio = max(float(branch_aspect_ratio), 0.1)
        wastage_factor = max(float(wastage_factor), 1.0)

        # Convert CMH to m³/s
        q_main = supply_cmh / 3600.0

        # Main duct cross-section
        a_main = q_main / main_velocity_mps if main_velocity_mps > 0 else 0.0
        if a_main <= 0.0:
            # No duct if no airflow
            return DuctRunResult(
                total_duct_length_m=0.0,
                main_duct_length_m=0.0,
                branch_duct_length_m=0.0,
                duct_surface_area_sqm=0.0,
                insulation_area_sqm=0.0,
                meta=meta or {},
            )

        # derive W,H from A and aspect ratio AR = W/H
        #   A = W*H = AR*H*H => H = sqrt(A/AR), W = AR*H
        from math import sqrt
        H_main = sqrt(a_main / main_aspect_ratio)
        W_main = main_aspect_ratio * H_main
        perimeter_main = 2.0 * (W_main + H_main)  # m

        # main duct area
        area_main = perimeter_main * main_duct_length_m

        # Branch ducts: approximate that combined branch area is e.g. 0.7 of main
        branch_factor = 0.7
        a_branch = a_main * branch_factor * (branch_velocity_mps / main_velocity_mps)
        H_branch = sqrt(a_branch / branch_aspect_ratio)
        W_branch = branch_aspect_ratio * H_branch
        perimeter_branch = 2.0 * (W_branch + H_branch)
        area_branch = perimeter_branch * branch_duct_length_m

        total_area = (area_main + area_branch) * wastage_factor

        meta_out = {
            "supply_cmh": supply_cmh,
            "q_main_m3ps": q_main,
            "main_velocity_mps": main_velocity_mps,
            "branch_velocity_mps": branch_velocity_mps,
            "main_aspect_ratio": main_aspect_ratio,
            "branch_aspect_ratio": branch_aspect_ratio,
            "a_main_m2": a_main,
            "a_branch_m2": a_branch,
            "perimeter_main_m": perimeter_main,
            "perimeter_branch_m": perimeter_branch,
            "branch_factor": branch_factor,
            "wastage_factor": wastage_factor,
        }
        if meta:
            meta_out.update(meta)

        total_length = main_duct_length_m + branch_duct_length_m

        return DuctRunResult(
            total_duct_length_m=round(total_length, 2),
            main_duct_length_m=round(main_duct_length_m, 2),
            branch_duct_length_m=round(branch_duct_length_m, 2),
            duct_surface_area_sqm=round(total_area, 2),
            insulation_area_sqm=round(total_area, 2),  # usually same; adjust if needed
            meta=meta_out,
        )

    # ---------------------------------------------------------------------
    # 3. Chilled / condenser water piping
    # ---------------------------------------------------------------------
    @staticmethod
    def piping_run_estimate(
        floors: int,
        floor_height_m: float,
        risers: int,
        main_header_length_m: float,
        terminal_units_per_floor: int,
        avg_branch_length_per_unit_m: float,
        outer_diameter_mm: float,
        wastage_factor: float = 1.10,
        meta: Optional[Dict[str, Any]] = None,
    ) -> HvacPipeRunResult:
        """
        Estimate CHW / condenser water / refrigerant piping length & insulation area.

        Model:
        - Riser length:
            riser_length = floors * floor_height_m * risers
        - Main header length:
            main_header_length_m (plantroom, roof, etc.)
        - Branch length:
            branch_length = floors * terminal_units_per_floor * avg_branch_length_per_unit_m
              (e.g., branches from riser to AHUs/FCUs/IDUs).
        - Total base = riser_length + main_header_length_m + branch_length
        - Total length with wastage:
            total_length = base * wastage_factor
        - Insulation area (outer surface):
            circumference = π * outer_diameter_m
            insulation_area = circumference * total_length

        outer_diameter_mm includes pipe OD + insulation thickness approx.,
        or you can pass bare pipe OD and multiply.

        Parameters
        ----------
        floors : int
        floor_height_m : float
        risers : int
        main_header_length_m : float
        terminal_units_per_floor : int
        avg_branch_length_per_unit_m : float
        outer_diameter_mm : float
            External diameter used for insulation area calculation.
        wastage_factor : float

        Returns
        -------
        HvacPipeRunResult
        """
        from math import pi

        floors = max(int(floors), 0)
        risers = max(int(risers), 0)
        floor_height_m = max(float(floor_height_m), 0.0)
        main_header_length_m = max(float(main_header_length_m), 0.0)
        terminal_units_per_floor = max(int(terminal_units_per_floor), 0)
        avg_branch_length_per_unit_m = max(float(avg_branch_length_per_unit_m), 0.0)
        outer_diameter_mm = max(float(outer_diameter_mm), 0.0)
        wastage_factor = max(float(wastage_factor), 1.0)

        # Riser length
        riser_length = floors * floor_height_m * risers

        # Branch length
        total_units = floors * terminal_units_per_floor
        branch_length = total_units * avg_branch_length_per_unit_m

        # Base total
        base_total = riser_length + main_header_length_m + branch_length
        total_length = base_total * wastage_factor

        # Insulation area
        outer_diameter_m = outer_diameter_mm / 1000.0
        circumference = pi * outer_diameter_m
        insulation_area = circumference * total_length

        meta_out = {
            "floors": floors,
            "floor_height_m": floor_height_m,
            "risers": risers,
            "terminal_units_per_floor": terminal_units_per_floor,
            "avg_branch_length_per_unit_m": avg_branch_length_per_unit_m,
            "outer_diameter_mm": outer_diameter_mm,
            "wastage_factor": wastage_factor,
        }
        if meta:
            meta_out.update(meta)

        return HvacPipeRunResult(
            total_length_m=round(total_length, 2),
            header_length_m=round(main_header_length_m * wastage_factor, 2),
            riser_length_m=round(riser_length * wastage_factor, 2),
            branch_length_m=round(branch_length * wastage_factor, 2),
            insulation_area_sqm=round(insulation_area, 2),
            meta=meta_out,
        )
