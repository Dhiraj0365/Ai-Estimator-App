from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Dict, Any

import pandas as pd
import streamlit as st

from core.models import BOQLine, Item
from core.pricing import monte_carlo_amount
from engines.is1200_civil import IS1200Engine
from knowledge.dsr_master import (
    CPWD_BASE_DSR_2023,
    ITEMS,
    LOCATION_INDICES,
    PHASE_GROUPS,
    RATE_SOURCES,
)
from knowledge.composites_civil import WORK_PACKAGES_CIVIL, expand_work_package
from knowledge.composites_mep import WORK_PACKAGES_MEP, expand_mep_package
from rules.rules_runner import run_all_rules, group_results_by_level
from core.tender_models import (
    AdministrativeApproval,
    ExpenditureSanction,
    TechnicalSanction,
    NIT,
    Bidder,
    Bid,
    LetterOfAcceptance,
    PerformanceGuarantee,
    WorkOrder,
)


# =============================================================================
# Helpers
# =============================================================================

def format_rupees(amount: float) -> str:
    try:
        return f"₹{amount:,.0f}"
    except Exception:
        return "₹0"


def format_lakhs(amount: float) -> str:
    try:
        return f"{amount / 100000.0:,.2f} L"
    except Exception:
        return "0.00 L"


def _boqline_to_dict(line: BOQLine) -> Dict[str, Any]:
    """
    Convert BOQLine to a flat dict suitable for session_state.qto_items
    and for DataFrame / rules.
    """
    d = line.to_dict()
    # legacy-style fields for compatibility
    d["dsr_code"] = d.get("code", "")
    d["item"] = d.get("description", "")
    return d


def _next_id() -> int:
    return len(st.session_state.qto_items) + 1


# =============================================================================
# Streamlit setup & session state
# =============================================================================

st.set_page_config(
    page_title="CPWD / PWD AI Construction Estimator & Tender Engine",
    page_icon="🏗️",
    layout="wide",
)

# BOQ lines
if "qto_items" not in st.session_state:
    st.session_state.qto_items: List[Dict[str, Any]] = []

# Project meta
if "project_info" not in st.session_state:
    st.session_state.project_info = {
        "name": "G+1 Residential",
        "client": "CPWD Division",
        "engineer": "Er. Ravi Sharma",
        "location": "Delhi",
        "rate_source": "CPWD DSR 2023 (Civil + Elect)",
    }

# Tender engine state
if "aa" not in st.session_state:
    st.session_state.aa = None  # AdministrativeApproval

if "es" not in st.session_state:
    st.session_state.es = None  # ExpenditureSanction

if "ts" not in st.session_state:
    st.session_state.ts = None  # TechnicalSanction

if "nit" not in st.session_state:
    st.session_state.nit = None  # NIT

if "bidders" not in st.session_state:
    st.session_state.bidders: List[Dict[str, Any]] = []  # Bidder dicts

if "bids" not in st.session_state:
    st.session_state.bids: List[Dict[str, Any]] = []  # Bid dicts

if "loa" not in st.session_state:
    st.session_state.loa = None  # LetterOfAcceptance

if "pg" not in st.session_state:
    st.session_state.pg = None  # PerformanceGuarantee

if "work_order" not in st.session_state:
    st.session_state.work_order = None  # WorkOrder

# Civil package unlock state
if "civil_unlocked" not in st.session_state:
    st.session_state.civil_unlocked = False

# =============================================================================
# Header
# =============================================================================

st.markdown(
    """
<div style='background: linear-gradient(90deg, #1e3c72 0%, #2a5298 100%); padding:1.2rem; border-radius:0.7rem; color:white; text-align:center'>
  <h2 style='margin:0;'>🏗️ CPWD / PWD AI Estimator & Tender Engine</h2>
  <p style='margin:0.2rem 0 0;'>DSR-based Detailed Estimates, RCC packages (concrete + steel + formwork), audit rules, and end-to-end tender workflow (AA/ES → TS → NIT → L1 → LOA → PG → Work Order).</p>
</div>
""",
    unsafe_allow_html=True,
)

# =============================================================================
# Sidebar – Project / Rates
# =============================================================================

with st.sidebar:
    st.subheader("🏛️ Project Details")
    st.session_state.project_info["name"] = st.text_input(
        "Project Name", st.session_state.project_info["name"]
    )
    st.session_state.project_info["client"] = st.text_input(
        "Client", st.session_state.project_info["client"]
    )
    st.session_state.project_info["engineer"] = st.text_input(
        "Engineer", st.session_state.project_info["engineer"]
    )

    st.subheader("📍 Location & Rate Source")
    location = st.selectbox(
        "Location",
        list(LOCATION_INDICES.keys()),
        index=list(LOCATION_INDICES.keys()).index(
            st.session_state.project_info.get("location", "Delhi")
        ),
    )
    st.session_state.project_info["location"] = location
    cost_index = LOCATION_INDICES[location]
    st.info(f"Cost Index for **{location}**: **{cost_index:.1f}%** (Base = 100)")

    rate_source_names = list(RATE_SOURCES.keys())
    default_source = st.session_state.project_info.get("rate_source", rate_source_names[0])
    rate_source = st.selectbox(
        "Rate Source",
        rate_source_names,
        index=rate_source_names.index(default_source)
        if default_source in rate_source_names
        else 0,
    )
    st.session_state.project_info["rate_source"] = rate_source
    current_dsr = RATE_SOURCES[rate_source]

    st.subheader("⚙️ Pricing Adjustments (informational)")
    contingency_pct = st.slider("Contingency (%)", 0.0, 10.0, 5.0, 0.5)
    escalation_annual = st.slider("Escalation p.a. (%)", 0.0, 10.0, 5.0, 0.5)

# =============================================================================
# Dashboard metrics
# =============================================================================

total_cost = float(sum(item.get("amount", 0.0) for item in st.session_state.qto_items))
total_items = len(st.session_state.qto_items)

if total_cost > 0:
    mc = monte_carlo_amount(total_cost)
else:
    mc = {"p10": 0.0, "p50": 0.0, "p90": 0.0}

col0, col1, col2, col3, col4 = st.columns(5)
col0.metric("💰 Base Cost (Current BOQ)", format_rupees(total_cost))
col1.metric("📋 BOQ Lines", str(total_items))
col2.metric("📍 Cost Index", f"{cost_index:.1f}%")
col3.metric("📊 Sanction (~7.5% extra)", format_rupees(total_cost * 1.075))
col4.metric("🎯 P90 Risk Budget", format_rupees(mc["p90"]))

# =============================================================================
# Tabs
# =============================================================================

tab1, tab2, tab3, tab4, tab5 = st.tabs(
    [
        "📏 SOQ / BOQ",
        "📊 Abstract & Audit",
        "🎯 Risk",
        "📄 CPWD/PWD Formats",
        "📜 Tender Engine",
    ]
)

