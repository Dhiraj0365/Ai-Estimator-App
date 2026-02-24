```python
# engines/elec_engine.py

"""
Electrical Estimation Engine (Building Services)

This module provides reusable helpers for *estimation-level* electrical
quantities. It is **not** a detailed design tool; it encodes standard
CPWD / IS 732 style assumptions used by estimators:

- Number of circuits from number of points.
- Approximate conduit length from room geometry & point count.
- Approximate wire length (phase + neutral + earth) from conduit length.
- Simple feeder / cable run helpers.
- Earthing conductor length.

Typical use:
- In composites_mep.py you call these functions to convert:
    "N lighting points on this floor" → m of conduit + m of wire,
  which are then multiplied by CPWD DSR/SoR rates.

All functions are **UI-agnostic** (no Streamlit imports) and can be
used from tests or other front-ends.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional


# =============================================================================
# Result dataclasses
# =============================================================================

@dataclass
class CircuitSummary:
    """
    Summary of lighting / power circuits from point count.

    Attributes
    ----------
    points            : int   - total number of points (lights, fans, sockets, etc.)
    max_points_per_circuit : int
    circuits          : int   - required number of circuits.
    avg_points_per_circuit  : float
    meta              : dict  - free-form info (e.g. category: 'lighting'/'power').
    """

    points: int
    max_points_per_circuit: int
    circuits: int
    avg_points_per_circuit: float
    meta: Dict[str, Any] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class WiringRunResult:
    """
    Result of a point wiring estimation for a group of points.

    Attributes
    ----------
    points             : int     - number of points served.
    circuits           : int     - number of circuits.
    conduit_length_m   : float   - total linear metres of conduit.
    wire_length_m      : float   - total metres of phase + neutral wires.
    earthwire_length_m : float   - total metres of earth wire (if any).
    conduit_unit       : str     - usually "m".
    wire_unit          : str     - usually "m".
    meta               : dict    - includes assumptions used (wastage, cores, etc.).
    """

    points: int
    circuits: int
    conduit_length_m: float
    wire_length_m: float
    earthwire_length_m: float
    conduit_unit: str = "m"
    wire_unit: str = "m"
    meta: Dict[str, Any] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CableRunResult:
    """
    Result of a feeder / cable run estimation.

    Attributes
    ----------
    route_length_m   : float  - main route centre-line length.
    cable_length_m   : float  - length including bends and wastage.
    cores            : int    - number of cores in cable.
    unit             : str    - "m".
    meta             : dict   - assumptions.
    """

    route_length_m: float
    cable_length_m: float
    cores: int
    unit: str = "m"
    meta: Dict[str, Any] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EarthingRunResult:
    """
    Earthing conductor length summary.

    Attributes
    ----------
    electrodes         : int    - number of earth electrodes.
    main_earth_length  : float  - main earth conductor length (m).
    branch_earth_length: float  - total branch earth leads (m).
    unit               : str    - "m".
    meta               : dict   - notes/assumptions.
    """

    electrodes: int
    main_earth_length: float
    branch_earth_length: float
    unit: str = "m"
    meta: Dict[str, Any] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# =============================================================================
# Engine
# =============================================================================

class ElecEngine:
    """
    Electrical estimation helpers.

    All methods make **reasonable estimation assumptions**, not exact
    design-level computations. You should tune factors for your own
    practice if needed (e.g., wastage %, vertical drops, etc.).
    """

    # ---------------------------------------------------------------------
    # 1. Circuits from point count
    # ---------------------------------------------------------------------
    @staticmethod
    def circuits_from_points(
        points: int,
        max_points_per_circuit: int = 8,
        meta: Optional[Dict[str, Any]] = None,
    ) -> CircuitSummary:
        """
        Compute number of circuits required for given number of points.

        As per common practice (IS 732 / CPWD E&M):
        - Lighting: often 8–10 points per 6A circuit.
        - Power: fewer points per circuit (e.g., 4–6 sockets for 16A).

        Parameters
        ----------
        points : int
            Total number of points (e.g., light/fan/sockets).
        max_points_per_circuit : int
            Design limit for points per circuit.

        Returns
        -------
        CircuitSummary
        """
        p = max(int(points), 0)
        m = max(int(max_points_per_circuit), 1)

        if p == 0:
            return CircuitSummary(
                points=0,
                max_points_per_circuit=m,
                circuits=0,
                avg_points_per_circuit=0.0,
                meta=meta or {},
            )

        circuits = (p + m - 1) // m  # ceil division
        avg = p / circuits if circuits > 0 else 0.0

        return CircuitSummary(
            points=p,
            max_points_per_circuit=m,
            circuits=circuits,
            avg_points_per_circuit=avg,
            meta=meta or {},
        )

    # ---------------------------------------------------------------------
    # 2. Point wiring estimation (lighting / small power)
    # ---------------------------------------------------------------------
    @staticmethod
    def point_wiring_estimate(
        points: int,
        avg_horizontal_run_m: float,
        vertical_drop_m: float = 3.0,
        max_points_per_circuit: int = 8,
        wires_per_point: int = 2,     # typically phase + neutral
        include_earth: bool = True,
        conduit_wastage_factor: float = 1.10,
        wire_wastage_factor: float = 1.10,
        meta: Optional[Dict[str, Any]] = None,
    ) -> WiringRunResult:
        """
        Estimate conduit & wire quantities for point wiring.

        Assumptions (can be changed by parameters):
        - Average horizontal route per point from switchboard/DB to point
          is approx `avg_horizontal_run_m`.
        - Vertical rise/drop per point is `vertical_drop_m`.
        - Total conduit length = (horizontal + vertical) × conduit_wastage_factor.
        - Total wire length = conduit_length × wires_per_point (phase+neutral)
          × wire_wastage_factor.
        - Earth wire (if included) uses same conduit length × wire_wastage_factor.

        This is deliberately simple but practical for BOQ estimation.

        Parameters
        ----------
        points : int
            Number of points served (e.g., lights+fans).
        avg_horizontal_run_m : float
            Average horizontal route per point (m).
        vertical_drop_m : float
            Average vertical rise/drop per point (m).
        max_points_per_circuit : int
            Points per circuit.
        wires_per_point : int
            Number of current-carrying conductors per point (phase + neutral).
        include_earth : bool
            Whether to include earth wire for each point.
        conduit_wastage_factor : float
            Factor >1 to allow for bends, wastage, overlaps (e.g., 1.10).
        wire_wastage_factor : float
            Factor >1 to allow for wastage and terminations (e.g., 1.10).

        Returns
        -------
        WiringRunResult
        """
        points = max(int(points), 0)
        if points == 0:
            return WiringRunResult(
                points=0,
                circuits=0,
                conduit_length_m=0.0,
                wire_length_m=0.0,
                earthwire_length_m=0.0,
                meta=meta or {},
            )

        # Determine circuits
        circ_summary = ElecEngine.circuits_from_points(
            points=points,
            max_points_per_circuit=max_points_per_circuit,
            meta={"wires_per_point": wires_per_point},
        )

        # Base runs (without wastage)
        horizontal_total = float(points) * max(float(avg_horizontal_run_m), 0.0)
        vertical_total = float(points) * max(float(vertical_drop_m), 0.0)
        base_conduit = horizontal_total + vertical_total

        # Apply wastage for conduit
        conduit_length = base_conduit * max(float(conduit_wastage_factor), 1.0)

        # Wire length: for each point, wires_per_point cores share same conduit route
        base_wire = conduit_length * max(int(wires_per_point), 1)
        wire_length = base_wire * max(float(wire_wastage_factor), 1.0)

        earthwire_length = 0.0
        if include_earth:
            # One earth core per point (same conduit route)
            base_earth = conduit_length
            earthwire_length = base_earth * max(float(wire_wastage_factor), 1.0)

        meta_out = {
            "avg_horizontal_run_m": avg_horizontal_run_m,
            "vertical_drop_m": vertical_drop_m,
            "wires_per_point": wires_per_point,
            "include_earth": include_earth,
            "conduit_wastage_factor": conduit_wastage_factor,
            "wire_wastage_factor": wire_wastage_factor,
        }
        if meta:
            meta_out.update(meta)

        return WiringRunResult(
            points=points,
            circuits=circ_summary.circuits,
            conduit_length_m=round(conduit_length, 2),
            wire_length_m=round(wire_length, 2),
            earthwire_length_m=round(earthwire_length, 2),
            meta=meta_out,
        )

    # ---------------------------------------------------------------------
    # 3. Feeder / cable run estimation
    # ---------------------------------------------------------------------
    @staticmethod
    def cable_run_estimate(
        route_length_m: float,
        up_down_factor: float = 1.05,
        wastage_factor: float = 1.05,
        cores: int = 3,
        meta: Optional[Dict[str, Any]] = None,
    ) -> CableRunResult:
        """
        Estimate cable length for a feeder run between two switchboards/panels.

        Assumptions:
        - route_length_m is the centre-line length along the cable tray/conduit.
        - up_down_factor accounts for vertical rises/drops at both ends.
        - wastage_factor accounts for slack, cutting, terminations.

        cable_length = route_length_m × up_down_factor × wastage_factor

        cores is recorded but does not change length (number of conductors per
        cable; cost will come from DSR item for correct core size).
        """
        route = max(float(route_length_m), 0.0)
        up_down_factor = max(float(up_down_factor), 1.0)
        wastage_factor = max(float(wastage_factor), 1.0)
        cores = max(int(cores), 1)

        cable_length = route * up_down_factor * wastage_factor

        meta_out = {
            "up_down_factor": up_down_factor,
            "wastage_factor": wastage_factor,
        }
        if meta:
            meta_out.update(meta)

        return CableRunResult(
            route_length_m=round(route, 2),
            cable_length_m=round(cable_length, 2),
            cores=cores,
            meta=meta_out,
        )

    # ---------------------------------------------------------------------
    # 4. Earthing conductor estimation
    # ---------------------------------------------------------------------
    @staticmethod
    def earthing_conductor_estimate(
        electrodes: int,
        main_earth_route_m: float,
        avg_branch_length_m: float,
        branches_per_floor: int,
        floors: int,
        wastage_factor: float = 1.10,
        meta: Optional[Dict[str, Any]] = None,
    ) -> EarthingRunResult:
        """
        Estimate earthing conductor length for a building.

        Parameters
        ----------
        electrodes : int
            Number of earth electrodes (e.g., GI pipe earths, chemical earths).
        main_earth_route_m : float
            Approximate main earth conductor (earth bus) route distance (m)
            from earth pit area to main electrical room(s) and vertical riser.
        avg_branch_length_m : float
            Average length of each branch earth lead (m) from main earth bar
            or riser to local DBs / equipment per floor.
        branches_per_floor : int
            Number of earth branches per floor.
        floors : int
            Number of floors served by this earthing system.
        wastage_factor : float
            Wastage factor for cutting, terminations, routing.

        Returns
        -------
        EarthingRunResult
        """
        electrodes = max(int(electrodes), 0)
        main_earth_route_m = max(float(main_earth_route_m), 0.0)
        avg_branch_length_m = max(float(avg_branch_length_m), 0.0)
        branches_per_floor = max(int(branches_per_floor), 0)
        floors = max(int(floors), 0)
        wastage_factor = max(float(wastage_factor), 1.0)

        # Main earth conductor (bus) length
        main_len = main_earth_route_m * wastage_factor

        # Branch earth leads: total branches = branches_per_floor × floors
        total_branches = branches_per_floor * floors
        branch_len = avg_branch_length_m * total_branches * wastage_factor

        meta_out = {
            "branches_per_floor": branches_per_floor,
            "floors": floors,
            "wastage_factor": wastage_factor,
        }
        if meta:
            meta_out.update(meta)

        return EarthingRunResult(
            electrodes=electrodes,
            main_earth_length=round(main_len, 2),
            branch_earth_length=round(branch_len, 2),
            meta=meta_out,
        )
```
