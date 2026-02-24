# core/models.py

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Literal
from datetime import datetime


# =============================================================================
# QuantityResult – generic result of a measurement / IS 1200 computation
# =============================================================================

@dataclass
class QuantityResult:
    """
    Generic representation of a quantity calculation.

    Usually produced by measurement engines (IS1200Engine for civil, etc.).

    Attributes
    ----------
    gross       : float  - Gross measured quantity before deductions/additions.
    deductions  : float  - Deductions (e.g., openings, voids).
    additions   : float  - Additions (e.g., wastage, laps).
    net         : float  - Net payable quantity (gross - deductions + additions).
    unit        : str    - Unit of measurement (cum, sqm, m, kg, each, etc.).
    meta        : dict   - Extra info (e.g., pct_deduction, rule_used, notes).
    """

    gross: float
    deductions: float = 0.0
    additions: float = 0.0
    net: float = 0.0
    unit: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any], unit: Optional[str] = None) -> "QuantityResult":
        """
        Create a QuantityResult from a dict produced by engines like IS1200Engine.
        Expected keys at minimum: 'gross', 'deductions', 'additions', 'net'.
        """
        return cls(
            gross=float(data.get("gross", 0.0)),
            deductions=float(data.get("deductions", 0.0)),
            additions=float(data.get("additions", 0.0)),
            net=float(data.get("net", 0.0)),
            unit=unit or str(data.get("unit", "")),
            meta={k: v for k, v in data.items() if k not in {"gross", "deductions", "additions", "net", "unit"}},
        )

    def to_dict(self) -> Dict[str, Any]:
        """Return a serialisable dict representation."""
        return asdict(self)


# =============================================================================
# Item – one DSR/SoR line (master data)
# =============================================================================

