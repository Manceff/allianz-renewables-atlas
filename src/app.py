"""Allianz Renewables Atlas — single-page entry point.

Vraie photo Earth depuis l'espace (globe.gl + NASA Blue Marble) en iframe,
sélection par dropdown, panel avec vue satellite Esri zoom et analyse PVGIS.

Style : sober, sans emoji, design analyste private equity.
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
import streamlit.components.v1 as components

from src.lib.parks_loader import load_parks_index
from src.lib.pvgis_fetch import fetch_pvgis_hourly
from src.lib.reported_production import load_reported_production
from src.lib.solar_metrics import (
    capacity_factor_annual,
    estimate_for_date,
    hourly_to_daily,
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
def _load_reported() -> dict[str, dict]:
    rep = load_reported_production()
    return {pid: r.model_dump(mode="json") for pid, r in rep.items()}


@st.cache_data(ttl=86400, show_spinner=False)
def _fetch_hourly_cached(park_id: str, lat: float, lon: float, peakpower_mw: float) -> dict:
    return fetch_pvgis_hourly(lat=lat, lon=lon, peakpower_mw=peakpower_mw)


# ---------------------------------------------------------------------------
# Globe.gl HTML — real NASA Blue Marble texture, atmospheric glow, auto-rotate
# ---------------------------------------------------------------------------


def _build_globe_html(parks: pd.DataFrame, height: int = 600) -> str:
    """Renvoie le HTML autonome du globe Three.js avec textures NASA."""
    points = [
        {
            "name": row["name"],
            "country": row["country"],
            "cap": float(row["capacity_mwp"]),
            "lat": float(row["lat"]),
            "lng": float(row["lon"]),
        }
        for _, row in parks.iterrows()
    ]
    points_json = json.dumps(points)
    return f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<style>
  html, body {{ margin: 0; padding: 0; height: 100%; background: #000; overflow: hidden; }}
  #globeViz {{ width: 100%; height: 100%; cursor: grab; }}
  #globeViz:active {{ cursor: grabbing; }}
  .label-card {{
    background: rgba(15, 23, 42, 0.95);
    backdrop-filter: blur(8px);
    color: #f1f5f9;
    padding: 8px 12px;
    border-radius: 6px;
    border: 1px solid rgba(125, 211, 252, 0.4);
    font-family: -apple-system, "Inter", system-ui, sans-serif;
    font-size: 12px;
    letter-spacing: 0.01em;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.5);
    pointer-events: none;
    white-space: nowrap;
  }}
  .label-card .lbl-name {{ font-weight: 600; color: #f1f5f9; margin-bottom: 2px; }}
  .label-card .lbl-meta {{ color: #94a3b8; font-size: 11px; }}
</style>
</head>
<body>
<div id="globeViz"></div>
<script src="https://unpkg.com/three@0.149.0/build/three.min.js"></script>
<script src="https://unpkg.com/globe.gl@2.27.4/dist/globe.gl.min.js"></script>
<script>
  const POINTS = {points_json};
  const elem = document.getElementById('globeViz');

  const globe = Globe()
    .globeImageUrl('https://unpkg.com/three-globe/example/img/earth-blue-marble.jpg')
    .bumpImageUrl('https://unpkg.com/three-globe/example/img/earth-topology.png')
    .backgroundImageUrl('https://unpkg.com/three-globe/example/img/night-sky.png')
    .atmosphereColor('#fbbf24')                // single accent — warm amber, solar resonance
    .atmosphereAltitude(0.20)
    .pointsData(POINTS)
    .pointLat('lat')
    .pointLng('lng')
    .pointColor(() => '#fbbf24')
    .pointAltitude(0.014)
    .pointRadius(0.38)
    .pointLabel(d => `
      <div class="label-card">
        <div class="lbl-name">${{d.name}}</div>
        <div class="lbl-meta">${{d.country}} · ${{d.cap.toFixed(1)}} MWp</div>
      </div>
    `)
    .pointsMerge(true)
    .ringsData(POINTS)
    .ringLat('lat')
    .ringLng('lng')
    .ringColor(() => 'rgba(251, 191, 36, 0.55)')
    .ringMaxRadius(2.0)
    .ringPropagationSpeed(0.7)
    .ringRepeatPeriod(2200)
    .ringAltitude(0.003);

  globe(elem);

  // Initial framing — Europe-centric
  globe.pointOfView({{ lat: 38, lng: 4, altitude: 2.4 }}, 0);

  // Smooth auto-rotation
  globe.controls().autoRotate = true;
  globe.controls().autoRotateSpeed = 0.35;
  globe.controls().enableZoom = true;
  globe.controls().minDistance = 200;
  globe.controls().maxDistance = 800;

  // Resize handling
  function fit() {{
    globe.width(elem.clientWidth);
    globe.height(elem.clientHeight);
  }}
  fit();
  window.addEventListener('resize', fit);
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Satellite view HTML — Leaflet + Esri World Imagery (free, no auth)
# ---------------------------------------------------------------------------


def _build_satellite_html(lat: float, lon: float, label: str, height: int = 280) -> str:
    """Vue satellite zoomée sur la zone du parc, via Esri World Imagery (gratuit)."""
    label_safe = label.replace("'", "&#39;").replace('"', "&quot;")
    return f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<style>
  html, body {{ margin: 0; padding: 0; height: 100%; background: #050810; }}
  #map {{ width: 100%; height: 100%; border-radius: 10px; }}
  .leaflet-control-attribution {{
    font-size: 9px !important; opacity: 0.55;
    background: rgba(5, 8, 16, 0.85) !important;
    color: #94a3b8 !important;
  }}
  .leaflet-control-attribution a {{ color: #fbbf24 !important; }}
  .leaflet-control-zoom a {{
    background: rgba(13, 19, 32, 0.92) !important;
    color: #cbd5e1 !important;
    border: 1px solid rgba(148, 163, 184, 0.18) !important;
    font-family: 'JetBrains Mono', monospace !important;
  }}
  .leaflet-control-zoom a:hover {{
    background: rgba(13, 19, 32, 1) !important;
    color: #fbbf24 !important;
  }}
</style>
</head>
<body>
<div id="map"></div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
  const map = L.map('map', {{ zoomControl: true, attributionControl: true }})
    .setView([{lat}, {lon}], 14);

  L.tileLayer(
    'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}',
    {{ maxZoom: 18, attribution: 'Esri, Maxar, Earthstar Geographics' }}
  ).addTo(map);

  // Outer ring + inner dot — accent amber
  L.circleMarker([{lat}, {lon}], {{
    radius: 14,
    color: '#fbbf24',
    weight: 2,
    fillColor: '#fbbf24',
    fillOpacity: 0.12,
  }}).addTo(map).bindPopup('{label_safe}');
  L.circleMarker([{lat}, {lon}], {{
    radius: 5,
    color: '#fbbf24',
    weight: 2,
    fillColor: '#fbbf24',
    fillOpacity: 0.95,
  }}).addTo(map);
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

st.markdown(
    """
    <div style="text-align: center; padding: 1.2rem 0 0.6rem;">
        <h1 style="margin: 0; font-size: 1.85rem; font-weight: 600; letter-spacing: -0.02em;">
            Allianz Renewables Atlas
        </h1>
        <p style="color: #94a3b8; font-size: 0.85rem; margin-top: 0.35rem; letter-spacing: 0.04em;">
            Solar PV assets owned directly by Allianz Capital Partners · 2010-2026
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

