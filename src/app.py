"""Allianz Renewables Atlas — single-page entry point.

Globe Earth from space (globe.gl + NASA Blue Marble) avec click natif
sur les markers via custom Streamlit component → panel détail direct.
Vue satellite Esri + PVGIS year-2023 actual hourly data.
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

import yaml

from src.components.globe_picker import globe_picker
from src.lib.electricity_prices import (
    compute_revenue_metrics,
    fetch_current_spot_price,
    fetch_hourly_prices,
    get_zone,
)
from src.lib.live_weather import estimate_current_output_mw, fetch_current_weather
from src.lib.parks_loader import load_parks_index
from src.lib.pvgis_fetch import DEFAULT_REPRESENTATIVE_YEAR, fetch_pvgis_hourly
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

SEVERITY_LABELS = {
    "green": "ALIGNED",
    "yellow": "MONITOR",
    "red": "INVESTIGATE",
    "none": "N/A",
}

MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
DATA_YEAR = DEFAULT_REPRESENTATIVE_YEAR  # 2020, latest stable in PVGIS-SARAH2

COORD_OVERRIDES_PATH = _ROOT / "data" / "coord_overrides.yaml"


def _load_coord_overrides() -> dict[str, list[float]]:
    """Load user-curated coord overrides (set via dblclick on satellite view)."""
    if not COORD_OVERRIDES_PATH.exists():
        return {}
    with open(COORD_OVERRIDES_PATH) as f:
        return yaml.safe_load(f) or {}


def _save_coord_override(park_id: str, lat: float, lon: float) -> None:
    overrides = _load_coord_overrides()
    overrides[park_id] = [round(float(lat), 6), round(float(lon), 6)]
    with open(COORD_OVERRIDES_PATH, "w") as f:
        yaml.safe_dump(overrides, f, default_flow_style=False, sort_keys=True)


# ---------------------------------------------------------------------------
# Data loaders (cached)
# ---------------------------------------------------------------------------


@st.cache_data
def _load_parks_df() -> pd.DataFrame:
    idx = load_parks_index()
    overrides = _load_coord_overrides()
    rows = []
    for p in idx.parks:
        lat, lon = p.lat, p.lon
        if p.id in overrides:
            lat, lon = overrides[p.id]
        rows.append(
            {
                "id": p.id,
                "name": p.name,
                "country": p.country,
                "lat": lat,
                "lon": lon,
                "capacity_mwp": p.capacity_mwp or 0.0,
                "commissioning_year": p.commissioning_year,
                "operator": p.operator or "—",
                "press_release_url": p.press_release_url,
                "coord_overridden": p.id in overrides,
            }
        )
    return pd.DataFrame(rows)


@st.cache_data
def _load_reported() -> dict[str, dict]:
    rep = load_reported_production()
    return {pid: r.model_dump(mode="json") for pid, r in rep.items()}


@st.cache_data(ttl=86400, show_spinner=False)
def _fetch_hourly_cached(park_id: str, lat: float, lon: float, peakpower_mw: float) -> dict:
    return fetch_pvgis_hourly(lat=lat, lon=lon, peakpower_mw=peakpower_mw)


@st.cache_data(ttl=86400, show_spinner=False)
def _fetch_prices_cached(zone: str, year: int) -> list[float] | None:
    return fetch_hourly_prices(zone, year)


@st.cache_data(ttl=900, show_spinner=False)  # 15 min refresh
def _fetch_live_weather_cached(lat: float, lon: float) -> dict | None:
    return fetch_current_weather(lat, lon)


@st.cache_data(ttl=1800, show_spinner=False)  # 30 min refresh
def _fetch_live_spot_cached(zone: str) -> dict | None:
    return fetch_current_spot_price(zone)


# ---------------------------------------------------------------------------
# Satellite view HTML (read-only) — Leaflet + Esri World Imagery
# ---------------------------------------------------------------------------


def _build_satellite_html(lat: float, lon: float, label: str) -> str:
    label_safe = label.replace("'", "&#39;").replace('"', "&quot;")
    return f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<style>
  html, body {{ margin: 0; padding: 0; height: 100%; background: #000; }}
  #map {{ width: 100%; height: 100%; border-radius: 10px; }}
  .leaflet-control-attribution {{
    font-size: 9px !important; opacity: 0.55;
    background: rgba(0, 0, 0, 0.85) !important;
    color: #a8a294 !important;
  }}
  .leaflet-control-attribution a {{ color: #e8e4d6 !important; }}
  .leaflet-control-zoom a {{
    background: rgba(13, 13, 13, 0.92) !important;
    color: #e8e4d6 !important;
    border: 1px solid rgba(232, 228, 214, 0.18) !important;
    font-family: 'JetBrains Mono', monospace !important;
  }}
  .leaflet-control-zoom a:hover {{ background: rgba(20, 20, 20, 1) !important; }}
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
  L.circleMarker([{lat}, {lon}], {{
    radius: 14, color: '#e8e4d6', weight: 2,
    fillColor: '#e8e4d6', fillOpacity: 0.12,
  }}).addTo(map).bindPopup('{label_safe}');
  L.circleMarker([{lat}, {lon}], {{
    radius: 5, color: '#e8e4d6', weight: 2,
    fillColor: '#e8e4d6', fillOpacity: 0.95,
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

st.markdown("<br>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Globe — custom component with click events
# ---------------------------------------------------------------------------

globe_parks = [
    {
        "id": row["id"],
        "name": row["name"],
        "country": row["country"],
        "cap": float(row["capacity_mwp"]),
        "lat": float(row["lat"]),
        "lng": float(row["lon"]),
    }
    for _, row in parks_df.iterrows()
]

clicked_park_id = globe_picker(parks=globe_parks, height=620, key="atlas-globe")

# Persist selection across reruns
if clicked_park_id:
    st.session_state["selected_park_id"] = clicked_park_id

selected_park_id = st.session_state.get("selected_park_id")

if not selected_park_id:
    st.markdown(
        """
        <div class="empty-hint">
          <span class="empty-prompt">▸</span> Click a marker on the globe to open
          satellite imagery and PVGIS analysis.
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.stop()

