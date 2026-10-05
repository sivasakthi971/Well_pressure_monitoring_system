import os
import sqlite3
import time
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots

DATA_DIR = os.getenv("DATA_DIR", ".")
CSV_FILE = os.path.join(DATA_DIR, "pressure_data.csv")
DB_FILE = os.path.join(DATA_DIR, "well_integrity.db")

MAASP_LIMITS = {
    "tubing_head": 148.0,
    "casing_A": 110.0,
    "casing_B": 95.0,
    "casing_C": 85.0,
    "flowline": 100.0,
    "choke": 90.0
}

st.set_page_config(
    page_title="Wellhead Pressure Monitoring Dashboard",
    page_icon="🛢️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Clean, User-Friendly Dark Industrial Styling
st.markdown("""
<style>
    .stApp {
        background-color: #0B0E14;
        color: #E2E8F0;
        font-family: 'Inter', system-ui, -apple-system, sans-serif;
    }
    
    .header-banner {
        background: linear-gradient(135deg, #0F172A 0%, #1E293B 100%);
        border: 1px solid #334155;
        border-radius: 10px;
        padding: 16px 20px;
        margin-bottom: 20px;
    }
    .header-title {
        font-size: 24px;
        font-weight: 700;
        color: #F8FAFC;
        margin: 0;
    }
    .header-subtitle {
        font-size: 13px;
        color: #94A3B8;
        margin-top: 4px;
    }

    .kpi-card {
        background: #1E293B;
        border: 1px solid #334155;
        border-radius: 8px;
        padding: 14px 16px;
        text-align: center;
    }
    .kpi-title {
        font-size: 12px;
        font-weight: 600;
        text-transform: uppercase;
        color: #94A3B8;
        margin-bottom: 4px;
    }
    .kpi-value {
        font-size: 26px;
        font-weight: 700;
        color: #F8FAFC;
    }
    .kpi-good { color: #10B981; }
    .kpi-warn { color: #F59E0B; }
    .kpi-crit { color: #EF4444; }

    .well-card {
        background: #1E293B;
        border-radius: 10px;
        padding: 16px;
        margin-bottom: 14px;
        border-left: 5px solid #3B82F6;
    }
    .well-card-crit { border-left-color: #EF4444; background: linear-gradient(180deg, #2D1517 0%, #1E293B 100%); }
    .well-card-warn { border-left-color: #F59E0B; background: linear-gradient(180deg, #2A2111 0%, #1E293B 100%); }
    .well-card-good { border-left-color: #10B981; }

    .badge {
        display: inline-block;
        padding: 3px 8px;
        border-radius: 12px;
        font-size: 11px;
        font-weight: 700;
    }
    .badge-normal { background: rgba(16, 185, 129, 0.2); color: #34D399; border: 1px solid #10B981; }
    .badge-warning { background: rgba(245, 158, 11, 0.2); color: #FBBF24; border: 1px solid #F59E0B; }
    .badge-critical { background: rgba(239, 68, 68, 0.2); color: #F87171; border: 1px solid #EF4444; }

    section[data-testid="stSidebar"] {
        background-color: #0F172A;
        border-right: 1px solid #1E293B;
    }
</style>
""", unsafe_allow_html=True)

def load_data():
    if os.path.exists(DB_FILE):
        try:
            conn = sqlite3.connect(DB_FILE)
            df = pd.read_sql_query("SELECT * FROM telemetry ORDER BY id DESC LIMIT 300", conn)
            alarms_df = pd.read_sql_query("SELECT * FROM alarms ORDER BY id DESC LIMIT 100", conn)
            conn.close()
            if not df.empty:
                return df, alarms_df
        except Exception:
            pass

    if os.path.exists(CSV_FILE):
        df = pd.read_csv(CSV_FILE).tail(300)
        return df, pd.DataFrame()

    return pd.DataFrame(), pd.DataFrame()

df, alarms_df = load_data()

if df.empty:
    st.info("⏳ Connecting to RTU Telemetry Bus...")
    time.sleep(3)
    st.rerun()

well_list = sorted(df["well_id"].unique().tolist())
if not well_list:
    well_list = ["WELL-001"]

# Sidebar Navigation (Simple & Clean)
st.sidebar.title("🛢️ Wellhead Surveillance")
st.sidebar.markdown("---")

view_mode = st.sidebar.radio(
    "Navigation",
    [
        "🌐 Well Stock Overview & Watch-List",
        "📈 Pressure Trends & MAASP Drill-Down",
        "⚡ Production Loss Signals",
        "🚨 Severity Escalation Center"
    ]
)

st.sidebar.markdown("---")
selected_well = st.sidebar.selectbox("Target Well", ["All Wells"] + well_list)

# Header
st.markdown("""
<div class="header-banner">
    <div class="header-title">🛢️ Wellhead Pressure Monitoring Dashboard</div>
    <div class="header-subtitle">Real-Time Surveillance • Sustained Casing Pressure (SCP) • MAASP Containment • Production Loss Signals</div>
</div>
""", unsafe_allow_html=True)

# Latest well status calculation
total_wells = len(well_list)
crit_wells = 0
warn_wells = 0
healthy_wells = 0

well_latest_map = {}
for w_id in well_list:
    w_df = df[df["well_id"] == w_id]
    if w_df.empty:
        continue
    latest = w_df.iloc[0] if "id" in w_df.columns else w_df.iloc[-1]
    well_latest_map[w_id] = latest
    c_a = latest.get("casing_A", 0)
    t_head = latest.get("tubing_head", 0)
    flowline = latest.get("flowline", 0)

    if c_a > MAASP_LIMITS["casing_A"] or t_head > MAASP_LIMITS["tubing_head"]:
        crit_wells += 1
    elif flowline < 35.0:
        warn_wells += 1
    else:
        healthy_wells += 1

# Top KPI Summary Bar
k1, k2, k3, k4 = st.columns(4)
with k1:
    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-title">Monitored Well Stock</div>
        <div class="kpi-value">{total_wells}</div>
    </div>
    """, unsafe_allow_html=True)
with k2:
    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-title">Healthy Wells</div>
        <div class="kpi-value kpi-good">{healthy_wells} / {total_wells}</div>
    </div>
    """, unsafe_allow_html=True)
