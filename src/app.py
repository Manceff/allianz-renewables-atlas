"""Allianz Renewables Atlas — single-page entry point.

Globe terrestre orthographique sur fond starfield, click natif sur un marker
ouvre une analyse fine pour un analyste private equity.

Style : dark space, vibe ISS / Tesla console — pas d'emojis, pas de gimmick.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

# Ajout de la racine au sys.path pour `from src.lib.X`
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.lib.parks_loader import load_parks_index
from src.lib.pvgis_fetch import fetch_pvgis_hourly
from src.lib.reported_production import load_reported_production
from src.lib.solar_metrics import (
    capacity_factor_annual,
    estimate_for_date,
    monthly_aggregates,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Page config + CSS injection
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Allianz Renewables Atlas",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="collapsed",
)

CSS_PATH = Path(__file__).resolve().parent / "assets" / "style.css"
if CSS_PATH.exists():
    st.markdown(f"<style>{CSS_PATH.read_text()}</style>", unsafe_allow_html=True)

PORTFOLIO_SWEEP_PATH = _ROOT / "data" / "portfolio_sweep.json"

SEVERITY_COLORS = {
    "green": "#10b981",
    "yellow": "#facc15",
    "red": "#f87171",
    "none": "#475569",
}

SEVERITY_LABELS = {
    "green": "ALIGNED",
    "yellow": "MONITOR",
    "red": "INVESTIGATE",
    "none": "N/A",
}

MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------


@st.cache_data
def _load_parks_df() -> pd.DataFrame:
    idx = load_parks_index()
    return pd.DataFrame(
        [
            {
                "id": p.id,
                "name": p.name,
                "country": p.country,
                "lat": p.lat,
                "lon": p.lon,
                "capacity_mwp": p.capacity_mwp or 0.0,
                "commissioning_year": p.commissioning_year,
                "operator": p.operator or "—",
                "press_release_url": p.press_release_url,
            }
            for p in idx.parks
        ]
    )


@st.cache_data
def _load_severity_map() -> dict[str, str]:
    if not PORTFOLIO_SWEEP_PATH.exists():
        return {}
    try:
        with open(PORTFOLIO_SWEEP_PATH) as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    entries = data.get("entries", []) if isinstance(data, dict) else []
    return {e.get("park_id"): e.get("severity") for e in entries if e.get("park_id")}


@st.cache_data
def _load_reported() -> dict[str, dict]:
    rep = load_reported_production()
    return {pid: r.model_dump(mode="json") for pid, r in rep.items()}


@st.cache_data(ttl=86400, show_spinner=False)
def _fetch_hourly_cached(park_id: str, lat: float, lon: float, peakpower_mw: float) -> dict:
    return fetch_pvgis_hourly(lat=lat, lon=lon, peakpower_mw=peakpower_mw)


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

st.markdown(
    """
    <div style="text-align: center; padding: 1.2rem 0 0.4rem;">
        <h1 style="margin: 0; font-size: 1.9rem; font-weight: 600; letter-spacing: -0.02em;">
            Allianz Renewables Atlas
        </h1>
        <p style="color: #94a3b8; font-size: 0.85rem; margin-top: 0.3rem; letter-spacing: 0.04em;">
            Solar PV assets owned directly by Allianz Capital Partners · 2010-2026
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

parks_df = _load_parks_df()
severity_map = _load_severity_map()
reported_map = _load_reported()

# Compute severity at runtime for completeness (some parks may not be in portfolio_sweep yet)
parks_df["severity"] = parks_df["id"].map(severity_map).fillna("none")
# Force grey-with-cyan-edge for "none" severity so they're still visible on the dark globe
parks_df["color"] = parks_df["severity"].map(SEVERITY_COLORS)
# Bigger min size so markers are visible on the orthographic projection
parks_df["marker_size"] = parks_df["capacity_mwp"].clip(lower=18, upper=50)

# ---------------------------------------------------------------------------
# Top metrics — sober, no emoji
# ---------------------------------------------------------------------------

c1, c2, c3, c4 = st.columns(4)
c1.metric("Solar parks", f"{len(parks_df)}")
c2.metric("Installed capacity", f"{parks_df['capacity_mwp'].sum():,.0f} MWp")
c3.metric("Countries", f"{parks_df['country'].nunique()}")
c4.metric("With production delta", f"{len(reported_map)} of {len(parks_df)}")