selected_row = parks_df[parks_df["id"] == selected_park_id]
if selected_row.empty:
    st.session_state.pop("selected_park_id", None)
    st.rerun()
selected_row = selected_row.iloc[0]

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
# Satellite view
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# LIVE STATUS — current weather + estimated output + current spot price
# ---------------------------------------------------------------------------

st.markdown(
    '<div style="font-family: \'JetBrains Mono\', monospace; '
    'font-size: 0.65rem; letter-spacing: 0.16em; text-transform: uppercase; '
    'color: #7a7464; margin: 8px 0 12px;">Live · right now</div>',
    unsafe_allow_html=True,
)

live_weather = _fetch_live_weather_cached(
    float(selected_row["lat"]), float(selected_row["lon"])
)
live_zone = get_zone(selected_row["country"], park_id=selected_park_id)
live_spot = _fetch_live_spot_cached(live_zone) if live_zone else None

l1, l2, l3, l4, l5 = st.columns(5)

if live_weather:
    cloud = live_weather["cloud_cover_pct"]
    cloud_label = "clear" if cloud < 25 else ("partly" if cloud < 75 else "overcast")
    l1.metric(
        "Sun exposure",
        f"{live_weather['ghi_w_m2']:,.0f} W/m²",
        delta=cloud_label,
        delta_color="off",
        help=f"Global Horizontal Irradiance from Open-Meteo · cloud cover {cloud:.0f}% · refreshed every 15 min",
    )
    l2.metric(
        "Air temperature",
        f"{live_weather['temp_c']:.1f} °C",
        help=f"Sampled at the park coordinates · {live_weather['time_iso']}",
    )

    estimated_mw = estimate_current_output_mw(
        capacity_mwp=float(selected_row["capacity_mwp"]),
        ghi_w_m2=live_weather["ghi_w_m2"],
        temp_c=live_weather["temp_c"],
    )
    cf_now = (estimated_mw / float(selected_row["capacity_mwp"]) * 100.0) if selected_row["capacity_mwp"] else 0.0
    l3.metric(
        "Estimated output",
        f"{estimated_mw:,.1f} MW",
        delta=f"{cf_now:.0f}% of capacity",
        delta_color="off",
        help=(
            "Live estimate from public data only. "
            "Formula: capacity × (GHI/1000) × (1 − loss%) × temperature_derating. "
            "Accuracy ±15% vs operator's metered output."
        ),
    )