with k3:
    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-title">MAASP / SCP Risk Breaches</div>
        <div class="kpi-value kpi-crit">{crit_wells}</div>
    </div>
    """, unsafe_allow_html=True)
with k4:
    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-title">Production Loss Signals</div>
        <div class="kpi-value kpi-warn">{warn_wells}</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ------------------------------------------------------------------------------
# VIEW 1: WELL STOCK OVERVIEW & INTEGRITY WATCH-LIST
# ------------------------------------------------------------------------------
if view_mode == "🌐 Well Stock Overview & Watch-List":
    st.subheader("🌐 Well Stock Status (Single Live View)")

    cols = st.columns(len(well_list))
    for i, w_id in enumerate(well_list):
        latest = well_latest_map.get(w_id, {})
        if not latest.to_dict():
            continue
        
        c_a = latest.get("casing_A", 0)
        t_head = latest.get("tubing_head", 0)
        flowline = latest.get("flowline", 0)
        choke = latest.get("choke", 0)

        is_crit = (c_a > MAASP_LIMITS["casing_A"] or t_head > MAASP_LIMITS["tubing_head"])
        is_warn = (flowline < 35.0)

        card_class = "well-card-crit" if is_crit else ("well-card-warn" if is_warn else "well-card-good")
        badge_html = '<span class="badge badge-critical">🚨 CRITICAL</span>' if is_crit else (
            '<span class="badge badge-warning">⚠️ WARNING</span>' if is_warn else '<span class="badge badge-normal">✅ NORMAL</span>'
        )

        with cols[i]:
            st.markdown(f"""
            <div class="well-card {card_class}">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                    <h3 style="margin: 0; color: #F8FAFC;">{w_id}</h3>
                    {badge_html}
                </div>
                <div style="font-size: 13px; color: #CBD5E1; line-height: 1.7;">
                    <strong>Tubing Head:</strong> <span style="color: #38BDF8; font-weight:700;">{t_head:.1f} bar</span><br/>
                    <strong>Casing A (SCP):</strong> <span style="color: {'#EF4444' if c_a > MAASP_LIMITS['casing_A'] else '#34D399'}; font-weight:700;">{c_a:.1f} bar</span><br/>
                    <strong>Flowline:</strong> <span style="color: #FBBF24; font-weight:700;">{flowline:.1f} bar</span><br/>
                    <strong>Choke:</strong> <span style="color: #E2E8F0; font-weight:700;">{choke:.1f}%</span>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            pct_maasp = min(100.0, (c_a / MAASP_LIMITS['casing_A']) * 100)
            st.progress(pct_maasp / 100.0, text=f"Casing A MAASP: {pct_maasp:.0f}%")

    st.markdown("---")
    st.subheader("🛡️ Integrity Watch-List (MAASP & SCP Containment Breaches)")

    watchlist_data = []
    for w_id in well_list:
        latest = well_latest_map.get(w_id, {})
        c_a = latest.get("casing_A", 0)
        t_head = latest.get("tubing_head", 0)
        
        if c_a > MAASP_LIMITS["casing_A"]:
            watchlist_data.append({
                "Well ID": w_id,
                "Integrity Parameter": "Casing A (SCP)",
                "Current Pressure": f"{c_a:.2f} bar",
                "MAASP Limit": f"{MAASP_LIMITS['casing_A']:.0f} bar",
                "Exceedance": f"+{c_a - MAASP_LIMITS['casing_A']:.2f} bar",
                "Severity": "CRITICAL",
                "Action": "Bleed down annulus & monitor build-up dP/dt rate"
            })
        elif t_head > MAASP_LIMITS["tubing_head"]:
            watchlist_data.append({
                "Well ID": w_id,
                "Integrity Parameter": "Tubing Head (HIHI)",
                "Current Pressure": f"{t_head:.2f} bar",
                "MAASP Limit": f"{MAASP_LIMITS['tubing_head']:.0f} bar",
                "Exceedance": f"+{t_head - MAASP_LIMITS['tubing_head']:.2f} bar",
                "Severity": "CRITICAL",
                "Action": "Throttle choke & verify automated SSSV shutdown"
            })

    if watchlist_data:
        st.dataframe(pd.DataFrame(watchlist_data))
    else:
        st.success("✅ All wells operating safely within MAASP containment limits.")

