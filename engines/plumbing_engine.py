"""
Plumbing Estimation Engine (Water Supply & Drainage)

This module provides *estimation-level* helpers for plumbing quantities.
It is NOT a full hydraulic design; it encodes common CPWD / NBC / good
practice assumptions used by estimators:

- Approximate water-supply riser + branch pipe lengths from building geometry.
- Approximate drainage stack + branch pipe lengths.
- Fittings count from pipe length (elbows, tees, reducers, sockets).
- Sanitary fixture groupings.

You typically use these functions inside composites_mep.py to translate
building-level inputs (floors, fixtures/floor, stack counts) into:

    → m of pipe
    → number of fittings
    → number of fixtures

Then you map these to DSR/SoR items (PVC/CPVC/GI pipes, bends, tees,
traps, WCs, basins, taps, etc.) and multiply by rates.

All functions are UI-agnostic (no Streamlit), suitable for tests or
any front-end.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional


# =============================================================================
# Result dataclasses
# =============================================================================

@dataclass
class PipeRunResult:
    """
    Summary of a water-supply or drainage pipe run.

    Attributes
    ----------
    total_length_m  : float  - total pipe length including wastage.
    header_length_m : float  - horizontal header / main length.
    riser_length_m  : float  - vertical riser length (sum of risers).
    branch_length_m : float  - horizontal branches to fixtures/stacks.
    unit            : str    - "m".
    meta            : dict   - notes/assumptions, breakdown by cold/hot, etc.
    """

    total_length_m: float
    header_length_m: float
    riser_length_m: float
    branch_length_m: float
    unit: str = "m"
    meta: Dict[str, Any] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class FittingsResult:
    """
    Estimated count of pipe fittings for a given run.

    Attributes
    ----------
    elbows_90      : int
    elbows_45      : int
    tees           : int
    reducers       : int
    sockets        : int
    cleaning_eye   : int   - for drainage; 0 for water supply if not used.
    traps          : int   - for drainage; 0 for water supply.
    meta           : dict
    """

    elbows_90: int
    elbows_45: int
    tees: int
    reducers: int
    sockets: int
    cleaning_eye: int = 0
    traps: int = 0
    meta: Dict[str, Any] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class FixtureGroupResult:
    """
    Summary of sanitary fixtures / water points.

    Attributes
    ----------
    wc_count          : int  - number of WCs.
    basin_count       : int  - number of wash basins.
    urinal_count      : int
    kitchen_sink_count: int
    floor_trap_count  : int
    nahani_trap_count : int
    other_fixtures    : dict - key -> count (showers, bib taps, health faucets etc.)
    meta              : dict - notes/assumptions.
    """

    wc_count: int
    basin_count: int
    urinal_count: int
    kitchen_sink_count: int
    floor_trap_count: int
    nahani_trap_count: int
    other_fixtures: Dict[str, int] = None
    meta: Dict[str, Any] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# =============================================================================
# Engine
# =============================================================================

class PlumbingEngine:
    """
    Plumbing estimation helpers.

    These methods implement *simple but reasonable* rules that estimators
    use to quickly convert building data into pipe + fitting quantities.
    You should tune the factors (wastage, branch lengths, fittings/10m, etc.)
    to match your practice and past projects.
    """

    # ---------------------------------------------------------------------
    # 1. Water supply – riser & branch distribution
    # ---------------------------------------------------------------------
    @staticmethod
    def water_risers_and_branches(
        floors: int,
        floor_height_m: float,
        risers: int,
        main_header_length_m: float,
        fixtures_per_floor: int,
        avg_branch_length_per_fixture_m: float,
        wastage_factor: float = 1.10,
        meta: Optional[Dict[str, Any]] = None,
    ) -> PipeRunResult:
        """
        Simple estimate of total water supply pipe length for a building.

        Model:
        - Vertical riser length:
            riser_length = floors * floor_height_m * risers
        - Horizontal main header on ground/terrace:
            header_length_m as given.
        - Horizontal branches to fixtures per floor:
            branch_length = floors * fixtures_per_floor * avg_branch_length_per_fixture_m
        - Total base length = riser + header + branch
        - Total including wastage:
            total = base * wastage_factor

        Parameters
        ----------
        floors : int
            Number of storeys served by these risers.
        floor_height_m : float
            Typical floor-to-floor height (m).
        risers : int
            Number of separate riser pipes (cold, hot, zoned etc.).
        main_header_length_m : float
            Summed length of main headers (basement + overhead tank connections).
        fixtures_per_floor : int
            Number of water-supplied fixtures per floor.
        avg_branch_length_per_fixture_m : float
            Average length from riser/header to each fixture (m).
        wastage_factor : float
            Wastage / allowance factor (>1.0) for bends, offsets, cutting.

        Returns
        -------
        PipeRunResult
        """
        floors = max(int(floors), 0)
        risers = max(int(risers), 0)
        floor_height_m = max(float(floor_height_m), 0.0)
        main_header_length_m = max(float(main_header_length_m), 0.0)
        fixtures_per_floor = max(int(fixtures_per_floor), 0)
        avg_branch_length_per_fixture_m = max(float(avg_branch_length_per_fixture_m), 0.0)
        wastage_factor = max(float(wastage_factor), 1.0)

        # Vertical riser length
        riser_length = floors * floor_height_m * risers

        # Horizontal branches
        total_fixtures = floors * fixtures_per_floor
        branch_length = total_fixtures * avg_branch_length_per_fixture_m

        # Base total
        base_total = riser_length + main_header_length_m + branch_length

        total_length = base_total * wastage_factor

        meta_out = {
            "floors": floors,
            "floor_height_m": floor_height_m,
            "risers": risers,
            "fixtures_per_floor": fixtures_per_floor,
            "avg_branch_length_per_fixture_m": avg_branch_length_per_fixture_m,
            "wastage_factor": wastage_factor,
        }
        if meta:
            meta_out.update(meta)

        return PipeRunResult(
            total_length_m=round(total_length, 2),
            header_length_m=round(main_header_length_m * wastage_factor, 2),
            riser_length_m=round(riser_length * wastage_factor, 2),
            branch_length_m=round(branch_length * wastage_factor, 2),
            meta=meta_out,
        )

    # ---------------------------------------------------------------------
    # 2. Drainage – soil & waste stacks, branches, building drains
    # ---------------------------------------------------------------------
    @staticmethod
    def drainage_stacks_and_branches(
        floors: int,
        floor_height_m: float,
        stacks: int,
        building_drain_length_m: float,
        sanitary_fixtures_per_floor: int,
        avg_branch_length_per_fixture_m: float,
        wastage_factor: float = 1.10,
        meta: Optional[Dict[str, Any]] = None,
    ) -> PipeRunResult:
        """
        Simple estimate of total drainage pipe length.

        Model:
        - Vertical soil/waste stack length:
            stack_length = floors * floor_height_m * stacks
        - Building drain (collector) length:
            building_drain_length_m as given.
        - Branch connections from fixtures to stacks:
            branch_length = floors * sanitary_fixtures_per_floor * avg_branch_length_per_fixture_m
        - Total base = stack_length + building_drain + branch_length
        - Total including wastage:
            total = base * wastage_factor

        Parameters
        ----------
        floors : int
        floor_height_m : float
        stacks : int
        building_drain_length_m : float
            Ground level collector drains, from stacks to manholes/outfall.
        sanitary_fixtures_per_floor : int
            WCs, basins, sinks, floor traps that connect to drainage.
        avg_branch_length_per_fixture_m : float
        wastage_factor : float

        Returns
        -------
        PipeRunResult
        """
        floors = max(int(floors), 0)
        stacks = max(int(stacks), 0)
        floor_height_m = max(float(floor_height_m), 0.0)
        building_drain_length_m = max(float(building_drain_length_m), 0.0)
        sanitary_fixtures_per_floor = max(int(sanitary_fixtures_per_floor), 0)
        avg_branch_length_per_fixture_m = max(float(avg_branch_length_per_fixture_m), 0.0)
        wastage_factor = max(float(wastage_factor), 1.0)

        stack_length = floors * floor_height_m * stacks
        total_fixtures = floors * sanitary_fixtures_per_floor
        branch_length = total_fixtures * avg_branch_length_per_fixture_m

        base_total = stack_length + building_drain_length_m + branch_length
        total_length = base_total * wastage_factor

        meta_out = {
            "floors": floors,
            "floor_height_m": floor_height_m,
            "stacks": stacks,
            "sanitary_fixtures_per_floor": sanitary_fixtures_per_floor,
            "avg_branch_length_per_fixture_m": avg_branch_length_per_fixture_m,
            "wastage_factor": wastage_factor,
        }
        if meta:
            meta_out.update(meta)

        return PipeRunResult(
            total_length_m=round(total_length, 2),
            header_length_m=round(building_drain_length_m * wastage_factor, 2),
            riser_length_m=round(stack_length * wastage_factor, 2),
            branch_length_m=round(branch_length * wastage_factor, 2),
            meta=meta_out,
        )

    # ---------------------------------------------------------------------
    # 3. Fittings estimate from pipe length
    # ---------------------------------------------------------------------
    @staticmethod
    def fittings_from_pipe_length(
        total_length_m: float,
        elbows_90_per_10m: float = 4.0,
        elbows_45_per_10m: float = 1.0,
        tees_per_10m: float = 1.0,
        reducers_per_30m: float = 1.0,
        sockets_per_10m: float = 2.0,
        include_traps: bool = False,
        traps_per_10m: float = 0.0,
        include_cleanouts: bool = False,
        cleanouts_per_30m: float = 0.0,
        meta: Optional[Dict[str, Any]] = None,
    ) -> FittingsResult:
        """
        Estimate number of fittings from a given pipe length.

        This is a RULE-OF-THUMB style helper:

            elbows_90 ≈ elbows_90_per_10m × (total_length_m / 10)
            tees      ≈ tees_per_10m      × (total_length_m / 10)
            reducers  ≈ reducers_per_30m  × (total_length_m / 30)
            sockets   ≈ sockets_per_10m   × (total_length_m / 10)
            traps     ≈ traps_per_10m     × (total_length_m / 10) if include_traps
            cleaning_eye ≈ cleanouts_per_30m × (total_length_m / 30) if include_cleanouts

        You can tune densities (per 10m / 30m) for different systems:
        - Water supply: more elbows, fewer traps.
        - Drainage: more cleanouts/traps, perhaps fewer elbows.

        Returns an integer estimate of each fitting type.
        """
        L = max(float(total_length_m), 0.0)

        e90 = int(round(elbows_90_per_10m * (L / 10.0)))
        e45 = int(round(elbows_45_per_10m * (L / 10.0)))
        tees = int(round(tees_per_10m * (L / 10.0)))
        red = int(round(reducers_per_30m * (L / 30.0)))
        soc = int(round(sockets_per_10m * (L / 10.0)))

        traps = 0
        if include_traps and traps_per_10m > 0.0:
            traps = int(round(traps_per_10m * (L / 10.0)))

        clean_eye = 0
        if include_cleanouts and cleanouts_per_30m > 0.0:
            clean_eye = int(round(cleanouts_per_30m * (L / 30.0)))

        meta_out = {
            "total_length_m": L,
            "elbows_90_per_10m": elbows_90_per_10m,
            "elbows_45_per_10m": elbows_45_per_10m,
            "tees_per_10m": tees_per_10m,
            "reducers_per_30m": reducers_per_30m,
            "sockets_per_10m": sockets_per_10m,
            "traps_per_10m": traps_per_10m if include_traps else 0.0,
            "cleanouts_per_30m": cleanouts_per_30m if include_cleanouts else 0.0,
        }
        if meta:
            meta_out.update(meta)

        return FittingsResult(
            elbows_90=max(e90, 0),
            elbows_45=max(e45, 0),
            tees=max(tees, 0),
            reducers=max(red, 0),
            sockets=max(soc, 0),
            cleaning_eye=max(clean_eye, 0),
            traps=max(traps, 0),
            meta=meta_out,
        )

    # ---------------------------------------------------------------------
    # 4. Fixture grouping – count fixtures for BOQ
    # ---------------------------------------------------------------------
    @staticmethod
    def fixture_group(
        wc_per_toilet: int,
        toilet_blocks: int,
        basins_per_toilet: int,
        urinals_per_block: int = 0,
        kitchen_sinks: int = 0,
        floor_traps_per_block: int = 0,
        nahani_traps_per_block: int = 0,
        extra_fixtures: Optional[Dict[str, int]] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> FixtureGroupResult:
        """
        Compute total fixtures from basic toilet block counts.

        Parameters
        ----------
        wc_per_toilet : int
            Number of WCs per toilet block (e.g., 2 per toilet).
        toilet_blocks : int
            Number of toilet blocks on all floors.
        basins_per_toilet : int
            Number of wash basins per toilet block.
        urinals_per_block : int
            Urinals per toilet block (for male toilets).
        kitchen_sinks : int
            Count of kitchen sinks in the building (total).
        floor_traps_per_block : int
            Number of floor traps per toilet block (if separate).
        nahani_traps_per_block : int
            Nahani traps in bathrooms/wash areas per block.
        extra_fixtures : dict
            key->count, e.g. {"showers": 10, "health_faucets": 20}.
        meta : dict
            Additional notes/assumptions.

        Returns
        -------
        FixtureGroupResult
        """
        toilet_blocks = max(int(toilet_blocks), 0)
        wc_per_toilet = max(int(wc_per_toilet), 0)
        basins_per_toilet = max(int(basins_per_toilet), 0)
        urinals_per_block = max(int(urinals_per_block), 0)
        kitchen_sinks = max(int(kitchen_sinks), 0)
        floor_traps_per_block = max(int(floor_traps_per_block), 0)
        nahani_traps_per_block = max(int(nahani_traps_per_block), 0)

        wc_total = toilet_blocks * wc_per_toilet
        basin_total = toilet_blocks * basins_per_toilet
        urinal_total = toilet_blocks * urinals_per_block
        floor_trap_total = toilet_blocks * floor_traps_per_block
        nahani_trap_total = toilet_blocks * nahani_traps_per_block

        other = dict(extra_fixtures or {})

        meta_out = {
            "toilet_blocks": toilet_blocks,
            "wc_per_toilet": wc_per_toilet,
            "basins_per_toilet": basins_per_toilet,
            "urinals_per_block": urinals_per_block,
            "floor_traps_per_block": floor_traps_per_block,
            "nahani_traps_per_block": nahani_traps_per_block,
        }
        if meta:
            meta_out.update(meta)

        return FixtureGroupResult(
            wc_count=wc_total,
            basin_count=basin_total,
            urinal_count=urinal_total,
            kitchen_sink_count=kitchen_sinks,
            floor_trap_count=floor_trap_total,
            nahani_trap_count=nahani_trap_total,
            other_fixtures=other,
            meta=meta_out,
        )