# =============================================================================
# TAB 1 – SOQ / BOQ – Single Items + Civil & MEP Packages
# =============================================================================

with tab1:
    st.subheader("📏 Schedule of Quantities (IS 1200)")

    mode = st.radio(
        "Input Mode",
        ["Single DSR Item (Manual QTO)", "Civil Work Package", "MEP Work Package"],
        horizontal=True,
    )

    # -------------------------------------------------------------------------
    # 1A. Single DSR Item
    # -------------------------------------------------------------------------
    if mode == "Single DSR Item (Manual QTO)":
        c1, c2 = st.columns([1, 2])
        phase = c1.selectbox("Phase", list(PHASE_GROUPS.keys()))
        available_items = PHASE_GROUPS.get(phase, [])
        if not available_items:
            st.warning("No predefined items for this phase; configure PHASE_GROUPS in dsr_master.py.")
        item_key = c2.selectbox("DSR Item", available_items) if available_items else None

        if item_key and item_key in CPWD_BASE_DSR_2023:
            item: Item = ITEMS[item_key]
            measure_type = item.measure_type
            rule = item.measurement_rule or "volume"

            st.markdown(
                f"**Code:** `{item.code}` &nbsp;&nbsp; **Unit:** `{item.unit}` &nbsp;&nbsp; "
                f"**Category:** `{item.category}` &nbsp;&nbsp; **Rule:** `{rule}`"
            )

            quantity = 0.0
            qto_info = ""
            length = breadth = depth = height = 0.0

            if rule == "trench_excavation":
                c1, c2, c3, c4 = st.columns(4)
                L = c1.number_input("Length L (m)", 0.1, 1000.0, 10.0, 0.1)
                B = c2.number_input("Bottom breadth B (m)", 0.1, 10.0, 1.0, 0.1)
                D = c3.number_input("Depth D (m)", 0.1, 10.0, 1.5, 0.1)
                slope = c4.number_input("Side slope (H:1V)", 0.0, 3.0, 0.0, 0.1)
                res = IS1200Engine.trench_excavation(L, B, D, side_slope_h_over_v=slope)
                quantity = res["net"]
                qto_info = f"L×B×D with slope = {res['gross']:.3f} – {res['deductions']:.3f} = {res['net']:.3f} m³"
                length, breadth, depth = L, B, D

            elif rule == "brickwork_wall":
                c1, c2, c3, c4 = st.columns(4)
                L = c1.number_input("Wall length L (m)", 0.1, 100.0, 5.0, 0.1)
                t = c2.number_input("Thickness t (m)", 0.05, 1.0, 0.23, 0.01)
                H = c3.number_input("Height H (m)", 0.1, 10.0, 3.0, 0.1)
                op_area = c4.number_input("Total large openings area (sqm)", 0.0, 50.0, 0.0, 0.1)
                openings = [{"w": 1.0, "h": op_area, "n": 1}] if op_area > 0 else []
                res = IS1200Engine.brickwork_wall(L, t, H, openings)
                quantity = res["net"]
                qto_info = f"L×t×H = {res['gross']:.3f} – {res['deductions']:.3f} = {res['net']:.3f} m³"
                length, breadth, height = L, t, H

            elif rule == "wall_finish_area":
                c1, c2, c3, c4 = st.columns(4)
                L = c1.number_input("Wall length L (m)", 0.1, 100.0, 5.0, 0.1)
                H = c2.number_input("Wall height H (m)", 0.1, 10.0, 3.0, 0.1)
                sides = int(c3.number_input("Number of sides", 1, 2, 2, 1))
                op_area = c4.number_input("Total large openings area (sqm)", 0.0, 50.0, 0.0, 0.1)
                openings = [{"w": 1.0, "h": op_area, "n": 1}] if op_area > 0 else []
                res = IS1200Engine.wall_finish_area(L, H, sides=sides, openings=openings)
                quantity = res["net"]
                qto_info = f"Gross {res['gross']:.3f} – Deduction {res['deductions']:.3f} = {res['net']:.3f} sqm"
                length, height = L, H

            elif rule == "floor_area":
                c1, c2, c3 = st.columns(3)
                L = c1.number_input("Length L (m)", 0.1, 100.0, 4.0, 0.1)
                B = c2.number_input("Breadth B (m)", 0.1, 100.0, 3.0, 0.1)
                cutouts = c3.number_input("Total cutout area (sqm)", 0.0, 50.0, 0.0, 0.1)
                cut = [{"w": 1.0, "h": cutouts, "n": 1}] if cutouts > 0 else []
                res = IS1200Engine.floor_area(L, B, cut)
                quantity = res["net"]
                qto_info = f"L×B = {res['gross']:.3f} – Cutouts {res['deductions']:.3f} = {res['net']:.3f} sqm"
                length, breadth = L, B

            else:
                # generic handling by measure_type
                if measure_type == "volume":
                    c1, c2, c3, c4 = st.columns(4)
                    L = c1.number_input("Length L (m)", 0.1, 100.0, 2.0, 0.1)
                    B = c2.number_input("Breadth B (m)", 0.1, 100.0, 1.0, 0.1)
                    D = c3.number_input("Depth D (m)", 0.01, 10.0, 0.3, 0.01)
                    ded = c4.number_input("Deductions (m³)", 0.0, 10.0, 0.0, 0.1)
                    res = IS1200Engine.volume(L, B, D, deductions=ded)
                    quantity = res["net"]
                    qto_info = f"L×B×D = {res['gross']:.3f} – {res['deductions']:.3f} = {res['net']:.3f} m³"
                    length, breadth, depth = L, B, D
                elif measure_type == "area":
                    c1, c2 = st.columns(2)
                    L = c1.number_input("Length L (m)", 0.1, 100.0, 4.0, 0.1)
                    B = c2.number_input("Breadth B (m)", 0.1, 100.0, 3.0, 0.1)
                    gross = L * B
                    quantity = gross
                    qto_info = f"L×B = {gross:.3f} sqm"
                    length, breadth = L, B
                elif measure_type == "length":
                    L = st.number_input("Length (m)", 0.1, 1000.0, 10.0, 0.1)
                    quantity = L
                    qto_info = f"Length = {L:.3f} m"
                    length = L
                else:  # weight/each
                    quantity = st.number_input("Quantity", 0.0, 1e6, 1.0, 1.0)
                    qto_info = f"Quantity = {quantity:.3f} {item.unit}"

            rate = item.rate_at_index(cost_index)
            amount = quantity * rate

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("📐 Quantity", f"{quantity:.3f} {item.unit}")
            c2.metric("💰 Rate", f"{rate:,.2f}")
            c3.metric("💵 Amount", format_rupees(amount))
            c4.metric("🔢 DSR Code", item.code)

            if qto_info:
                st.info(f"**IS 1200 Calculation:** {qto_info}")

            if st.button("➕ Add to SOQ", type="primary"):
                line = BOQLine.from_item(
                    line_id=_next_id(),
                    item=item,
                    phase=phase,
                    quantity=quantity,
                    rate=rate,
                    amount=amount,
                    source="single_item",
                    notes=f"Manual QTO using rule: {rule}",
                    length=length,
                    breadth=breadth,
                    depth=depth,
                    height=height,
                    meta={},
                )
                st.session_state.qto_items.append(_boqline_to_dict(line))
                st.success("Item added to SOQ.")
                st.balloons()

    # -------------------------------------------------------------------------
    # 1B. Civil Work Package (protected by password 03656236)
    # -------------------------------------------------------------------------
    elif mode == "Civil Work Package":
        # First, check if civil packages are unlocked
        if not st.session_state.civil_unlocked:
            with st.expander("🔐 Civil Packages Locked – Enter Password to Unlock", expanded=True):
                civil_pw = st.text_input(
                    "Enter Civil Package Password",
                    type="password",
                    key="civil_pkg_pw",
                )
                if st.button("🔓 Unlock Civil Packages", key="unlock_civil_pkg_btn"):
                    if civil_pw == "03656236":
                        st.session_state.civil_unlocked = True
                        st.success("✅ Civil packages unlocked for this session.")
                    else:
                        st.error("❌ Invalid password. Please enter correct key.")
            # Stop here if not unlocked yet
            if not st.session_state.civil_unlocked:
                st.stop()

        # Once unlocked, proceed as normal
        pkg_name = st.selectbox("Select Civil Package", list(WORK_PACKAGES_CIVIL.keys()))
        pkg = WORK_PACKAGES_CIVIL[pkg_name]

        st.markdown(f"**Package:** {pkg.name}")
        st.caption(pkg.description)

        ctx: Dict[str, Any] = {}

        if "Site clearance" in pkg_name:
            ctx["site_area_sqm"] = st.number_input(
                "Site clearance area (sqm)", 10.0, 1e6, 500.0, 10.0
            )

        elif "Bulk earthworks" in pkg_name:
            c1, c2 = st.columns(2)
            ctx["cut_volume_cum"] = c1.number_input("Cut volume (cum)", 0.0, 1e6, 100.0, 1.0)
            ctx["fill_volume_cum"] = c2.number_input("Fill volume (cum)", 0.0, 1e6, 80.0, 1.0)

        elif "Isolated footing" in pkg_name:
            c1, c2, c3 = st.columns(3)
            ctx["L_foot"] = c1.number_input("Footing L (m)", 0.1, 10.0, 2.0, 0.1)
            ctx["B_foot"] = c2.number_input("Footing B (m)", 0.1, 10.0, 2.0, 0.1)
            ctx["D_foot"] = c3.number_input("Footing D (m)", 0.1, 2.0, 0.5, 0.05)

            c4, c5, c6 = st.columns(3)
            ctx["L_blind"] = c4.number_input("Blinding L (m)", 0.1, 10.0, ctx["L_foot"] + 0.2, 0.1)
            ctx["B_blind"] = c5.number_input("Blinding B (m)", 0.1, 10.0, ctx["B_foot"] + 0.2, 0.1)
            ctx["t_blind"] = c6.number_input("Blinding t (m)", 0.03, 0.20, 0.05, 0.01)

            c7, c8, c9 = st.columns(3)
            ctx["L_exc"] = c7.number_input("Excavation L (m)", 0.1, 10.0, ctx["L_blind"] + 0.3, 0.1)
            ctx["B_exc"] = c8.number_input("Excavation B (m)", 0.1, 10.0, ctx["B_blind"] + 0.3, 0.1)
            ctx["D_exc"] = c9.number_input("Excavation D (m)", 0.1, 3.0, ctx["D_foot"] + 0.2, 0.05)

            ctx["backfill_volume_cum"] = st.number_input(
                "Backfill volume (cum)", 0.0, 1e6, 0.0, 0.1
            )

        elif "RCC columns" in pkg_name:
            c1, c2, c3 = st.columns(3)
            ctx["n_cols"] = c1.number_input("Number of columns", 1, 1000, 4, 1)
            ctx["b_col"] = c2.number_input("Column width b (m)", 0.1, 1.0, 0.23, 0.01)
            ctx["d_col"] = c3.number_input("Column depth d (m)", 0.1, 1.0, 0.23, 0.01)

            c4, c5 = st.columns(2)
            ctx["h_col"] = c4.number_input("Column height (floor-to-floor) (m)", 1.0, 6.0, 3.0, 0.1)
            ctx["steel_kg_per_cum_col"] = c5.number_input(
                "Steel kg/m³ (columns)", 40.0, 300.0, 160.0, 5.0
            )

        elif "RCC beams" in pkg_name:
            c1, c2, c3 = st.columns(3)
            ctx["n_beams"] = c1.number_input("Number of beams", 1, 1000, 6, 1)
            ctx["L_beam"] = c2.number_input("Beam span L (m)", 0.5, 20.0, 4.0, 0.1)
            ctx["b_beam"] = c3.number_input("Beam width b (m)", 0.1, 1.0, 0.23, 0.01)

            c4, c5 = st.columns(2)
            ctx["d_beam"] = c4.number_input("Beam depth D (m)", 0.1, 2.0, 0.45, 0.01)
            ctx["steel_kg_per_cum_beam"] = c5.number_input(
                "Steel kg/m³ (beams)", 40.0, 300.0, 120.0, 5.0
            )

        elif "RCC slab" in pkg_name:
            c1, c2, c3 = st.columns(3)
            ctx["n_slabs"] = c1.number_input("Number of identical slabs/bays", 1, 100, 1, 1)
            ctx["L_slab"] = c2.number_input("Slab span L (m)", 1.0, 20.0, 4.0, 0.1)
            ctx["B_slab"] = c3.number_input("Slab breadth B (m)", 1.0, 20.0, 3.0, 0.1)

            c4, c5 = st.columns(2)
            ctx["t_slab"] = c4.number_input("Slab thickness t (m)", 0.08, 0.25, 0.15, 0.01)
            ctx["steel_kg_per_cum_slab"] = c5.number_input(
                "Steel kg/m³ (slabs)", 40.0, 300.0, 100.0, 5.0
            )

        elif "Brick wall with plaster" in pkg_name:
            c1, c2, c3 = st.columns(3)
            ctx["L_wall"] = c1.number_input("Wall length L (m)", 0.1, 100.0, 5.0, 0.1)
            ctx["H_wall"] = c2.number_input("Wall height H (m)", 0.1, 10.0, 3.0, 0.1)
            ctx["t_wall"] = c3.number_input("Thickness t (m)", 0.05, 1.0, 0.23, 0.01)

        elif "Vitrified floor tiles" in pkg_name:
            c1, c2, c3 = st.columns(3)
            ctx["L_room"] = c1.number_input("Room length L (m)", 0.1, 100.0, 4.0, 0.1)
            ctx["B_room"] = c2.number_input("Room breadth B (m)", 0.1, 100.0, 3.0, 0.1)
            ctx["wastage_factor"] = c3.number_input(
                "Wastage factor", 1.00, 1.20, 1.03, 0.01
            )

        elif "Internal wall painting" in pkg_name:
            c1, c2, c3 = st.columns(3)
            ctx["L_wall"] = c1.number_input("Wall length L (m)", 0.1, 100.0, 5.0, 0.1)
            ctx["H_wall"] = c2.number_input("Wall height H (m)", 0.1, 10.0, 3.0, 0.1)
            ctx["sides"] = int(c3.number_input("Number of sides", 1, 2, 2, 1))

        if st.button("➕ Add Civil Package", type="primary"):
            lines = expand_work_package(pkg_name, ctx, phase=None, cost_index=cost_index)
            for line in lines:
                line.id = _next_id()
                st.session_state.qto_items.append(_boqline_to_dict(line))
            st.success(f"Package '{pkg_name}' expanded into {len(lines)} BOQ lines.")
            st.balloons()

    # -------------------------------------------------------------------------
    # 1C. MEP Work Package
    # -------------------------------------------------------------------------
    else:  # MEP Work Package
        pkg_name = st.selectbox("Select MEP Package", list(WORK_PACKAGES_MEP.keys()))
        pkg = WORK_PACKAGES_MEP[pkg_name]

        st.markdown(f"**Package:** {pkg.name}")
        st.caption(pkg.description)

        ctx: Dict[str, Any] = {}

        if "lighting wiring" in pkg_name.lower():
            c1, c2 = st.columns(2)
            ctx["lighting_points"] = c1.number_input("Lighting points", 1, 200, 8, 1)
            ctx["avg_run_ltg"] = c2.number_input(
                "Avg horizontal run per point (m)", 1.0, 50.0, 8.0, 0.5
            )
            c3, c4 = st.columns(2)
            ctx["vertical_drop"] = c3.number_input(
                "Vertical drop (m)", 1.0, 6.0, 3.0, 0.1
            )
            ctx["lighting_points_per_circuit"] = int(
                c4.number_input("Points per circuit", 2, 15, 8, 1)
            )
            ctx["points_per_switchboard"] = int(
                st.number_input("Points per 6M switchboard", 1, 20, 4, 1)
            )

        elif "toilet block plumbing" in pkg_name.lower():
            c1, c2, c3 = st.columns(3)
            ctx["toilet_blocks"] = c1.number_input("No. of toilet blocks", 1, 50, 2, 1)
            ctx["wc_per_block"] = c2.number_input("WCs per block", 1, 20, 2, 1)
            ctx["basins_per_block"] = c3.number_input("Basins per block", 1, 20, 2, 1)
            c4, c5, c6 = st.columns(3)
            ctx["urinals_per_block"] = c4.number_input("Urinals per block", 0, 20, 1, 1)
            ctx["floor_traps_per_block"] = c5.number_input(
                "Floor traps per block", 0, 20, 2, 1
            )
            ctx["nahani_traps_per_block"] = c6.number_input(
                "Nahani traps per block", 0, 20, 0, 1
            )

        elif "ahu zone ducting" in pkg_name.lower():
            c1, c2, c3 = st.columns(3)
            ctx["supply_cmh"] = c1.number_input(
                "Supply airflow (CMH)", 100.0, 200000.0, 8000.0, 100.0
            )
            ctx["main_duct_length_m"] = c2.number_input(
                "Main duct length (m)", 5.0, 500.0, 20.0, 1.0
            )
            ctx["branch_duct_length_m"] = c3.number_input(
                "Branch duct length (m)", 5.0, 1000.0, 40.0, 1.0
            )

        elif "fire alarm devices" in pkg_name.lower():
            c1, c2, c3, c4 = st.columns(4)
            ctx["smoke_detectors"] = c1.number_input("Smoke detectors", 0, 500, 20, 1)
            ctx["heat_detectors"] = c2.number_input("Heat detectors", 0, 500, 5, 1)
            ctx["mcps"] = c3.number_input("Manual call points", 0, 200, 4, 1)
            ctx["hooters"] = c4.number_input("Hooters/sounders", 0, 200, 4, 1)

        if st.button("➕ Add MEP Package", type="primary"):
            lines = expand_mep_package(pkg_name, ctx, phase=None, cost_index=cost_index)
            for line in lines:
                line.id = _next_id()
                st.session_state.qto_items.append(_boqline_to_dict(line))
            st.success(f"MEP package '{pkg_name}' expanded into {len(lines)} BOQ lines.")
            st.balloons()

    # -------------------------------------------------------------------------
    # Show current BOQ
    # -------------------------------------------------------------------------
    if st.session_state.qto_items:
        st.markdown("### Current SOQ / BOQ")
        df_boq = pd.DataFrame(st.session_state.qto_items)
        show_cols = [
            "id",
            "phase",
            "code",
            "description",
            "quantity",
            "unit",
            "rate",
            "amount",
            "category",
            "discipline",
            "source",
        ]
        show_cols = [c for c in show_cols if c in df_boq.columns]
        st.dataframe(df_boq[show_cols].round(3), use_container_width=True)

        col_btn1, col_btn2 = st.columns(2)
        if col_btn1.button("🧹 Clear SOQ", type="secondary"):
            st.session_state.qto_items = []
            st.rerun()
        if col_btn2.button("💾 Download BOQ (CSV)"):
            csv = df_boq.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="Save BOQ CSV",
                data=csv,
                file_name=f"BOQ_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
            )