# ------------------------------------------------------------------------------
# VIEW 2: PRESSURE TRENDS & MAASP DRILL-DOWN
# ------------------------------------------------------------------------------
elif view_mode == "📈 Pressure Trends & MAASP Drill-Down":
    target_well = selected_well if selected_well != "All Wells" else well_list[0]
    st.subheader(f"📈 Pressure Trends & MAASP Overlays: {target_well}")

    w_df = df[df["well_id"] == target_well].copy()
    if not w_df.empty:
        latest = w_df.iloc[0] if "id" in w_df.columns else w_df.iloc[-1]

        m1, m2, m3, m4, m5, m6 = st.columns(6)
        m1.metric("Tubing Head", f"{latest.get('tubing_head', 0):.1f} bar")
        m2.metric("Casing A (SCP)", f"{latest.get('casing_A', 0):.1f} bar")
        m3.metric("Casing B", f"{latest.get('casing_B', 0):.1f} bar")
        m4.metric("Casing C", f"{latest.get('casing_C', 0):.1f} bar")
        m5.metric("Flowline", f"{latest.get('flowline', 0):.1f} bar")
        m6.metric("Choke Valve", f"{latest.get('choke', 0):.1f}%")

        st.markdown("---")

        fig = make_subplots(
            rows=2, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.1,
            subplot_titles=("Tubing Head & Casing Annulus Pressures (bar)", "Flowline Pressure & Choke Position (%)")
        )

        w_df_sorted = w_df.sort_values("timestamp")

        fig.add_trace(go.Scatter(x=w_df_sorted["timestamp"], y=w_df_sorted["tubing_head"], name="Tubing Head", line=dict(color="#38BDF8", width=2)), row=1, col=1)
        fig.add_trace(go.Scatter(x=w_df_sorted["timestamp"], y=w_df_sorted["casing_A"], name="Casing A (SCP)", line=dict(color="#EF4444", width=2)), row=1, col=1)
        fig.add_trace(go.Scatter(x=w_df_sorted["timestamp"], y=w_df_sorted["casing_B"], name="Casing B", line=dict(color="#F59E0B", width=1.5, dash="dash")), row=1, col=1)

        fig.add_hline(y=MAASP_LIMITS["casing_A"], line_dash="dot", line_color="#EF4444", annotation_text="Casing A MAASP (110 bar)", row=1, col=1)
        fig.add_hline(y=MAASP_LIMITS["tubing_head"], line_dash="dot", line_color="#38BDF8", annotation_text="Tubing MAOP (148 bar)", row=1, col=1)

        fig.add_trace(go.Scatter(x=w_df_sorted["timestamp"], y=w_df_sorted["flowline"], name="Flowline (bar)", line=dict(color="#10B981", width=2)), row=2, col=1)
        fig.add_trace(go.Scatter(x=w_df_sorted["timestamp"], y=w_df_sorted["choke"], name="Choke Position (%)", line=dict(color="#A855F7", width=1.5, dash="dot")), row=2, col=1)

        fig.update_layout(
            template="plotly_dark",
            paper_bgcolor="#0B0E14",
            plot_bgcolor="#1E293B",
            height=480,
            margin=dict(l=10, r=10, t=30, b=10)
        )

        st.plotly_chart(fig)