st.markdown("<br>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Globe — Plotly orthographic, ISS-style palette
# ---------------------------------------------------------------------------

# Single trace for click-event simplicity
fig = go.Figure()

fig.add_trace(
    go.Scattergeo(
        lat=parks_df["lat"],
        lon=parks_df["lon"],
        mode="markers",
        marker=dict(
            size=parks_df["marker_size"].tolist(),
            color=parks_df["color"].tolist(),
            line=dict(width=1.5, color="rgba(125, 211, 252, 0.7)"),
            opacity=0.95,
        ),
        text=parks_df["name"],
        customdata=parks_df[["id", "country", "capacity_mwp", "operator", "commissioning_year"]].values,
        hovertemplate=(
            "<b>%{text}</b><br>"
            "%{customdata[1]} · %{customdata[2]:.1f} MWp<br>"
            "%{customdata[3]} · COD %{customdata[4]}<extra></extra>"
        ),
        name="",
    )
)

fig.update_geos(
    showland=True,
    landcolor="#5a4a35",          # warm tan / desert (vu de l'ISS de nuit)
    showocean=True,
    oceancolor="#020512",         # quasi noir
    showcountries=True,
    countrycolor="rgba(255, 220, 160, 0.18)",
    showcoastlines=True,
    coastlinecolor="rgba(255, 220, 160, 0.40)",
    showframe=False,
    bgcolor="rgba(0,0,0,0)",
    projection=dict(
        type="orthographic",
        rotation=dict(lon=2, lat=42, roll=0),  # centré Europe / Iberie
    ),
    showlakes=False,
    showrivers=False,
)

fig.update_layout(
    height=560,
    margin=dict(l=0, r=0, t=0, b=0),
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    showlegend=False,
)

# Atmospheric halo overlay via Plotly shape (paper coordinates, behind plot)
fig.add_layout_image(
    dict(
        source="data:image/svg+xml;utf8,"
               "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 600 600'>"
               "<defs><radialGradient id='atm' cx='50%' cy='50%' r='50%'>"
               "<stop offset='40%' stop-color='rgba(0,0,0,0)'/>"
               "<stop offset='52%' stop-color='rgba(125,211,252,0.18)'/>"
               "<stop offset='62%' stop-color='rgba(125,211,252,0.06)'/>"
               "<stop offset='100%' stop-color='rgba(0,0,0,0)'/>"
               "</radialGradient></defs>"
               "<rect width='600' height='600' fill='url(%23atm)'/></svg>",
        xref="paper", yref="paper",
        x=0.5, y=0.5,
        sizex=1.0, sizey=1.0,
        xanchor="center", yanchor="middle",
        layer="below",
        sizing="contain",
    )
)

# Render globe with standard plotly_chart (markers render reliably).
# Click-on-marker via streamlit-plotly-events drops Scattergeo points — we use
# the dropdown below the globe instead.
st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

# Park selector — single source of truth for which park is shown
park_options = ["— select a park —"] + parks_df["name"].tolist()
selected_park_id = st.session_state.get("selected_park_id")
default_idx = 0
if selected_park_id:
    matching = parks_df[parks_df["id"] == selected_park_id]
    if not matching.empty:
        default_idx = park_options.index(matching.iloc[0]["name"])

selected_name = st.selectbox(
    "Park",
    options=park_options,
    index=default_idx,
    label_visibility="collapsed",
)

if selected_name != "— select a park —":
    matching = parks_df[parks_df["name"] == selected_name]
    if not matching.empty:
        st.session_state["selected_park_id"] = matching.iloc[0]["id"]
        selected_park_id = matching.iloc[0]["id"]
else:
    selected_park_id = None
    if "selected_park_id" in st.session_state:
        del st.session_state["selected_park_id"]

if not selected_park_id:
    st.markdown(
        """
        <div style="text-align: center; color: #64748b; padding: 1.5rem 0; font-size: 0.85rem;">
            Click a marker on the globe — or use the dropdown above — to open the park analysis.
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.stop()

selected_row = parks_df[parks_df["id"] == selected_park_id].iloc[0]

# ---------------------------------------------------------------------------
# Detail panel — fetch PVGIS and render
# ---------------------------------------------------------------------------

with st.spinner(f"Computing PVGIS for {selected_row['name']}…"):
    try:
        hourly_data = _fetch_hourly_cached(
            park_id=selected_park_id,
            lat=selected_row["lat"],
            lon=selected_row["lon"],
            peakpower_mw=selected_row["capacity_mwp"],
        )
    except Exception as e:
        st.error(f"PVGIS request failed: {e}")
        st.stop()

today_est = estimate_for_date(
    hourly_kwh=hourly_data["hourly_production_kwh"],
    irradiance_wm2=hourly_data["hourly_irradiance_wm2"],
)

annual_kwh = hourly_data["annual_total_kwh"]
annual_mwh = annual_kwh / 1000.0
cf_annual = capacity_factor_annual(
    hourly_data["hourly_production_kwh"], peakpower_mw=selected_row["capacity_mwp"]
)
monthly = monthly_aggregates(hourly_data["hourly_production_kwh"])

reported = reported_map.get(selected_park_id)
delta_pct = None
delta_severity = "none"
if reported:
    rep_mwh = float(reported["annual_mwh"])
    delta_pct = (annual_mwh - rep_mwh) / rep_mwh * 100.0
    if abs(delta_pct) < 5:
        delta_severity = "green"
    elif abs(delta_pct) < 10:
        delta_severity = "yellow"
    else:
        delta_severity = "red"

# ---------------------------------------------------------------------------
# Park header
# ---------------------------------------------------------------------------

st.markdown(
    f"""
    <div class="park-header">
      <div class="park-title">{selected_row['name']}</div>
      <div class="park-meta">
        {selected_row['country']}
        <span class="dot">·</span>
        {selected_row['capacity_mwp']:,.1f} MWp
        <span class="dot">·</span>
        COD {selected_row['commissioning_year']}
        <span class="dot">·</span>
        operator {selected_row['operator']}
        <span class="dot">·</span>
        <a href="{selected_row['press_release_url']}" target="_blank">press release</a>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# 4 KPI metrics — terminal style, no emoji
# ---------------------------------------------------------------------------

m1, m2, m3, m4 = st.columns(4)

m1.metric(
    "Today's typical output",
    f"{today_est['production_kwh'] / 1000:,.1f} MWh",
    help=f"Climatological estimate for {today_est['date']}, based on TMY 2019.",
)
m2.metric(
    "Annual estimate",
    f"{annual_mwh:,.0f} MWh",
    help="PVGIS PVcalc annual production with 14% system losses.",
)
m3.metric(
    "Capacity factor",
    f"{cf_annual:.1f} %",
    help="Annual production / (peakpower × 8760 h). Industry benchmark for solar in Europe: 12-18%.",
)

if reported:
    m4.metric(
        "Delta vs reported",
        f"{delta_pct:+.1f} %",
        delta=SEVERITY_LABELS[delta_severity],
        delta_color="off",
        help=f"Reported {float(reported['annual_mwh']):,.0f} MWh ({reported['year']}) — see operator press release.",
    )
else:
    m4.metric("Delta vs reported", "—", help="No public production figure available for this park.")

st.markdown("<br>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Single chart — monthly seasonality
# ---------------------------------------------------------------------------

monthly_mwh = [m["production_mwh"] for m in monthly]

fig_monthly = go.Figure()
fig_monthly.add_trace(
    go.Bar(
        x=MONTH_NAMES,
        y=monthly_mwh,
        marker=dict(
            color="rgba(125, 211, 252, 0.85)",
            line=dict(color="rgba(125, 211, 252, 1)", width=1),
        ),
        hovertemplate="%{x} · %{y:,.0f} MWh<extra></extra>",
        name="Estimated",
    )
)

if reported:
    avg_monthly_reported = float(reported["annual_mwh"]) / 12.0
    fig_monthly.add_hline(
        y=avg_monthly_reported,
        line_dash="dash",
        line_color="#facc15",
        line_width=1.5,
        annotation_text=f"Reported avg: {avg_monthly_reported:,.0f} MWh/mo",
        annotation_position="top right",
        annotation_font=dict(color="#facc15", size=11),
    )

fig_monthly.update_layout(
    title=dict(
        text="Monthly production estimate (MWh)",
        font=dict(color="#cbd5e1", size=14, weight=500),
        x=0.0,
        xanchor="left",
    ),
    height=320,
    margin=dict(l=0, r=0, t=40, b=0),
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    xaxis=dict(showgrid=False, tickfont=dict(color="#94a3b8")),
    yaxis=dict(
        gridcolor="rgba(125, 211, 252, 0.08)",
        tickfont=dict(color="#94a3b8"),
        title=None,
    ),
    showlegend=False,
)

st.plotly_chart(fig_monthly, width="stretch", config={"displayModeBar": False})

# ---------------------------------------------------------------------------
# About this data — collapsed expander (replaces methodology page)
# ---------------------------------------------------------------------------

with st.expander("About the methodology", expanded=False):
    st.markdown(
        """
**Source.** PVGIS v5.2 (Joint Research Centre, European Commission) —
the reference tool for European solar production estimates. Free, no API key.
<https://re.jrc.ec.europa.eu/pvg_tools/en/>

**TMY (Typical Meteorological Year).** PVGIS reports what a panel produces in
an *average* climatic year, computed from 16 years of satellite radiation data
(2005-2020 for Europe-Africa). It does **not** report what the park produced
this specific year.

**Default assumptions.** System losses 14% (inverter, cabling, soiling
baseline) — varied 10/14/18% for confidence interval. Mounting fixed,
azimuth 0° south, tilt = lat. crystSi modules.

**Reading the delta.** A delta of -8% does **not** mean the park
underperforms. It can reflect: a sub-average climatic year, real losses
above 14%, marketing rounding in the press release, or a more optimal
real geometry than our defaults. The delta is a starting point for
analysis, not a verdict on performance.

**Severity thresholds.** Green: |Δ| < 5% (aligned). Yellow: 5-10% (within
model uncertainty). Red: ≥ 10% (significant gap, investigate).

**Out of scope (V1).** Wind production (would need windpowerlib + ERA5,
±15% accuracy below PVGIS standard). Battery storage (no public
"production" notion for storage). Real-time / day-of measurements
(operational data, private).

**Data sourcing.** Park list curated from Allianz Capital Partners press
archive, operator partner publications (WElink, Grenergy, Avantus, Elgin,
IBC Solar, BayWa), and trade press (PV-Tech, Renewables Now, GEM Wiki),
cross-checked via Gemini deep research run on 2026-04-30.
"""
    )