parks_df = _load_parks_df()
reported_map = _load_reported()

# ---------------------------------------------------------------------------
# Top metrics
# ---------------------------------------------------------------------------

c1, c2, c3, c4 = st.columns(4)
c1.metric("Solar parks", f"{len(parks_df)}")
c2.metric("Installed capacity", f"{parks_df['capacity_mwp'].sum():,.0f} MWp")
c3.metric("Countries", f"{parks_df['country'].nunique()}")
c4.metric("With production delta", f"{len(reported_map)} of {len(parks_df)}")

st.markdown('<div class="vspace"></div>', unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Globe — globe.gl iframe with NASA Blue Marble texture
# ---------------------------------------------------------------------------

components.html(_build_globe_html(parks_df), height=600, scrolling=False)

# ---------------------------------------------------------------------------
# Park selector
# ---------------------------------------------------------------------------

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
        <div class="empty-hint">
          <span class="empty-prompt">▸</span> Select a park from the dropdown to open
          satellite imagery and PVGIS analysis.
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.stop()

selected_row = parks_df[parks_df["id"] == selected_park_id].iloc[0]

# ---------------------------------------------------------------------------
# Park header
# ---------------------------------------------------------------------------

st.markdown(
    f"""
    <div class="park-header">
      <div class="park-title">{selected_row['name']}</div>
      <div class="park-stats">
        <div class="stat">
          <div class="stat-label">Country</div>
          <div class="stat-value">{selected_row['country']}</div>
        </div>
        <div class="stat">
          <div class="stat-label">Capacity</div>
          <div class="stat-value">{selected_row['capacity_mwp']:,.1f} <span class="stat-unit">MWp</span></div>
        </div>
        <div class="stat">
          <div class="stat-label">Commissioned</div>
          <div class="stat-value">{selected_row['commissioning_year']}</div>
        </div>
        <div class="stat stat-wide">
          <div class="stat-label">Operator</div>
          <div class="stat-value stat-operator">{selected_row['operator']}</div>
        </div>
        <div class="stat stat-source">
          <div class="stat-label">Source</div>
          <div class="stat-value"><a href="{selected_row['press_release_url']}" target="_blank">press release ↗</a></div>
        </div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Satellite view (top of the panel — wow effect)
# ---------------------------------------------------------------------------

components.html(
    _build_satellite_html(
        lat=float(selected_row["lat"]),
        lon=float(selected_row["lon"]),
        label=selected_row["name"],
    ),
    height=320,
    scrolling=False,
)

# ---------------------------------------------------------------------------
# Detail panel — fetch PVGIS and render
# ---------------------------------------------------------------------------

with st.spinner("Querying PVGIS…"):
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
# 4 KPI metrics
# ---------------------------------------------------------------------------

st.markdown('<div class="vspace"></div>', unsafe_allow_html=True)
m1, m2, m3, m4 = st.columns(4)

m1.metric(
    "Today's typical output",
    f"{today_est['production_kwh'] / 1000:,.1f} MWh",
    help=f"Climatological estimate for {today_est['date']}, based on TMY 2019.",
)
m2.metric(
    "Annual estimate",
    f"{annual_mwh:,.0f} MWh",
    help="PVGIS annual production with 14% system losses.",
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

# Source caption — explicit traceability for the reported figure
if reported:
    src_url = reported.get("source_url", "")
    src_year = reported.get("year", "—")
    src_note = reported.get("note", "")
    st.markdown(
        f"""
        <div class="source-caption">
          <span class="src-label">Reported source</span>
          {float(reported['annual_mwh']):,.0f} MWh · {src_year} ·
          <a href="{src_url}" target="_blank">{src_url[:80]}{'…' if len(src_url) > 80 else ''}</a>
          <div class="src-note">{src_note}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
else:
    st.markdown(
        """
        <div class="source-caption">
          <span class="src-label">Reported source</span>
          No public production figure identified for this park — delta cannot be computed.
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown('<div class="vspace-lg"></div>', unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Single chart — monthly seasonality
# ---------------------------------------------------------------------------

monthly_mwh = [m["production_mwh"] for m in monthly]
daily_kwh = hourly_to_daily(hourly_data["hourly_production_kwh"])
daily_mwh = [v / 1000.0 for v in daily_kwh]
day_dates = pd.date_range("2019-01-01", periods=365, freq="D")

# ----- Daily seasonality chart (smooth, fluid, premium) -------------
fig_daily = go.Figure()
fig_daily.add_trace(
    go.Scatter(
        x=day_dates,
        y=daily_mwh,
        mode="lines",
        line=dict(color="#fbbf24", width=1.4, shape="spline", smoothing=0.6),
        fill="tozeroy",
        fillcolor="rgba(251, 191, 36, 0.10)",
        hovertemplate="%{x|%d %b} · %{y:,.1f} MWh<extra></extra>",
        name="Daily output",
    )
)

# 7-day rolling mean — slightly emphasized
import numpy as np
arr = np.asarray(daily_mwh)
window = 7
rolling = np.convolve(arr, np.ones(window) / window, mode="same")
fig_daily.add_trace(
    go.Scatter(
        x=day_dates,
        y=rolling,
        mode="lines",
        line=dict(color="rgba(251, 191, 36, 0.9)", width=2.4, shape="spline", smoothing=0.4),
        hoverinfo="skip",
        name="7-day rolling mean",
    )
)

fig_daily.update_layout(
    title=dict(
        text="Daily output across the climatic year",
        font=dict(color="#f1f5f9", size=14, family="Geist", weight=500),
        x=0.0,
        xanchor="left",
        pad=dict(b=8),
    ),
    height=240,
    margin=dict(l=0, r=0, t=44, b=10),
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    xaxis=dict(
        showgrid=False,
        tickfont=dict(color="#64748b", size=10, family="JetBrains Mono"),
        tickformat="%b",
        dtick="M1",
    ),
    yaxis=dict(
        gridcolor="rgba(148, 163, 184, 0.06)",
        tickfont=dict(color="#64748b", size=10, family="JetBrains Mono"),
        title=None,
        ticksuffix=" MWh",
    ),
    showlegend=False,
    hoverlabel=dict(
        bgcolor="rgba(13, 19, 32, 0.95)",
        bordercolor="rgba(251, 191, 36, 0.4)",
        font=dict(color="#f1f5f9", family="JetBrains Mono", size=11),
    ),
)

st.plotly_chart(fig_daily, width="stretch", config={"displayModeBar": False})

# ----- Monthly bar chart (kept as macro view) ------------------------
st.markdown('<div class="vspace"></div>', unsafe_allow_html=True)

fig_monthly = go.Figure()
fig_monthly.add_trace(
    go.Bar(
        x=MONTH_NAMES,
        y=monthly_mwh,
        marker=dict(
            color="rgba(251, 191, 36, 0.78)",
            line=dict(color="rgba(251, 191, 36, 0.95)", width=0.8),
        ),
        hovertemplate="%{x} · %{y:,.0f} MWh<extra></extra>",
        name="Estimated",
    )
)

if reported:
    avg_monthly_reported = float(reported["annual_mwh"]) / 12.0
    fig_monthly.add_hline(
        y=avg_monthly_reported,
        line_dash="dot",
        line_color="rgba(248, 250, 252, 0.5)",
        line_width=1.2,
        annotation_text=f"Reported / 12 · {avg_monthly_reported:,.0f}",
        annotation_position="top right",
        annotation_yshift=2,
        annotation_font=dict(color="#cbd5e1", size=10, family="JetBrains Mono"),
    )

fig_monthly.update_layout(
    title=dict(
        text="Monthly production estimate (MWh)",
        font=dict(color="#f1f5f9", size=14, family="Geist", weight=500),
        x=0.0,
        xanchor="left",
        pad=dict(b=8),
    ),
    height=260,
    margin=dict(l=0, r=0, t=44, b=0),
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    xaxis=dict(
        showgrid=False,
        tickfont=dict(color="#64748b", size=10, family="JetBrains Mono"),
    ),
    yaxis=dict(
        gridcolor="rgba(148, 163, 184, 0.06)",
        tickfont=dict(color="#64748b", size=10, family="JetBrains Mono"),
        title=None,
    ),
    showlegend=False,
    hoverlabel=dict(
        bgcolor="rgba(13, 19, 32, 0.95)",
        bordercolor="rgba(251, 191, 36, 0.4)",
        font=dict(color="#f1f5f9", family="JetBrains Mono", size=11),
    ),
)

st.plotly_chart(fig_monthly, width="stretch", config={"displayModeBar": False})

# ---------------------------------------------------------------------------
# About this data
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
baseline). Mounting fixed, azimuth 0° south, tilt = lat. crystSi modules.

**Reading the delta.** A delta of -8% does **not** mean the park
underperforms. It can reflect: a sub-average climatic year, real losses
above 14%, marketing rounding in the press release, or a more optimal
real geometry than our defaults.

**Severity thresholds.** Green: |Δ| < 5% (aligned). Yellow: 5-10% (within
model uncertainty). Red: ≥ 10% (significant gap, investigate).

**Out of scope.** Wind production. Battery storage. Real-time / day-of measurements.

**Data sourcing.** Park list curated from Allianz Capital Partners press
archive, operator partner publications, and trade press, cross-checked via
deep research run on 2026-04-30. Satellite imagery: Esri World Imagery
(Maxar, Earthstar Geographics).
"""
    )