# =============================================================================
# TAB 2 – Abstract & Audit
# =============================================================================

with tab2:
    st.subheader("📊 Abstract of Cost & Technical/Audit Checks")

    if not st.session_state.qto_items:
        st.info("Add items in SOQ / BOQ tab to see abstract and audit checks.")
    else:
        df = pd.DataFrame(st.session_state.qto_items)
        phase_totals = df.groupby("phase")["amount"].sum().reset_index()
        phase_totals["Amount (₹)"] = phase_totals["amount"].apply(format_rupees)
        st.markdown("### Phase-wise Abstract")
        st.dataframe(
            phase_totals[["phase", "Amount (₹)"]].rename(columns={"phase": "Phase"}),
            use_container_width=True,
        )

        st.markdown("**Grand Total:** " + format_rupees(total_cost))

        st.markdown("### 🛡️ Technical & Audit Rules (Civil + MEP)")
        results = run_all_rules(st.session_state.qto_items)
        if not results:
            st.success("No issues detected by the configured rules.")
        else:
            grouped = group_results_by_level(results)
            if "ERROR" in grouped:
                st.error(f"Errors: {len(grouped['ERROR'])}")
                for r in grouped["ERROR"]:
                    st.write(f"❌ [{r.discipline}] {r.code or ''} {r.message}")
            if "WARNING" in grouped:
                st.warning(f"Warnings: {len(grouped['WARNING'])}")
                for r in grouped["WARNING"]:
                    st.write(f"⚠️ [{r.discipline}] {r.code or ''} {r.message}")
            if "INFO" in grouped:
                st.info(f"Infos: {len(grouped['INFO'])}")
                for r in grouped["INFO"]:
                    st.write(f"ℹ️ [{r.discipline}] {r.code or ''} {r.message}")

