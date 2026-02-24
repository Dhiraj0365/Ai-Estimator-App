from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import List, Dict, Any

import numpy as np
import pandas as pd
import streamlit as st

from core.models import BOQLine, Item, Project
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
    # For backward compatibility with any legacy code:
    d["dsr_code"] = d.get("code", "")
    # Ensure 'item' points to description for old references
    d["item"] = d.get("description", "")
    return d


def _next_id() -> int:
    return len(st.session_state.qto_items) + 1


# =============================================================================
# Streamlit setup & session state
# =============================================================================

st.set_page_config(
    page_title="CPWD DSR 2023 – Civil + MEP Estimator",
    page_icon="🏗️",
    layout="wide",
)

if "qto_items" not in st.session_state:
    st.session_state.qto_items: List[Dict[str, Any]] = []

if "project_info" not in st.session_state:
    st.session_state.project_info = {
        "name": "G+1 Residential",
        "client": "CPWD Division",
        "engineer": "Er. Ravi Sharma",
        "location": "Delhi",
        "rate_source": "CPWD DSR 2023 (Civil + Elect)",
    }

# =============================================================================
# Header
# =============================================================================

st.markdown(
    """
<div style='background: linear-gradient(90deg, #1e3c72 0%, #2a5298 100%); padding:1.2rem; border-radius:0.7rem; color:white; text-align:center'>
  <h2 style='margin:0;'>🏗️ CPWD DSR 2023 – Civil + MEP Estimator (IS 1200, Packages, Rules)</h2>
  <p style='margin:0.2rem 0 0;'>JE-style estimate generator with auto-expansion, IS-1200 measurement and multi-discipline rule checks.</p>
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
    location = st.selectbox("Location", list(LOCATION_INDICES.keys()),
                            index=list(LOCATION_INDICES.keys()).index(
                                st.session_state.project_info.get("location", "Delhi")
                            )
                            )
    st.session_state.project_info["location"] = location
    cost_index = LOCATION_INDICES[location]
    st.info(f"Cost Index for **{location}**: **{cost_index}%** (Base = 100)")

    rate_source_names = list(RATE_SOURCES.keys())
    default_source = st.session_state.project_info.get("rate_source", rate_source_names[0])
    rate_source = st.selectbox("Rate Source", rate_source_names,
                               index=rate_source_names.index(default_source)
                               if default_source in rate_source_names
                               else 0)
    st.session_state.project_info["rate_source"] = rate_source
    current_dsr = RATE_SOURCES[rate_source]

    st.subheader("⚙️ Pricing Adjustments (for display only)")
    contingency_pct = st.slider("Contingency (%)", 0.0, 10.0, 5.0, 0.5)
    escalation_annual = st.slider("Escalation p.a. (%)", 0.0, 10.0, 5.0, 0.5)
    # We use base rates + index in calculations; contingency/escalation only for info.

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
col3.metric("📊 Sanction Estimate (~7.5% extra)", format_rupees(total_cost * 1.075))
col4.metric("🎯 P90 Risk Budget", format_rupees(mc["p90"]))

# =============================================================================
# Tabs
# =============================================================================

tab1, tab2, tab3, tab4 = st.tabs(
    ["📏 SOQ / BOQ", "📊 Abstract & Audit", "🎯 Risk", "📄 CPWD/PWD Formats"]
)

# =============================================================================
# TAB 1 – SOQ / BOQ – Single Items + Packages
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
            st.warning("No predefined items for this phase; please configure PHASE_GROUPS.")
        item_key = c2.selectbox(
            "DSR Item",
            available_items,
        ) if available_items else (None)

        if item_key and item_key in CPWD_BASE_DSR_2023:
            rec = CPWD_BASE_DSR_2023[item_key]
            item: Item = ITEMS[item_key]
            st.markdown(
                f"**Code:** `{item.code}` &nbsp;&nbsp; **Unit:** `{item.unit}` &nbsp;&nbsp; "
                f"**Category:** `{item.category}` &nbsp;&nbsp; **Rule:** `{item.measurement_rule}`"
            )

            measure_type = item.measure_type
            rule = item.measurement_rule or "volume"

            quantity = 0.0
            qto_info = ""

            # Geometry inputs based on measurement_rule
            if rule == "trench_excavation":
                c1, c2, c3, c4 = st.columns(4)
                L = c1.number_input("Length L (m)", 0.1, 1000.0, 10.0, 0.1)
                B = c2.number_input("Bottom breadth B (m)", 0.1, 10.0, 1.0, 0.1)
                D = c3.number_input("Depth D (m)", 0.1, 10.0, 1.5, 0.1)
                slope = c4.number_input("Side slope (H:1V)", 0.0, 3.0, 0.0, 0.1)
                res = IS1200Engine.trench_excavation(L, B, D, side_slope_h_over_v=slope)
                quantity = res["net"]
                qto_info = f"L×B×D with slope = {res['gross']:.3f} – {res['deductions']:.3f} = {res['net']:.3f} m³"
                length, breadth, depth, height = L, B, D, 0.0

            elif rule == "brickwork_wall":
                c1, c2, c3, c4 = st.columns(4)
                L = c1.number_input("Wall length L (m)", 0.1, 100.0, 5.0, 0.1)
                t = c2.number_input("Thickness t (m)", 0.05, 1.0, 0.23, 0.01)
                H = c3.number_input("Height H (m)", 0.1, 10.0, 3.0, 0.1)
                op_area = c4.number_input("Total large openings area (sqm)", 0.0, 50.0, 0.0, 0.1)
                openings = []
                if op_area > 0:
                    openings = [{"w": 1.0, "h": op_area, "n": 1}]
                res = IS1200Engine.brickwork_wall(L, t, H, openings)
                quantity = res["net"]
                qto_info = f"L×t×H = {res['gross']:.3f} – {res['deductions']:.3f} = {res['net']:.3f} m³"
                length, breadth, depth, height = L, t, 0.0, H

            elif rule == "wall_finish_area":
                c1, c2, c3, c4 = st.columns(4)
                L = c1.number_input("Wall length L (m)", 0.1, 100.0, 5.0, 0.1)
                H = c2.number_input("Wall height H (m)", 0.1, 10.0, 3.0, 0.1)
                sides = int(c3.number_input("Number of sides", 1, 2, 2, 1))
                op_area = c4.number_input("Total large openings area (sqm)", 0.0, 50.0, 0.0, 0.1)
                openings = []
                if op_area > 0:
                    openings = [{"w": 1.0, "h": op_area, "n": 1}]
                res = IS1200Engine.wall_finish_area(L, H, sides=sides, openings=openings)
                quantity = res["net"]
                qto_info = f"Gross {res['gross']:.3f} – Deduction {res['deductions']:.3f} = {res['net']:.3f} sqm"
                length, breadth, depth, height = L, H, 0.0, H

            elif rule == "floor_area":
                c1, c2, c3 = st.columns(3)
                L = c1.number_input("Length L (m)", 0.1, 100.0, 4.0, 0.1)
                B = c2.number_input("Breadth B (m)", 0.1, 100.0, 3.0, 0.1)
                cutouts = c3.number_input("Total cutout area (sqm)", 0.0, 50.0, 0.0, 0.1)
                cut = []
                if cutouts > 0:
                    cut = [{"w": 1.0, "h": cutouts, "n": 1}]
                res = IS1200Engine.floor_area(L, B, cut)
                quantity = res["net"]
                qto_info = f"L×B = {res['gross']:.3f} – Cutouts {res['deductions']:.3f} = {res['net']:.3f} sqm"
                length, breadth, depth, height = L, B, 0.0, 0.0

            else:  # default volume / simple area / length
                if measure_type == "volume":
                    c1, c2, c3, c4 = st.columns(4)
                    L = c1.number_input("Length L (m)", 0.1, 100.0, 2.0, 0.1)
                    B = c2.number_input("Breadth B (m)", 0.1, 100.0, 1.0, 0.1)
                    D = c3.number_input("Depth D (m)", 0.01, 10.0, 0.3, 0.01)
                    ded = c4.number_input("Deductions (m³)", 0.0, 10.0, 0.0, 0.1)
                    res = IS1200Engine.volume(L, B, D, deductions=ded)
                    quantity = res["net"]
                    qto_info = f"L×B×D = {res['gross']:.3f} – {res['deductions']:.3f} = {res['net']:.3f} m³"
                    length, breadth, depth, height = L, B, D, 0.0
                elif measure_type == "area":
                    c1, c2 = st.columns(2)
                    L = c1.number_input("Length L (m)", 0.1, 100.0, 4.0, 0.1)
                    B = c2.number_input("Breadth/Width B (m)", 0.1, 100.0, 3.0, 0.1)
                    gross = L * B
                    quantity = gross
                    qto_info = f"L×B = {gross:.3f} sqm"
                    length, breadth, depth, height = L, B, 0.0, 0.0
                elif measure_type == "length":
                    L = st.number_input("Length (m)", 0.1, 1000.0, 10.0, 0.1)
                    quantity = L
                    qto_info = f"Length = {L:.3f} m"
                    length, breadth, depth, height = L, 0.0, 0.0, 0.0
                else:  # weight/each
                    quantity = st.number_input("Quantity", 0.0, 1e6, 1.0, 1.0)
                    qto_info = f"Quantity = {quantity:.3f} {item.unit}"
                    length, breadth, depth, height = 0.0, 0.0, 0.0, 0.0

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
    # 1B. Civil Work Package
    # -------------------------------------------------------------------------
    elif mode == "Civil Work Package":
        pkg_name = st.selectbox("Select Civil Package", list(WORK_PACKAGES_CIVIL.keys()))
        pkg = WORK_PACKAGES_CIVIL[pkg_name]

        st.markdown(f"**Package:** {pkg.name}")
        st.caption(pkg.description)

        ctx: Dict[str, Any] = {}
        # Minimal UI for the known packages
        if "Site clearance" in pkg_name:
            ctx["site_area_sqm"] = st.number_input("Site clearance area (sqm)", 10.0, 1e6, 500.0, 10.0)
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

            ctx["backfill_volume_cum"] = st.number_input("Backfill volume (cum)", 0.0, 1e6, 0.0, 0.1)

        elif "Brick wall with plaster" in pkg_name:
            c1, c2, c3 = st.columns(3)
            ctx["L_wall"] = c1.number_input("Wall length L (m)", 0.1, 100.0, 5.0, 0.1)
            ctx["H_wall"] = c2.number_input("Wall height H (m)", 0.1, 10.0, 3.0, 0.1)
            ctx["t_wall"] = c3.number_input("Thickness t (m)", 0.05, 1.0, 0.23, 0.01)

        elif "Vitrified floor tiles" in pkg_name:
            c1, c2, c3 = st.columns(3)
            ctx["L_room"] = c1.number_input("Room length L (m)", 0.1, 100.0, 4.0, 0.1)
            ctx["B_room"] = c2.number_input("Room breadth B (m)", 0.1, 100.0, 3.0, 0.1)
            ctx["wastage_factor"] = c3.number_input("Wastage factor", 1.00, 1.20, 1.03, 0.01)

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
    else:
        pkg_name = st.selectbox("Select MEP Package", list(WORK_PACKAGES_MEP.keys()))
        pkg = WORK_PACKAGES_MEP[pkg_name]

        st.markdown(f"**Package:** {pkg.name}")
        st.caption(pkg.description)

        ctx: Dict[str, Any] = {}
        # Electrical lighting package
        if "lighting wiring" in pkg_name.lower():
            c1, c2 = st.columns(2)
            ctx["lighting_points"] = c1.number_input("Lighting points", 1, 200, 8, 1)
            ctx["avg_run_ltg"] = c2.number_input("Avg horizontal run per point (m)", 1.0, 50.0, 8.0, 0.5)
            c3, c4 = st.columns(2)
            ctx["vertical_drop"] = c3.number_input("Vertical drop (m)", 1.0, 6.0, 3.0, 0.1)
            ctx["lighting_points_per_circuit"] = int(
                c4.number_input("Points per circuit", 2, 15, 8, 1)
            )
            ctx["points_per_switchboard"] = int(
                st.number_input("Points per 6M switchboard", 1, 20, 4, 1)
            )

        # Plumbing toilet fixtures
        elif "Toilet block plumbing" in pkg_name:
            c1, c2, c3 = st.columns(3)
            ctx["toilet_blocks"] = c1.number_input("No. of toilet blocks", 1, 50, 2, 1)
            ctx["wc_per_block"] = c2.number_input("WCs per block", 1, 20, 2, 1)
            ctx["basins_per_block"] = c3.number_input("Basins per block", 1, 20, 2, 1)
            c4, c5, c6 = st.columns(3)
            ctx["urinals_per_block"] = c4.number_input("Urinals per block", 0, 20, 1, 1)
            ctx["floor_traps_per_block"] = c5.number_input("Floor traps per block", 0, 20, 2, 1)
            ctx["nahani_traps_per_block"] = c6.number_input("Nahani traps per block", 0, 20, 0, 1)

        # HVAC ducting
        elif "ahu zone ducting" in pkg_name.lower():
            c1, c2, c3 = st.columns(3)
            ctx["supply_cmh"] = c1.number_input("Supply airflow (CMH)", 100.0, 200000.0, 8000.0, 100.0)
            ctx["main_duct_length_m"] = c2.number_input("Main duct length (m)", 5.0, 500.0, 20.0, 1.0)
            ctx["branch_duct_length_m"] = c3.number_input("Branch duct length (m)", 5.0, 1000.0, 40.0, 1.0)

        # Fire alarm floor
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
    # Display current SOQ/BOQ
    # -------------------------------------------------------------------------
    if st.session_state.qto_items:
        st.markdown("### Current SOQ / BOQ")
        df = pd.DataFrame(st.session_state.qto_items)
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
        show_cols = [c for c in show_cols if c in df.columns]
        st.dataframe(df[show_cols].round(3), use_container_width=True)

        col_btn1, col_btn2 = st.columns(2)
        if col_btn1.button("🧹 Clear SOQ", type="secondary"):
            st.session_state.qto_items = []
            st.experimental_rerun()
        if col_btn2.button("💾 Download BOQ (CSV)"):
            csv = df.to_csv(index=False).encode("utf-8")
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
        # Abstract by phase
        df = pd.DataFrame(st.session_state.qto_items)
        phase_totals = df.groupby("phase")["amount"].sum().reset_index()
        phase_totals["Amount (₹)"] = phase_totals["amount"].apply(format_rupees)
        st.markdown("### Phase-wise Abstract (Form 5A Style)")
        st.dataframe(
            phase_totals[["phase", "Amount (₹)"]].rename(columns={"phase": "Phase"}),
            use_container_width=True,
        )

        st.markdown("**Grand Total:** " + format_rupees(total_cost))

        # Audit rules
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
            prev = 0.0  # for first bill
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
            df6 = pd.DataFrame(wo_data)
            st.dataframe(df6, use_container_width=True)

            st.download_button(
                "📥 Download PWD Form 6 (CSV)",
                df6.to_csv(index=False).encode("utf-8"),
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

st.success("✅ Estimator ready – Civil + MEP packages, IS 1200 measurement, and multi-discipline rule checks are active.")
```
