from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, Any, List, Optional


@dataclass
class AdministrativeApproval:
    aa_number: str
    aa_date: datetime
    authority: str        # e.g. SE/CE
    amount_sanctioned: float
    remarks: str = ""

    def to_dict(self): return asdict(self)


@dataclass
class ExpenditureSanction:
    es_number: str
    es_date: datetime
    authority: str
    amount_sanctioned: float
    head_of_account: str
    remarks: str = ""

    def to_dict(self): return asdict(self)


@dataclass
class TechnicalSanction:
    ts_number: str
    ts_date: datetime
    authority: str        # EE/SE
    amount_approved: float
    remarks: str = ""

    def to_dict(self): return asdict(self)


@dataclass
class NIT:
    nit_number: str
    nit_date: datetime
    name_of_work: str
    estimated_cost: float
    emd_amount: float
    completion_time_days: int
    tender_type: str          # Open / Limited / Item Rate / % Rate
    eligibility_criteria: str
    document_fee: float = 0.0
    remarks: str = ""

    def to_dict(self): return asdict(self)


@dataclass
class Bidder:
    name: str
    registration_class: str
    registration_dept: str
    pan: str
    gst: str
    solvency_amount: float
    experience_value: float
    emd_paid: float
    affidavits_ok: bool
    other_docs_ok: bool
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self): return asdict(self)


@dataclass
class Bid:
    bidder_name: str
    technical_qualified: bool
    quoted_amount: float          # total value from BOQ
    discount_pct: float = 0.0
    remarks: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self): return asdict(self)


@dataclass
class LetterOfAcceptance:
    loa_number: str
    loa_date: datetime
    bidder_name: str
    accepted_amount: float
    completion_time_days: int
    remarks: str = ""

    def to_dict(self): return asdict(self)


@dataclass
class PerformanceGuarantee:
    pct_required: float     # e.g., 3 to 5%
    amount_required: float
    received: bool = False
    instrument_details: str = ""

    def to_dict(self): return asdict(self)


@dataclass
class WorkOrder:
    wo_number: str
    wo_date: datetime
    name_of_work: str
    contractor_name: str
    contract_amount: float
    date_of_start: datetime
    date_of_completion: datetime
    time_allowed: str        # e.g. "6 (Six) Months"
    remarks: str = ""

    def to_dict(self): return asdict(self)