# =============================================================================
# TAB 3 – Risk Analysis
# =============================================================================

with tab3:
    st.subheader("🎯 Risk Analysis (Monte Carlo)")

    if total_cost <= 0:
        st.info("Add items in SOQ / BOQ tab to run risk analysis.")
    else:
        st.markdown("Base Cost (from BOQ): " + format_rupees(total_cost))

        col1, col2 = st.columns(2)
        sims = int(col1.number_input("Number of simulations", 200, 5000, 1000, 100))
        seed = int(col2.number_input("Random seed", 1, 9999, 42, 1))

        mc_res = monte_carlo_amount(total_cost, n=sims, seed=seed)
        c1, c2, c3 = st.columns(3)
        c1.metric("P10 (Optimistic)", format_rupees(mc_res["p10"]))
        c2.metric("P50 (Median)", format_rupees(mc_res["p50"]))
        c3.metric("P90 (Conservative Budget)", format_rupees(mc_res["p90"]))

        st.write(
            f"Recommended **budget** at P90: **{format_rupees(mc_res['p90'])}** "
            f"(~{mc_res['p90']/total_cost*100:.1f}% of base)."
        )

# =============================================================================
# TAB 4 – CPWD / PWD Formats
# =============================================================================

with tab4:
    st.subheader("📄 CPWD / PWD Formats")

    if not st.session_state.qto_items:
        st.info("Complete SOQ / BOQ first to generate formats.")
    else:
        format_type = st.selectbox(
            "Select Format",
            [
                "1️⃣ Form 5A – Abstract of Cost",
                "2️⃣ Form 7 – Schedule of Quantities (SOQ)",
                "3️⃣ Form 8 – Measurement Book",
                "4️⃣ Form 31 – Running Account Bill",
                "5️⃣ PWD Form 6 – Work Order",
            ],
        )

        df = pd.DataFrame(st.session_state.qto_items)
        today = datetime.now()

        # 1) FORM 5A – ABSTRACT OF COST
        if "Form 5A" in format_type:
            st.markdown("### 📋 CPWD Form 5A – Abstract of Cost")

            phase_totals = df.groupby("phase")["amount"].sum().reset_index()
            phase_totals["No.Items"] = df.groupby("phase")["id"].count().values
            phase_totals["Amount (₹)"] = phase_totals["amount"].apply(format_rupees)
            phase_totals.rename(
                columns={"phase": "Description"}, inplace=True
            )

            total_row = pd.DataFrame(
                [
                    {
                        "Description": "CIVIL & MEP WORKS",
                        "No.Items": len(df),
                        "Amount (₹)": format_rupees(total_cost),
                    }
                ]
            )

            form5a = pd.concat(
                [phase_totals[["Description", "No.Items", "Amount (₹)"]], total_row],
                ignore_index=True,
            )
            form5a.insert(0, "S.No.", range(1, len(form5a) + 1))

            st.dataframe(form5a, use_container_width=True)

            st.download_button(
                "📥 Download Form 5A (CSV)",
                form5a.to_csv(index=False).encode("utf-8"),
                file_name=f"CPWD_Form5A_{today.strftime('%Y%m%d')}.csv",
                mime="text/csv",
            )

        # 2) FORM 7 – SCHEDULE OF QUANTITIES
        elif "Form 7" in format_type:
            st.markdown("### 📋 CPWD Form 7 – Schedule of Quantities")

            soq = df.copy()
            soq["Rate (₹)"] = soq["rate"].map(lambda r: f"{r:,.2f}")
            soq["Amount (₹)"] = soq["amount"].map(format_rupees)

            out = soq[["id", "code", "description", "quantity", "unit", "Rate (₹)", "Amount (₹)"]].rename(
                columns={
                    "id": "Item No",
                    "code": "DSR Code",
                    "description": "Description",
                    "quantity": "Quantity",
                    "unit": "Unit",
                }
            )

            total_row = pd.DataFrame(
                [
                    {
                        "Item No": "TOTAL",
                        "DSR Code": "",
                        "Description": "GRAND TOTAL",
                        "Quantity": "",
                        "Unit": "",
                        "Rate (₹)": "",
                        "Amount (₹)": format_rupees(total_cost),
                    }
                ]
            )
            out = pd.concat([out, total_row], ignore_index=True)

            st.dataframe(out, use_container_width=True)

            st.download_button(
                "📥 Download Form 7 (CSV)",
                out.to_csv(index=False).encode("utf-8"),
                file_name=f"CPWD_Form7_SOQ_{today.strftime('%Y%m%d')}.csv",
                mime="text/csv",
            )

        # 3) FORM 8 – MEASUREMENT BOOK
        elif "Form 8" in format_type:
            st.markdown("### 📏 CPWD Form 8 – Measurement Book")

            mb_rows = []
            for _, row in df.iterrows():
                mb_rows.append(
                    {
                        "Date": today.strftime("%d/%m/%Y"),
                        "MB Page": f"MB/{int(row['id']):03d}",
                        "Item Description": str(row.get("description", ""))[:60],
                        "Length (m)": f"{float(row.get('length', 0.0)):.2f}",
                        "Breadth (m)": f"{float(row.get('breadth', 0.0)):.2f}",
                        "Depth/Height (m)": f"{float(row.get('depth', 0.0) or row.get('height', 0.0)):.3f}",
                        "Content": f"{float(row.get('quantity', 0.0)):.3f} {row.get('unit', '')}",
                        "Initials": "Checked & Verified",
                    }
                )

            df8 = pd.DataFrame(mb_rows)
            st.dataframe(df8, use_container_width=True)

            st.download_button(
                "📥 Download Form 8 (CSV)",
                df8.to_csv(index=False).encode("utf-8"),
                file_name=f"CPWD_Form8_MB_{today.strftime('%Y%m%d')}.csv",
                mime="text/csv",
            )

        # 4) FORM 31 – RUNNING ACCOUNT BILL
        elif "Form 31" in format_type:
            st.markdown("### 💰 CPWD Form 31 – Running Account Bill (Simple)")

            gross = total_cost
            prev = 0.0  # first bill
            total_work = gross + prev
            it_ded = gross * 0.02
            cess_ded = gross * 0.01
            net = gross - it_ded - cess_ded

            ra_data = {
                "S.No.": [1, 2, 3, 4, 5, 6, 7],
                "Particulars": [
                    "Gross value of work measured (this bill)",
                    "Work done - previous bills",
                    "Total value of work done (1+2)",
                    "Deductions:",
                    "Income Tax @2%",
                    "Labour Cess @1%",
                    "NET AMOUNT PAYABLE",
                ],
                "Amount (₹)": [
                    format_rupees(gross),
                    format_rupees(prev),
                    format_rupees(total_work),
                    "",
                    format_rupees(it_ded),
                    format_rupees(cess_ded),
                    format_rupees(net),
                ],
            }

            df31 = pd.DataFrame(ra_data)
            st.dataframe(df31, use_container_width=True)

            st.download_button(
                "📥 Download Form 31 (CSV)",
                df31.to_csv(index=False).encode("utf-8"),
                file_name=f"CPWD_Form31_RA_{today.strftime('%Y%m%d')}.csv",
                mime="text/csv",
            )

            c1, c2 = st.columns(2)
            c1.metric("Gross Value", format_rupees(gross))
            c2.metric("Net Payable", format_rupees(net))

        # 5) PWD Form 6 – Work Order
        else:
            st.markdown("### 📜 PWD Form 6 – Work Order (Summary)")

            completion_date = today + timedelta(days=180)
            name = st.session_state.project_info["name"]
            client = st.session_state.project_info["client"]

            wo_data = {
                "S.No.": list(range(1, 10)),
                "Particulars": [
                    "Name of Work",
                    "Location",
                    "Probable Amount of Contract",
                    "Earnest Money Deposit (2%)",
                    "Security Deposit (5%)",
                    "Time Allowed",
                    "Date of Commencement",
                    "Scheduled Completion Date",
                    "Performance Guarantee (3%)",
                ],
                "Details": [
                    name,
                    st.session_state.project_info["location"],
                    format_rupees(total_cost),
                    format_rupees(total_cost * 0.02),
                    format_rupees(total_cost * 0.05),
                    "6 (Six) Months",
                    today.strftime("%d/%m/%Y"),
                    completion_date.strftime("%d/%m/%Y"),
                    format_rupees(total_cost * 0.03),
                ],
            }
        st.dataframe(wo_data if isinstance(wo_data, pd.DataFrame) else pd.DataFrame(wo_data), use_container_width=True)

        st.download_button(
            "📥 Download PWD Form 6 (CSV)",
            pd.DataFrame(wo_data).to_csv(index=False).encode("utf-8"),
            file_name=f"PWD_Form6_WorkOrder_{today.strftime('%Y%m%d')}.csv",
            mime="text/csv",
        )

        st.markdown(
            f"""
**WORK ORDER No:** WO/{location[:3].upper()}/{today.strftime('%Y')}/{today.strftime('%m%d')}/001  

**To:** M/s [CONTRACTOR NAME]  

**Subject:** Award of Contract – {name} for {client}
"""
        )