@dataclass
class Item:
    """
    One DSR/SoR item as used by the estimator.

    Typically loaded from CPWD/State SoR CSV via knowledge.dsr_master.
    Matches one row of cpwd_dsr_civil_2023.csv:

        item_key, code, description, unit, rate, category, type,
        measurement_rule, discipline
    """

    # Key in CPWD_BASE_DSR_2023 – e.g. "Earth work in excavation ... (2.8.1)"
    key: str

    # Core SoR fields
    code: str
    description: str
    unit: str
    base_rate: float

    # Classification / behavior
    category: str = ""          # earthwork, concrete, brickwork, plaster, tiles, painting, etc.
    measure_type: str = "volume"  # volume, area, length, weight, each, lumpsum
    measurement_rule: str = ""  # which engine method to use, e.g. volume, trench_excavation, brickwork_wall
    discipline: str = "civil"   # civil, electrical, plumbing, hvac, fire, etc.

    # Extra metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dsr_record(cls, key: str, rec: Dict[str, Any]) -> "Item":
        """
        Instantiate Item from one entry of CPWD_BASE_DSR_2023[key].
        rec is a dict with keys: code, description, unit, rate, category, type, measurement_rule, discipline.
        """
        return cls(
            key=key,
            code=str(rec.get("code", "")),
            description=str(rec.get("description", "")),
            unit=str(rec.get("unit", "")),
            base_rate=float(rec.get("rate", 0.0)),
            category=str(rec.get("category", "")),
            measure_type=str(rec.get("type", "volume")),
            measurement_rule=str(rec.get("measurement_rule", "")),
            discipline=str(rec.get("discipline", "civil")),
            metadata={k: v for k, v in rec.items()
                      if k not in {"code", "description", "unit", "rate", "category", "type", "measurement_rule", "discipline"}},
        )

    def rate_at_index(self, cost_index: float) -> float:
        """
        Calculate location-adjusted rate based on cost index.
        Example: Delhi 100.0; a city with 110.0 index → rate * 1.10.
        """
        return self.base_rate * (cost_index / 100.0)

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to plain dict (for debugging, export, etc.)."""
        return {
            "key": self.key,
            "code": self.code,
            "description": self.description,
            "unit": self.unit,
            "base_rate": self.base_rate,
            "category": self.category,
            "measure_type": self.measure_type,
            "measurement_rule": self.measurement_rule,
            "discipline": self.discipline,
            "metadata": self.metadata,
        }


# =============================================================================
# BOQLine – one line in the Bill of Quantities
# =============================================================================

@dataclass
class BOQLine:
    """
    One entry in the working BOQ / SOQ.

    Attributes
    ----------
    id              : int      - running serial number in the BOQ.
    item_key        : str      - key to Item (DSR item_key).
    item            : Optional[Item] - resolved Item, for easy access.
    description     : str      - line description (default from Item.description).
    phase           : str      - construction phase ("1️⃣ SUBSTRUCTURE", "2️⃣ PLINTH", etc.).
    discipline      : str      - civil, electrical, plumbing, hvac, fire, etc.
    length,breadth,depth,height: float - geometric data (for MB & audit).
    quantity        : float    - net quantity.
    unit            : str      - unit.
    rate            : float    - applied rate (after index; without contingencies).
    amount          : float    - quantity * rate.
    category        : str      - engineering category (earthwork, rcc_concrete, plaster, etc.).
    source          : str      - "single_item" or "package: <name>" etc., for traceability.
    notes           : str      - technical/audit notes (e.g., IS 1200 rule, cure days).
    meta            : dict     - any additional metadata (e.g., package_name, rule_used).
    """

    id: int
    item_key: str
    description: str
    phase: str
    quantity: float
    unit: str
    rate: float
    amount: float

    # Optional linkage & classification
    item: Optional[Item] = None
    discipline: str = "civil"
    category: str = ""
    source: str = "single_item"
    notes: str = ""

    # Basic geometry for MB and IS-1200 auditing
    length: float = 0.0
    breadth: float = 0.0
    depth: float = 0.0
    height: float = 0.0

    # Auxiliary data
    meta: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_item(
        cls,
        line_id: int,
        item: Item,
        phase: str,
        quantity: float,
        rate: float,
        amount: Optional[float] = None,
        source: str = "single_item",
        notes: str = "",
        length: float = 0.0,
        breadth: float = 0.0,
        depth: float = 0.0,
        height: float = 0.0,
        meta: Optional[Dict[str, Any]] = None,
    ) -> "BOQLine":
        """
        Create a BOQ line from an Item and measured quantity.
        If amount is None, it is computed as quantity * rate.
        """
        if amount is None:
            amount = quantity * rate

        return cls(
            id=line_id,
            item_key=item.key,
            description=item.description,
            phase=phase,
            quantity=float(quantity),
            unit=item.unit,
            rate=float(rate),
            amount=float(amount),
            item=item,
            discipline=item.discipline,
            category=item.category,
            source=source,
            notes=notes,
            length=float(length),
            breadth=float(breadth),
            depth=float(depth),
            height=float(height),
            meta=meta or {},
        )

    def to_dict(self) -> Dict[str, Any]:
        """
        Serialise to dict suitable for DataFrame / CSV export.
        """
        return {
            "id": self.id,
            "item_key": self.item_key,
            "code": self.item.code if self.item else "",
            "description": self.description,
            "phase": self.phase,
            "discipline": self.discipline,
            "category": self.category,
            "length": self.length,
            "breadth": self.breadth,
            "depth": self.depth,
            "height": self.height,
            "quantity": self.quantity,
            "unit": self.unit,
            "rate": self.rate,
            "amount": self.amount,
            "source": self.source,
            "notes": self.notes,
            "meta": self.meta,
        }


# =============================================================================
# RuleResult – output from rules_civil / rules_elec / etc.
# =============================================================================

RuleLevel = Literal["ERROR", "WARNING", "INFO"]


@dataclass
class RuleResult:
    """
    Result of applying one validation / audit rule.

    Attributes
    ----------
    level      : "ERROR" / "WARNING" / "INFO".
    message    : human-readable explanation.
    discipline : affected discipline (civil, electrical, etc.).
    code       : optional short rule code (e.g., CIV-RCC-001).
    context    : optional context: line_id, item_code, phase, etc.
    """

    level: RuleLevel
    message: str
    discipline: str = "civil"
    code: str = ""
    context: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# =============================================================================
# Project – represents one full estimate (civil + MEP)
# =============================================================================

@dataclass
class Project:
    """
    Aggregation of all BOQ lines and metadata for one project.

    This is the central object you could save/load as JSON or in a DB.

    Attributes
    ----------
    name         : project name.
    client       : client/owner.
    engineer     : engineer preparing the estimate.
    location     : city/location string (used with LOCATION_INDICES).
    sor_source   : e.g., "CPWD DSR 2023 Civil + E&M", "PWD Rajasthan 2023".
    cost_index   : float – location index (100.0 for base).
    created_at   : timestamp.
    updated_at   : timestamp.
    boq_lines    : list of BOQLine entries.
    meta         : project-level metadata (storeys, building type, etc.).
    """

    name: str
    client: str
    engineer: str
    location: str
    sor_source: str = "CPWD DSR 2023"
    cost_index: float = 100.0
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    boq_lines: List[BOQLine] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)

    # ----- Basic aggregates -----

    def total_amount(self) -> float:
        return float(sum(line.amount for line in self.boq_lines))

    def total_by_phase(self) -> Dict[str, float]:
        out: Dict[str, float] = {}
        for line in self.boq_lines:
            out[line.phase] = out.get(line.phase, 0.0) + line.amount
        return out

    def total_by_discipline(self) -> Dict[str, float]:
        out: Dict[str, float] = {}
        for line in self.boq_lines:
            out[line.discipline] = out.get(line.discipline, 0.0) + line.amount
        return out

    def total_by_category(self) -> Dict[str, float]:
        out: Dict[str, float] = {}
        for line in self.boq_lines:
            key = line.category or "uncategorised"
            out[key] = out.get(key, 0.0) + line.amount
        return out

    # ----- Manipulation helpers -----

    def add_line(self, line: BOQLine) -> None:
        """Append a BOQLine and update timestamp."""
        self.boq_lines.append(line)
        self.updated_at = datetime.utcnow()

    def next_line_id(self) -> int:
        """Return the next available line ID."""
        if not self.boq_lines:
            return 1
        return max(l.id for l in self.boq_lines) + 1

    # ----- Serialisation -----

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "client": self.client,
            "engineer": self.engineer,
            "location": self.location,
            "sor_source": self.sor_source,
            "cost_index": self.cost_index,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "boq_lines": [line.to_dict() for line in self.boq_lines],
            "meta": self.meta,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Project":
        """
        Hydrate a Project from a dict (e.g., loaded from JSON).
        NOTE: This does not auto-resolve Item objects; item_key and other
        fields are preserved as plain data in BOQLine.
        """
        proj = cls(
            name=data.get("name", ""),
            client=data.get("client", ""),
            engineer=data.get("engineer", ""),
            location=data.get("location", ""),
            sor_source=data.get("sor_source", "CPWD DSR 2023"),
            cost_index=float(data.get("cost_index", 100.0)),
            created_at=datetime.fromisoformat(data.get("created_at"))
            if data.get("created_at") else datetime.utcnow(),
            updated_at=datetime.fromisoformat(data.get("updated_at"))
            if data.get("updated_at") else datetime.utcnow(),
            boq_lines=[],
            meta=data.get("meta", {}) or {},
        )

        for ld in data.get("boq_lines", []):
            line = BOQLine(
                id=int(ld.get("id", 0)),
                item_key=str(ld.get("item_key", "")),
                description=str(ld.get("description", "")),
                phase=str(ld.get("phase", "")),
                quantity=float(ld.get("quantity", 0.0)),
                unit=str(ld.get("unit", "")),
                rate=float(ld.get("rate", 0.0)),
                amount=float(ld.get("amount", 0.0)),
                discipline=str(ld.get("discipline", "civil")),
                category=str(ld.get("category", "")),
                source=str(ld.get("source", "")),
                notes=str(ld.get("notes", "")),
                length=float(ld.get("length", 0.0)),
                breadth=float(ld.get("breadth", 0.0)),
                depth=float(ld.get("depth", 0.0)),
                height=float(ld.get("height", 0.0)),
                meta=ld.get("meta", {}) or {},
            )
            proj.boq_lines.append(line)

        return proj