# ------------------------------------------------------------------------------
# VIEW 3: PRODUCTION LOSS SIGNALS
# ------------------------------------------------------------------------------
elif view_mode == "⚡ Production Loss Signals":
    st.subheader("⚡ Production Loss Diagnostics (Blockage, Sand-up & Hydrates)")

    loss_events = []
    for w_id in well_list:
        latest = well_latest_map.get(w_id, {})
        flowline = latest.get("flowline", 0)
        choke = latest.get("choke", 0)
        t_head = latest.get("tubing_head", 0)
        diff_dp = choke - flowline

        if flowline < 35.0 or diff_dp > 25.0:
            loss_events.append({
                "Well ID": w_id,
                "Detected Signal": "Hydrate Formation / Flowline Blockage",
                "Tubing Pressure": f"{t_head:.1f} bar",
                "Flowline Pressure": f"{flowline:.1f} bar",
                "Choke Setting": f"{choke:.1f}%",
                "Pressure Drop (ΔP)": f"{diff_dp:.1f} bar",
                "Severity": "WARNING",
                "Action": "Inject inhibitor & inspect choke valve"
            })

    if loss_events:
        st.dataframe(pd.DataFrame(loss_events))
    else:
        st.success("✅ No production blockage or hydrate signals detected.")

# ------------------------------------------------------------------------------
# VIEW 4: SEVERITY ESCALATION CENTER
# ------------------------------------------------------------------------------
elif view_mode == "🚨 Severity Escalation Center":
    st.subheader("🚨 Role-Based Escalation Matrix")

    t1, t2 = st.tabs(["👷 WARNING (Field Operator)", "🛡️ CRITICAL (Well Integrity & HSE)"])

    with t1:
        st.markdown("**Target Role: Field Operator** • Operational drift & flowline blockage warnings")
        if not alarms_df.empty and "severity" in alarms_df.columns:
            warn_df = alarms_df[alarms_df["severity"] == "WARNING"]
            st.dataframe(warn_df)
        else:
            st.info("No active WARNING escalation events.")

    with t2:
        st.markdown("**Target Role: Well Integrity Engineer & HSE** • MAASP breaches & Sustained Casing Pressure")
        if not alarms_df.empty and "severity" in alarms_df.columns:
            crit_df = alarms_df[alarms_df["severity"] == "CRITICAL"]
            st.dataframe(crit_df)
        else:
            st.info("No active CRITICAL escalation events.")

# Auto refresh loop
time.sleep(3)
st.rerun()