# =============================================================================
# TAB 5 – Tender Engine (AA/ES → TS → NIT → Bids → LOA → PG → Work Order)
# =============================================================================

with tab5:
    st.header("📜 End-to-End Tender Engine (CPWD / PWD Aligned)")
    st.caption("AA/ES → TS → NIT → Bidders → Two-Bid Evaluation → L1 → LOA → PG → Work Order")

    step = st.radio(
        "Tender Stage",
        [
            "1️⃣ AA & ES",
            "2️⃣ Estimate & TS",
            "3️⃣ NIT & Documents",
            "4️⃣ Bidders & Eligibility",
            "5️⃣ Bid Evaluation (Tech + Fin)",
            "6️⃣ LOA, PG & Work Order",
        ],
        horizontal=False,
    )

    aa_ok = st.session_state.aa is not None
    es_ok = st.session_state.es is not None

    # -------------------------
    # Stage 1 – AA & ES
    # -------------------------
    if step == "1️⃣ AA & ES":
        st.subheader("Administrative Approval (AA)")

        c1, c2, c3 = st.columns(3)
        aa_number = c1.text_input(
            "AA Number", value=st.session_state.aa.aa_number if st.session_state.aa else ""
        )
        aa_date = c2.date_input("AA Date", value=datetime.today())
        aa_auth = c3.text_input(
            "AA Authority (e.g. SE/CE)", value=st.session_state.aa.authority if st.session_state.aa else ""
        )
        aa_amt = st.number_input(
            "AA Amount Sanctioned (₹)",
            min_value=0.0,
            value=float(total_cost or 0.0),
            step=10000.0,
        )

        if st.button("💾 Save AA"):
            st.session_state.aa = AdministrativeApproval(
                aa_number=aa_number,
                aa_date=datetime.combine(aa_date, datetime.min.time()),
                authority=aa_auth,
                amount_sanctioned=aa_amt,
            )
            st.success("Administrative Approval saved.")

        st.markdown("---")
        st.subheader("Expenditure Sanction (ES)")

        d1, d2, d3 = st.columns(3)
        es_number = d1.text_input(
            "ES Number", value=st.session_state.es.es_number if st.session_state.es else ""
        )
        es_date = d2.date_input("ES Date", value=datetime.today())
        es_auth = d3.text_input(
            "ES Authority", value=st.session_state.es.authority if st.session_state.es else ""
        )
        head = st.text_input(
            "Head of Account", value=st.session_state.es.head_of_account if st.session_state.es else ""
        )
        es_amt = st.number_input(
            "ES Amount Sanctioned (₹)",
            min_value=0.0,
            value=float(total_cost or 0.0),
            step=10000.0,
        )

        if st.button("💾 Save ES"):
            st.session_state.es = ExpenditureSanction(
                es_number=es_number,
                es_date=datetime.combine(es_date, datetime.min.time()),
                authority=es_auth,
                amount_sanctioned=es_amt,
                head_of_account=head,
            )
            st.success("Expenditure Sanction saved.")

    # -------------------------
    # Stage 2 – Estimate & TS
    # -------------------------
    elif step == "2️⃣ Estimate & TS":
        if not aa_ok or not es_ok:
            st.warning("Please complete AA & ES first (Stage 1).")
            st.stop()
        if total_cost <= 0:
            st.warning("Please prepare Detailed Estimate (BOQ) in 'SOQ / BOQ' tab first.")
            st.stop()

        st.subheader("Technical Sanction (TS) – based on current Detailed Estimate")
        st.info(f"Current Estimate Amount (from BOQ): {format_rupees(total_cost)}")

        t1, t2, t3 = st.columns(3)
        ts_number = t1.text_input(
            "TS Number", value=st.session_state.ts.ts_number if st.session_state.ts else ""
        )
        ts_date = t2.date_input("TS Date", value=datetime.today())
        ts_auth = t3.text_input(
            "TS Authority (EE/SE)", value=st.session_state.ts.authority if st.session_state.ts else ""
        )
        ts_amt = st.number_input(
            "TS Amount Approved (₹)",
            min_value=0.0,
            value=float(total_cost or 0.0),
            step=10000.0,
        )

        if st.button("✅ Approve TS"):
            st.session_state.ts = TechnicalSanction(
                ts_number=ts_number,
                ts_date=datetime.combine(ts_date, datetime.min.time()),
                authority=ts_auth,
                amount_approved=ts_amt,
            )
            st.success("Technical Sanction recorded.")

    # -------------------------
    # Stage 3 – NIT & Documents
    # -------------------------
    elif step == "3️⃣ NIT & Documents":
        if not (aa_ok and es_ok and st.session_state.ts):
            st.warning("Please complete AA, ES and TS first (Stages 1 & 2).")
            st.stop()

        st.subheader("Notice Inviting Tender (NIT)")

        name_of_work = st.text_input("Name of Work", st.session_state.project_info["name"])
        est_cost = total_cost
        t1, t2, t3 = st.columns(3)
        nit_number = t1.text_input(
            "NIT Number", value=st.session_state.nit.nit_number if st.session_state.nit else ""
        )
        nit_date = t2.date_input("NIT Date", value=datetime.today())
        completion_time_days = t3.number_input("Completion Time (days)", 1, 3650, 180, 1)

        emd_pct = st.number_input("EMD (%)", 0.5, 5.0, 2.0, 0.5)
        emd_amt = est_cost * emd_pct / 100.0

        tender_type = st.selectbox("Tender Type", ["Open", "Limited", "Item Rate", "Percentage Rate"])
        eligibility = st.text_area(
            "Eligibility Criteria",
            "Registered contractor in appropriate class (CPWD/PWD/Local Body), experience of similar works, valid PAN, GST, etc.",
        )
        doc_fee = st.number_input("Tender Document Fee (₹)", 0.0, 100000.0, 0.0, 500.0)

        st.info(f"Estimated Cost: {format_rupees(est_cost)} | EMD @ {emd_pct:.1f}% = {format_rupees(emd_amt)}")

        if st.button("💾 Save NIT"):
            st.session_state.nit = NIT(
                nit_number=nit_number,
                nit_date=datetime.combine(nit_date, datetime.min.time()),
                name_of_work=name_of_work,
                estimated_cost=est_cost,
                emd_amount=emd_amt,
                completion_time_days=completion_time_days,
                tender_type=tender_type,
                eligibility_criteria=eligibility,
                document_fee=doc_fee,
            )
            st.success("NIT details saved.")

        if st.session_state.nit:
            st.markdown("#### NIT Preview (for CPPP / Notice Board)")
            nit = st.session_state.nit
            st.text(
                f"""
CPWD / {st.session_state.project_info['location']} Division

NOTICE INVITING TENDER (NIT No. {nit.nit_number} dated {nit.nit_date.strftime('%d-%m-%Y')})

Name of Work     : {nit.name_of_work}
Estimated Cost   : {format_rupees(nit.estimated_cost)}
EMD              : {format_rupees(nit.emd_amount)}
Completion Time  : {nit.completion_time_days} days
Tender Type      : {nit.tender_type}

Eligibility : {nit.eligibility_criteria}
"""
            )

    # -------------------------
    # Stage 4 – Bidders & Eligibility
    # -------------------------
    elif step == "4️⃣ Bidders & Eligibility":
        if not st.session_state.nit:
            st.warning("Please create and save NIT first (Stage 3).")
            st.stop()

        st.subheader("Bidder Registration & Eligibility (Technical Bid)")

        with st.form("add_bidder"):
            name = st.text_input("Bidder / Contractor Name")
            reg_class = st.text_input("Registration Class (e.g., Class II)")
            reg_dept = st.text_input("Registration Department (CPWD/PWD/Nagar Nigam etc.)")
            pan = st.text_input("PAN")
            gst = st.text_input("GST No.")
            solv = st.number_input("Solvency Amount (₹)", 0.0, 1e9, 0.0, 100000.0)
            exp_value = st.number_input("Value of similar works executed (₹)", 0.0, 1e9, 0.0, 100000.0)
            emd_paid = st.number_input("EMD Paid (₹)", 0.0, 1e9, 0.0, 1000.0)
            affid = st.checkbox("All required affidavits submitted", value=True)
            docs_ok = st.checkbox("All required documents submitted", value=True)
            submitted = st.form_submit_button("➕ Add / Update Bidder")

        if submitted and name:
            bidder = Bidder(
                name=name,
                registration_class=reg_class,
                registration_dept=reg_dept,
                pan=pan,
                gst=gst,
                solvency_amount=solv,
                experience_value=exp_value,
                emd_paid=emd_paid,
                affidavits_ok=affid,
                other_docs_ok=docs_ok,
            )
            st.session_state.bidders = [b for b in st.session_state.bidders if b["name"] != name]
            st.session_state.bidders.append(bidder.to_dict())
            st.success("Bidder saved/updated.")

        if st.session_state.bidders:
            st.markdown("#### Registered Bidders")
            st.dataframe(pd.DataFrame(st.session_state.bidders), use_container_width=True)

    # -------------------------
    # Stage 5 – Two-Bid Evaluation (Tech + Fin)
    # -------------------------
    elif step == "5️⃣ Bid Evaluation (Tech + Fin)":
        if not st.session_state.bidders:
            st.warning("No bidders registered in Stage 4.")
            st.stop()

        nit = st.session_state.nit
        est_cost = nit.estimated_cost if nit else total_cost
        emd_req = nit.emd_amount if nit else 0.0

        st.subheader("Technical Evaluation")

        tech_results = []
        for b in st.session_state.bidders:
            ok = True
            reasons = []
            if not b.get("affidavits_ok"):
                ok = False
                reasons.append("Affidavits missing")
            if not b.get("other_docs_ok"):
                ok = False
                reasons.append("Supporting documents missing")
            if b.get("solvency_amount", 0.0) < 0.4 * est_cost:
                ok = False
                reasons.append("Solvency < 40% of estimated cost")
            if b.get("experience_value", 0.0) < 0.8 * est_cost:
                ok = False
                reasons.append("Experience < 80% of estimated cost")
            if b.get("emd_paid", 0.0) < emd_req:
                ok = False
                reasons.append("EMD short / not paid")

            tech_results.append(
                {
                    "name": b["name"],
                    "technical_qualified": ok,
                    "remarks": "; ".join(reasons) if reasons else "Qualified",
                }
            )

        df_tech = pd.DataFrame(tech_results)
        st.dataframe(df_tech, use_container_width=True)

        st.markdown("---")
        st.subheader("Financial Bids (for Technically Qualified Bidders)")

        qualified = [r for r in tech_results if r["technical_qualified"]]
        if not qualified:
            st.error("No technically qualified bidders.")
            st.stop()

        for q in qualified:
            name = q["name"]
            quoted = st.number_input(
                f"Quoted amount by {name} (₹)",
                min_value=0.0,
                step=10000.0,
                key=f"fin_{name}",
            )
            if quoted > 0:
                st.session_state.bids = [
                    bd for bd in st.session_state.bids if bd["bidder_name"] != name
                ]
                st.session_state.bids.append(
                    Bid(
                        bidder_name=name,
                        technical_qualified=True,
                        quoted_amount=quoted,
                    ).to_dict()
                )

        if st.session_state.bids:
            df_bids = pd.DataFrame(st.session_state.bids)
            st.markdown("#### Financial Bids")
            st.dataframe(df_bids, use_container_width=True)

            l1 = min(
                (b for b in st.session_state.bids if b["technical_qualified"]),
                key=lambda x: x["quoted_amount"],
                default=None,
            )
            if l1:
                st.success(
                    f"L1 Bidder: **{l1['bidder_name']}** with quote {format_rupees(l1['quoted_amount'])}"
                )

    # -------------------------
    # Stage 6 – LOA, PG & Work Order
    # -------------------------
    elif step == "6️⃣ LOA, PG & Work Order":
        if not st.session_state.bids:
            st.warning("No evaluated bids from Stage 5.")
            st.stop()
        # Find L1
        l1 = min(
            (b for b in st.session_state.bids if b["technical_qualified"]),
            key=lambda x: x["quoted_amount"],
            default=None,
        )
        if not l1:
            st.error("No L1 bidder found.")
            st.stop()

        st.subheader("Letter of Acceptance (LOA)")

        c1, c2 = st.columns(2)
        loa_number = c1.text_input(
            "LOA Number", value=st.session_state.loa.loa_number if st.session_state.loa else ""
        )
        loa_date = c2.date_input("LOA Date", value=datetime.today())
        comp_days = st.number_input("Completion Time (days)", 1, 3650, 180, 1)

        if st.button("💾 Generate LOA"):
            st.session_state.loa = LetterOfAcceptance(
                loa_number=loa_number,
                loa_date=datetime.combine(loa_date, datetime.min.time()),
                bidder_name=l1["bidder_name"],
                accepted_amount=l1["quoted_amount"],
                completion_time_days=comp_days,
            )
            st.success("LOA details saved.")

        if st.session_state.loa:
            st.markdown("#### LOA Preview")
            loa = st.session_state.loa
            st.text(
                f"""
LETTER OF ACCEPTANCE (LOA No. {loa.loa_number} dated {loa.loa_date.strftime('%d-%m-%Y')})

Name of Work        : {st.session_state.project_info['name']}
Accepted Contractor : {loa.bidder_name}
Accepted Amount     : {format_rupees(loa.accepted_amount)}
Time of Completion  : {loa.completion_time_days} days
"""
            )

        st.markdown("---")
        st.subheader("Performance Guarantee (PG)")

        pg_pct = st.number_input("PG % (3–5%)", 3.0, 10.0, 3.0, 0.5)
        est_pg_amt = (l1["quoted_amount"] * pg_pct) / 100.0
        st.info(f"Required PG Amount @ {pg_pct:.1f}%: {format_rupees(est_pg_amt)}")

        pg_received = st.checkbox("Performance Guarantee received?", value=False)
        pg_instr = st.text_input("Instrument Details (BG/DD/FD, No., Date, Bank)")

        if st.button("💾 Save PG Status"):
            st.session_state.pg = PerformanceGuarantee(
                pct_required=pg_pct,
                amount_required=est_pg_amt,
                received=pg_received,
                instrument_details=pg_instr,
            )
            st.success("Performance Guarantee status saved.")

        st.markdown("---")
        st.subheader("Work Order / Agreement")

        if not st.session_state.loa or not st.session_state.pg or not st.session_state.pg.received:
            st.warning("Ensure LOA issued and PG received before final Work Order.")
        else:
            wo = st.session_state.work_order
            existing_comp_days = (
                st.session_state.loa.completion_time_days if st.session_state.loa else 180
            )
            start_date = st.date_input(
                "Date of Start",
                value=wo.date_of_start.date() if wo else datetime.today().date(),
            )
            completion_date = st.date_input(
                "Date of Completion",
                value=wo.date_of_completion.date()
                if wo
                else (datetime.today() + timedelta(days=existing_comp_days)).date(),
            )
            time_allowed_str = st.text_input(
                "Time Allowed (text)",
                wo.time_allowed if wo else f"{existing_comp_days//30} (months approx.)",
            )

            if st.button("✅ Finalize Work Order"):
                wo_number = (
                    st.session_state.work_order.wo_number
                    if st.session_state.work_order
                    else f"WO/{location[:3].upper()}/{datetime.now().strftime('%Y%m')}/001"
                )
                st.session_state.work_order = WorkOrder(
                    wo_number=wo_number,
                    wo_date=datetime.now(),
                    name_of_work=st.session_state.project_info["name"],
                    contractor_name=l1["bidder_name"],
                    contract_amount=l1["quoted_amount"],
                    date_of_start=datetime.combine(start_date, datetime.min.time()),
                    date_of_completion=datetime.combine(completion_date, datetime.min.time()),
                    time_allowed=time_allowed_str,
                )
                st.success(f"Work Order {wo_number} created.")

            if st.session_state.work_order:
                wo = st.session_state.work_order
                st.markdown("#### Work Order Summary")
                st.markdown(
                    f"""
**WORK ORDER No:** {wo.wo_number}  
**Name of Work:** {wo.name_of_work}  
**Contractor:** {wo.contractor_name}  
**Contract Amount:** {format_rupees(wo.contract_amount)}  
**Date of Start:** {wo.date_of_start.strftime('%d-%m-%Y')}  
**Date of Completion:** {wo.date_of_completion.strftime('%d-%m-%Y')}  
**Time Allowed:** {wo.time_allowed}
"""
                )

st.success(
    "✅ Estimator + Tender Engine ready – Civil & RCC packages (concrete+steel+formwork), MEP packages, IS-1200 measurement, multi-discipline rule checks, and CPWD/PWD tender flow (AA/ES → TS → NIT → L1 → LOA → PG → WO) are active.\n\nCivil Work Packages are password-protected with key 03656236."
)
