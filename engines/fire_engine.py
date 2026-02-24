```python
# engines/fire_engine.py

"""
Fire-Fighting Estimation Engine (Wet Systems & Basic Fire Alarm)

This module provides *estimation-level* helpers for fire-fighting and
basic fire-protection quantities. It is NOT a full NFPA/NBC hydraulic
design or detailed alarm design; instead it encodes common practical
assumptions used by estimators:

- Hydrant & hose reel points per floor / per stair core.
- Hydrant ring main and riser pipe lengths.
- Sprinkler head counts and design flow from floor area & density.
- Fire pipe lengths (mains, risers, branches) and fittings.
- Fire pump duty (flow & head) rough sizing for BOQ.
- Water storage volume for fire-fighting.

You typically use these functions in composites_mep.py to translate
building data:

    "G+4 office, 2 stair cores, floor area 800 m²"
        → hydrant outlets, hose reels, pipe length, pump duty, sprinkler heads

All functions are UI-agnostic (no Streamlit), suitable for tests or any
front-end. Numbers are *rules of thumb* and should be calibrated with
your own practice, local code (NBC), and consultants' designs.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional


# =============================================================================
# Result dataclasses
# =============================================================================

@dataclass
class FirePipeRunResult:
    """
    Summary of fire pipe runs (hydrant/sprinkler mains + risers + branches).

    Attributes
    ----------
    total_length_m   : float  - total fire pipe length including wastage.
    ring_main_length_m : float  - hydrant/sprinkler loop around building.
    riser_length_m   : float  - cumulative riser length (all risers).
    branch_length_m  : float  - branches to landing valves, hose reels, heads.
    unit             : str    - "m".
    meta             : dict   - notes & assumptions.
    """

    total_length_m: float
    ring_main_length_m: float
    riser_length_m: float
    branch_length_m: float
    unit: str = "m"
    meta: Dict[str, Any] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class FittingsResult:
    """
    Estimated count of fire pipe fittings.

    Attributes
    ----------
    elbows_90   : int
    tees        : int
    reducers    : int
    flanges     : int
    valves      : int
    drains      : int
    air_release : int
    meta        : dict
    """

    elbows_90: int
    tees: int
    reducers: int
    flanges: int
    valves: int
    drains: int
    air_release: int
    meta: Dict[str, Any] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class HydrantSystemResult:
    """
    Hydrant & hose reel point summary.

    Attributes
    ----------
    hydrant_points      : int   - landing valves / external hydrants.
    hose_reel_points    : int   - hose reel points.
    riser_count         : int   - number of vertical risers.
    pump_duty_flow_lpm  : float - combined design flow (rough) in l/min.
    tank_capacity_kl    : float - fire water storage in kilolitres (rough).
    meta                : dict
    """

    hydrant_points: int
    hose_reel_points: int
    riser_count: int
    pump_duty_flow_lpm: float
    tank_capacity_kl: float
    meta: Dict[str, Any] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SprinklerSystemResult:
    """
    Sprinkler head & flow summary for a zone/building.

    Attributes
    ----------
    heads                  : int   - total sprinkler heads.
    design_area_sqm        : float - area used for design calc (operating area).
    density_lpm_per_sqm    : float - design density.
    design_flow_lpm        : float - design flow (l/min).
    branches               : int   - rough count of branch lines.
    meta                   : dict
    """

    heads: int
    design_area_sqm: float
    density_lpm_per_sqm: float
    design_flow_lpm: float
    branches: int
    meta: Dict[str, Any] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class FirePumpDuty:
    """
    Pump duty summary (for hydrant/sprinkler pump BOQ).

    Attributes
    ----------
    flow_lpm      : float - design flow in l/min.
    head_m        : float - design head in m.
    power_kw      : float - approximate motor power in kW.
    meta          : dict  - includes method, efficiencies, etc.
    """

    flow_lpm: float
    head_m: float
    power_kw: float
    meta: Dict[str, Any] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# =============================================================================
# Engine
# =============================================================================

class FireEngine:
    """
    Fire-fighting estimation helpers.

    These functions are *deliberately simplified* but aligned with typical
    NBC/CPWD practice for quick BOQ-level estimation. They should be
    tuned against real consultant designs for your region.
    """

    # ---------------------------------------------------------------------
    # 1. Hydrant & hose reel points from floors and cores
    # ---------------------------------------------------------------------
    @staticmethod
    def hydrant_system_points(
        floors: int,
        stair_cores: int,
        external_hydrants: int = 4,
        hose_reels_per_floor_per_core: int = 1,
        landing_valves_per_floor_per_core: int = 1,
        design_flow_per_hose_lpm: float = 180.0,   # 1 hose ~ 180 lpm
        simultaneous_hoses: int = 2,
        duration_minutes: int = 90,
        meta: Optional[Dict[str, Any]] = None,
    ) -> HydrantSystemResult:
        """
        Estimate hydrant & hose reel points and basic storage requirements.

        Assumptions:
        - On each floor, for each stair core:
            * landing_valves_per_floor_per_core hydrant points
            * hose_reels_per_floor_per_core hose reels
        - Additionally, external_hydrants around the building.
        - Design flow:
            flow_lpm = design_flow_per_hose_lpm × simultaneous_hoses
        - Storage volume (hydrant only) ~ flow_lpm × duration / 1000 (kL).

        Parameters
        ----------
        floors : int
        stair_cores : int
        external_hydrants : int
        hose_reels_per_floor_per_core : int
        landing_valves_per_floor_per_core : int
        design_flow_per_hose_lpm : float
        simultaneous_hoses : int
        duration_minutes : int

        Returns
        -------
        HydrantSystemResult
        """
        floors = max(int(floors), 0)
        stair_cores = max(int(stair_cores), 0)
        external_hydrants = max(int(external_hydrants), 0)
        hose_reels_per_floor_per_core = max(int(hose_reels_per_floor_per_core), 0)
        landing_valves_per_floor_per_core = max(int(landing_valves_per_floor_per_core), 0)
        design_flow_per_hose_lpm = max(float(design_flow_per_hose_lpm), 0.0)
        simultaneous_hoses = max(int(simultaneous_hoses), 0)
        duration_minutes = max(int(duration_minutes), 0)

        hose_reels = floors * stair_cores * hose_reels_per_floor_per_core
        landing_valves = floors * stair_cores * landing_valves_per_floor_per_core

        hydrant_points = landing_valves + external_hydrants

        # Design flow and storage
        flow_lpm = design_flow_per_hose_lpm * max(simultaneous_hoses, 1)
        storage_litres = flow_lpm * duration_minutes
        storage_kl = storage_litres / 1000.0  # kL

        meta_out = {
            "floors": floors,
            "stair_cores": stair_cores,
            "external_hydrants": external_hydrants,
            "hose_reels_per_floor_per_core": hose_reels_per_floor_per_core,
            "landing_valves_per_floor_per_core": landing_valves_per_floor_per_core,
            "design_flow_per_hose_lpm": design_flow_per_hose_lpm,
            "simultaneous_hoses": simultaneous_hoses,
            "duration_minutes": duration_minutes,
        }
        if meta:
            meta_out.update(meta)

        return HydrantSystemResult(
            hydrant_points=hydrant_points,
            hose_reel_points=hose_reels,
            riser_count=stair_cores,
            pump_duty_flow_lpm=flow_lpm,
            tank_capacity_kl=round(storage_kl, 1),
            meta=meta_out,
        )

    # ---------------------------------------------------------------------
    # 2. Sprinkler quantities from area & density
    # ---------------------------------------------------------------------
    @staticmethod
    def sprinkler_system(
        total_area_sqm: float,
        coverage_per_head_sqm: float = 12.0,
        design_density_lpm_per_sqm: float = 10.2,  # ~ 0.16 l/s·m²
        design_area_sqm: Optional[float] = None,
        branches_per_50_heads: int = 4,
        meta: Optional[Dict[str, Any]] = None,
    ) -> SprinklerSystemResult:
        """
        Estimate sprinkler head counts and design flow.

        Parameters
        ----------
        total_area_sqm : float
            Total floor area to be sprinklered (all levels or one zone).
        coverage_per_head_sqm : float
            Area served per sprinkler head (typ. 9-12 m², adjust by hazard).
        design_density_lpm_per_sqm : float
            Design density as l/min per m².
        design_area_sqm : float, optional
            Operating area for hydraulic design; if None, we use the smaller of
            total_area_sqm and 200 m² (light hazard) as default.
        branches_per_50_heads : int
            Approximate branch line count ~ branches_per_50_heads per 50 heads.

        Returns
        -------
        SprinklerSystemResult
        """
        total_area_sqm = max(float(total_area_sqm), 0.0)
        coverage_per_head_sqm = max(float(coverage_per_head_sqm), 0.1)
        density = max(float(design_density_lpm_per_sqm), 0.0)

        # Total heads
        import math
        total_heads = int(math.ceil(total_area_sqm / coverage_per_head_sqm)) if total_area_sqm > 0 else 0

        # Design area
        if design_area_sqm is None:
            design_area_sqm = min(total_area_sqm, 200.0)  # typical default
        design_area_sqm = max(float(design_area_sqm), 0.0)

        # Design flow
        design_flow_lpm = density * design_area_sqm

        # Branch lines
        branches = 0
        if total_heads > 0 and branches_per_50_heads > 0:
            branches = int(math.ceil(total_heads / (50.0 / branches_per_50_heads)))

        meta_out = {
            "total_area_sqm": total_area_sqm,
            "coverage_per_head_sqm": coverage_per_head_sqm,
            "branches_per_50_heads": branches_per_50_heads,
        }
        if meta:
            meta_out.update(meta)

        return SprinklerSystemResult(
            heads=total_heads,
            design_area_sqm=round(design_area_sqm, 1),
            density_lpm_per_sqm=density,
            design_flow_lpm=round(design_flow_lpm, 1),
            branches=branches,
            meta=meta_out,
        )

    # ---------------------------------------------------------------------
    # 3. Fire pipe run estimation (hydrant + sprinkler combined)
    # ---------------------------------------------------------------------
    @staticmethod
    def fire_pipe_runs(
        floors: int,
        floor_height_m: float,
        risers: int,
        ring_main_length_m: float,
        branches_per_floor: int,
        avg_branch_length_m: float,
        wastage_factor: float = 1.10,
        meta: Optional[Dict[str, Any]] = None,
    ) -> FirePipeRunResult:
        """
        Estimate total fire pipe length for hydrant/sprinkler system.

        Model:
        - Ring main (ground/terrace):
            ring_main_length_m as given.
        - Riser length:
            riser_length = floors * floor_height_m * risers
        - Branch length (landing valves + sprinklers/hose reels):
            branch_length = floors * branches_per_floor * avg_branch_length_m
        - Base total = ring main + risers + branches
        - Total with wastage:
            total_length = base_total * wastage_factor

        Parameters
        ----------
        floors : int
        floor_height_m : float
        risers : int
        ring_main_length_m : float
        branches_per_floor : int
        avg_branch_length_m : float
        wastage_factor : float

        Returns
        -------
        FirePipeRunResult
        """
        floors = max(int(floors), 0)
        risers = max(int(risers), 0)
        floor_height_m = max(float(floor_height_m), 0.0)
        ring_main_length_m = max(float(ring_main_length_m), 0.0)
        branches_per_floor = max(int(branches_per_floor), 0)
        avg_branch_length_m = max(float(avg_branch_length_m), 0.0)
        wastage_factor = max(float(wastage_factor), 1.0)

        # Riser length
        riser_length = floors * floor_height_m * risers

        # Branch length
        total_branches = floors * branches_per_floor
        branch_length = total_branches * avg_branch_length_m

        base_total = ring_main_length_m + riser_length + branch_length
        total_length = base_total * wastage_factor

        meta_out = {
            "floors": floors,
            "floor_height_m": floor_height_m,
            "risers": risers,
            "branches_per_floor": branches_per_floor,
            "avg_branch_length_m": avg_branch_length_m,
            "wastage_factor": wastage_factor,
        }
        if meta:
            meta_out.update(meta)

        return FirePipeRunResult(
            total_length_m=round(total_length, 2),
            ring_main_length_m=round(ring_main_length_m * wastage_factor, 2),
            riser_length_m=round(riser_length * wastage_factor, 2),
            branch_length_m=round(branch_length * wastage_factor, 2),
            meta=meta_out,
        )

    # ---------------------------------------------------------------------
    # 4. Fittings from fire pipe length
    # ---------------------------------------------------------------------
    @staticmethod
    def fittings_from_fire_pipes(
        total_length_m: float,
        elbows_per_20m: float = 3.0,
        tees_per_30m: float = 1.0,
        reducers_per_40m: float = 0.5,
        flanges_per_50m: float = 0.5,
        valves_per_50m: float = 0.5,
        drains_per_100m: float = 0.5,
        air_release_per_100m: float = 0.5,
        meta: Optional[Dict[str, Any]] = None,
    ) -> FittingsResult:
        """
        Estimate fire main fittings (elbows, tees, reducers, flanges, valves, drains).

        Rule-of-thumb densities:
        - elbows_per_20m     : average 90° changes / 20 m
        - tees_per_30m       : connections to branches / 30 m
        - reducers_per_40m   : size changes / 40 m
        - flanges_per_50m    : flange joints / 50 m
        - valves_per_50m     : isolation valves / 50 m
        - drains_per_100m    : drain valves / 100 m
        - air_release_per_100m : air release valves / 100 m

        These should be tuned to your normal detailing. The goal here is to
        get **order-of-magnitude** counts for the BOQ.
        """
        L = max(float(total_length_m), 0.0)

        import math
        e90 = int(math.ceil(elbows_per_20m * (L / 20.0))) if L > 0 else 0
        tees = int(math.ceil(tees_per_30m * (L / 30.0))) if L > 0 else 0
        red = int(math.ceil(reducers_per_40m * (L / 40.0))) if L > 0 else 0
        flg = int(math.ceil(flanges_per_50m * (L / 50.0))) if L > 0 else 0
        vls = int(math.ceil(valves_per_50m * (L / 50.0))) if L > 0 else 0
        drn = int(math.ceil(drains_per_100m * (L / 100.0))) if L > 0 else 0
        air = int(math.ceil(air_release_per_100m * (L / 100.0))) if L > 0 else 0

        meta_out = {
            "total_length_m": L,
            "elbows_per_20m": elbows_per_20m,
            "tees_per_30m": tees_per_30m,
            "reducers_per_40m": reducers_per_40m,
            "flanges_per_50m": flanges_per_50m,
            "valves_per_50m": valves_per_50m,
            "drains_per_100m": drains_per_100m,
            "air_release_per_100m": air_release_per_100m,
        }
        if meta:
            meta_out.update(meta)

        return FittingsResult(
            elbows_90=max(e90, 0),
            tees=max(tees, 0),
            reducers=max(red, 0),
            flanges=max(flg, 0),
            valves=max(vls, 0),
            drains=max(drn, 0),
            air_release=max(air, 0),
            meta=meta_out,
        )

    # ---------------------------------------------------------------------
    # 5. Pump duty estimation
    # ---------------------------------------------------------------------
    @staticmethod
    def pump_duty_estimate(
        flow_lpm: float,
        head_m: float,
        pump_efficiency: float = 0.7,
        motor_efficiency: float = 0.9,
        meta: Optional[Dict[str, Any]] = None,
    ) -> FirePumpDuty:
        """
        Rough pump duty estimation for fire pumps.

        Hydraulic power:
            P_hyd (kW) = (Q * H * ρ * g) / 3.6e6
                       ≈ (flow_lps * head_m * 9.81) / 1000

        Where:
            flow_lps = flow_lpm / 60
            ρ ≈ 1000 kg/m³, g ≈ 9.81 m/s²

        Shaft power:
            P_shaft = P_hyd / pump_efficiency

        Motor power:
            P_motor = P_shaft / motor_efficiency

        Parameters
        ----------
        flow_lpm : float
            Design flow in l/min.
        head_m : float
            Design head in metres.
        pump_efficiency : float
        motor_efficiency : float

        Returns
        -------
        FirePumpDuty
        """
        from math import isfinite

        flow_lpm = max(float(flow_lpm), 0.0)
        head_m = max(float(head_m), 0.0)
        pump_efficiency = max(min(float(pump_efficiency), 1.0), 0.1)
        motor_efficiency = max(min(float(motor_efficiency), 1.0), 0.1)

        if flow_lpm <= 0.0 or head_m <= 0.0:
            return FirePumpDuty(
                flow_lpm=flow_lpm,
                head_m=head_m,
                power_kw=0.0,
                meta=meta or {},
            )

        flow_lps = flow_lpm / 60.0
        rho = 1000.0
        g = 9.81

        # Hydraulic power in kW
        p_hyd = (flow_lps * head_m * rho * g) / 1000.0  # W→kW
        p_shaft = p_hyd / pump_efficiency
        p_motor = p_shaft / motor_efficiency

        if not isfinite(p_motor):
            p_motor = 0.0

        meta_out = {
            "pump_efficiency": pump_efficiency,
            "motor_efficiency": motor_efficiency,
            "flow_lps": flow_lps,
            "rho": rho,
            "g": g,
            "P_hyd_kW": p_hyd,
            "P_shaft_kW": p_shaft,
        }
        if meta:
            meta_out.update(meta)

        return FirePumpDuty(
            flow_lpm=flow_lpm,
            head_m=head_m,
            power_kw=round(p_motor, 1),
            meta=meta_out,
        )
```