else:
    l1.metric("Sun exposure", "—")
    l2.metric("Air temperature", "—")
    l3.metric("Estimated output", "—")

if live_spot and live_spot.get("price_eur_mwh") is not None:
    spot_price = live_spot["price_eur_mwh"]
    l4.metric(
        "Spot price now",
        f"{spot_price:,.1f} €/MWh",
        help=f"Day-ahead zone {live_zone} · {live_spot['time_iso'][:16]} UTC · source energy-charts.info",
    )

    if live_weather:
        revenue_now = estimated_mw * spot_price  # €/h (MW × €/MWh × 1h)
        l5.metric(
            "Revenue (this hour)",
            f"€ {revenue_now:,.0f}",
            help="Estimated output × current spot price × 1 hour. Indicative only.",
        )
    else:
        l5.metric("Revenue (this hour)", "—")
else:
    l4.metric("Spot price now", "—", help=f"Zone {live_zone or '—'} not available right now.")
    l5.metric("Revenue (this hour)", "—")

st.markdown('<div class="vspace"></div>', unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Satellite view (read-only)
# ---------------------------------------------------------------------------

components.html(
    _build_satellite_html(
        lat=float(selected_row["lat"]),
        lon=float(selected_row["lon"]),
        label=selected_row["name"],
    ),
    height=360,
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
monthly = monthly_aggregates(hourly_data["hourly_production_kwh"], year=DATA_YEAR)

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
    help=f"Climatological estimate for the calendar day {today_est['date'][5:]}, derived from PVGIS year {DATA_YEAR}.",
)
m2.metric(
    f"Annual output ({DATA_YEAR})",
    f"{annual_mwh:,.0f} MWh",
    help=f"PVGIS year-{DATA_YEAR} actual hourly data, 14% system losses.",
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

# ----- Revenue metrics (electricity day-ahead price × hourly production) -----
zone = get_zone(selected_row["country"], park_id=selected_park_id)
revenue_metrics: dict = {}
if zone:
    prices = _fetch_prices_cached(zone, DATA_YEAR)
    if prices:
        revenue_metrics = compute_revenue_metrics(
            hourly_production_kwh=hourly_data["hourly_production_kwh"],
            hourly_prices_eur_mwh=prices,
        )

st.markdown('<div class="vspace"></div>', unsafe_allow_html=True)
r1, r2, r3, r4 = st.columns(4)

if revenue_metrics:
    r1.metric(
        f"Revenue ({DATA_YEAR})",
        f"€ {revenue_metrics['annual_revenue_eur'] / 1_000_000:,.2f} M",
        help=f"Hourly production × day-ahead price (zone {zone}). Source: energy-charts.info / ENTSO-E.",
    )
    r2.metric(
        "Effective sale price",
        f"{revenue_metrics['effective_price_eur_mwh']:,.1f} €/MWh",
        help="Production-weighted average price actually realised.",
    )
    r3.metric(
        "Day-ahead avg price",
        f"{revenue_metrics['avg_dayahead_price_eur_mwh']:,.1f} €/MWh",
        help=f"Simple time-average of zone {zone} hourly prices in {DATA_YEAR}.",
    )
    r4.metric(
        "Solar cannibalisation",
        f"{revenue_metrics['cannibalization_pct']:+.1f} %",
        help="(Effective − Day-ahead avg) / Day-ahead avg. Negative = solar produces more during low-price hours (typical).",
    )
else:
    r1.metric(f"Revenue ({DATA_YEAR})", "—", help=f"Zone {zone or '—'} not available on energy-charts.info.")
    r2.metric("Effective sale price", "—")
    r3.metric("Day-ahead avg price", "—")
    r4.metric("Solar cannibalisation", "—")

# Source caption
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
# Daily output chart — single fluid line, dated year DATA_YEAR
# ---------------------------------------------------------------------------

daily_kwh = hourly_to_daily(hourly_data["hourly_production_kwh"])
daily_mwh = [v / 1000.0 for v in daily_kwh]
day_dates = pd.date_range(f"{DATA_YEAR}-01-01", periods=365, freq="D")

# Light 7-day smoothing for a clean curve (replaces the dual-line previous version)
import numpy as np
arr = np.asarray(daily_mwh)
window = 5
smooth = np.convolve(arr, np.ones(window) / window, mode="same")

fig_daily = go.Figure()
fig_daily.add_trace(
    go.Scatter(
        x=day_dates,
        y=smooth,
        mode="lines",
        line=dict(color="#e8e4d6", width=2.2, shape="spline", smoothing=0.5),
        fill="tozeroy",
        fillcolor="rgba(232, 228, 214, 0.10)",
        hovertemplate="%{x|%d %b %Y} · %{y:,.1f} MWh<extra></extra>",
        name="Daily output",
    )
)

fig_daily.update_layout(
    title=dict(
        text=f"Daily output · year {DATA_YEAR}",
        font=dict(color="#f1f5f9", size=14, family="Geist", weight=500),
        x=0.0, xanchor="left", pad=dict(b=8),
    ),
    height=240,
    margin=dict(l=0, r=0, t=44, b=10),
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    xaxis=dict(
        showgrid=False,
        tickfont=dict(color="#64748b", size=10, family="JetBrains Mono"),
        tickformat="%b %Y",
        dtick="M2",
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
        bordercolor="rgba(232, 228, 214, 0.4)",
        font=dict(color="#f1f5f9", family="JetBrains Mono", size=11),
    ),
)

st.plotly_chart(fig_daily, width="stretch", config={"displayModeBar": False})

# ---------------------------------------------------------------------------
# Monthly bar chart
# ---------------------------------------------------------------------------

st.markdown('<div class="vspace"></div>', unsafe_allow_html=True)

monthly_mwh = [m["production_mwh"] for m in monthly]
fig_monthly = go.Figure()
fig_monthly.add_trace(
    go.Bar(
        x=MONTH_NAMES,
        y=monthly_mwh,
        marker=dict(
            color="rgba(232, 228, 214, 0.78)",
            line=dict(color="rgba(232, 228, 214, 0.95)", width=0.8),
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
        text=f"Monthly production · year {DATA_YEAR}",
        font=dict(color="#f1f5f9", size=14, family="Geist", weight=500),
        x=0.0, xanchor="left", pad=dict(b=8),
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
        bordercolor="rgba(232, 228, 214, 0.4)",
        font=dict(color="#f1f5f9", family="JetBrains Mono", size=11),
    ),
)

st.plotly_chart(fig_monthly, width="stretch", config={"displayModeBar": False})

# ---------------------------------------------------------------------------
# Reset button
# ---------------------------------------------------------------------------

st.markdown('<div class="vspace"></div>', unsafe_allow_html=True)
if st.button("← Back to globe", type="secondary"):
    st.session_state.pop("selected_park_id", None)
    st.rerun()

# ---------------------------------------------------------------------------
# About this data
# ---------------------------------------------------------------------------

with st.expander("About the methodology", expanded=False):
    st.markdown(
        f"""
**Source.** PVGIS v5.2 (Joint Research Centre, European Commission) —
the reference tool for European solar production estimates. Free, no API key.
<https://re.jrc.ec.europa.eu/pvg_tools/en/>

**Year used.** {DATA_YEAR} actual hourly data from the PVGIS SARAH-3 satellite
radiation database (latest full year published). PVGIS reconstructs hour-by-hour
solar production based on Meteosat satellite imagery + a panel model.

**Default assumptions.** System losses 14% (inverter, cabling, soiling
baseline). Mounting fixed, azimuth 0° south, tilt = lat. crystSi modules.

**Reading the delta.** A delta of -8% does **not** mean the park
underperforms. It can reflect: actual losses above 14%, marketing rounding
in the press release, geometry differences vs our defaults, or panel
degradation since commissioning.

**Severity thresholds.** Green: |Δ| < 5% (aligned). Yellow: 5-10% (within
model uncertainty). Red: ≥ 10% (significant gap, investigate).

**Out of scope.** Wind production. Battery storage. Real-time / day-of measurements.

**Data sourcing.** Park list curated from Allianz Capital Partners press
archive, operator partner publications, and trade press, cross-checked via
Global Energy Monitor (GEM Wiki) for exact GPS coordinates. Satellite imagery:
Esri World Imagery (Maxar, Earthstar Geographics).
"""
    )
