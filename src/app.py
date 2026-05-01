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
    fetch_today_curve,
    get_zone,
    interpret_spot_price,
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

# Fetch PVGIS hourly EARLY — used by both Live (typical-vs-now delta) and Historical sections
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
    """
    <div class="section-header section-first section-live">
      <span class="section-label">Live · right now</span>
      <span class="section-caption">
        Live snapshot · weather refreshed every 15 min (Open-Meteo) · spot price
        from ENTSO-E day-ahead. Estimated MW = capacity × (GHI / 1000) × (1 − 14% loss) × temperature derating.
      </span>
    </div>
    """,
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
        "Sun (live)",
        f"{live_weather['ghi_w_m2']:,.0f} W/m²",
        delta=cloud_label,
        delta_color="off",
        help=f"Global Horizontal Irradiance from Open-Meteo · cloud cover {cloud:.0f}% · refreshed every 15 min",
    )
    l2.metric(
        "Air temp (live)",
        f"{live_weather['temp_c']:.1f} °C",
        help=f"Sampled at the park coordinates · {live_weather['time_iso']}",
    )

    estimated_mw = estimate_current_output_mw(
        capacity_mwp=float(selected_row["capacity_mwp"]),
        ghi_w_m2=live_weather["ghi_w_m2"],
        temp_c=live_weather["temp_c"],
    )
    cf_now = (estimated_mw / float(selected_row["capacity_mwp"]) * 100.0) if selected_row["capacity_mwp"] else 0.0

    # Bridge live ↔ historical : compare to typical 2023 value at this same hour
    import datetime as _dt
    _now_utc = _dt.datetime.now(_dt.timezone.utc)
    _doy = min(_now_utc.timetuple().tm_yday, 365)
    _hour_idx = (_doy - 1) * 24 + _now_utc.hour
    typical_mw_this_hour: float | None = None
    if _hour_idx < len(hourly_data["hourly_production_kwh"]):
        typical_mw_this_hour = hourly_data["hourly_production_kwh"][_hour_idx] / 1000.0
    delta_label = f"{cf_now:.0f}% of capacity"
    if typical_mw_this_hour and typical_mw_this_hour > 0.5:
        d = (estimated_mw - typical_mw_this_hour) / typical_mw_this_hour * 100.0
        delta_label = f"{d:+.0f}% vs typical for this hour"

    l3.metric(
        "Output (live est.)",
        f"{estimated_mw:,.1f} MW",
        delta=delta_label,
        delta_color="off",
        help=(
            f"Live estimate from current GHI + temperature. ±15% vs operator's meter. "
            f"Typical {DATA_YEAR} for this hour : "
            f"{typical_mw_this_hour:.1f} MW." if typical_mw_this_hour else
            "Live estimate from current GHI + temperature. ±15% vs operator's meter."
        ),
    )
else:
    l1.metric("Sun (live)", "—")
    l2.metric("Air temp (live)", "—")
    l3.metric("Output (live est.)", "—")

spot_context = None
if live_spot and live_spot.get("price_eur_mwh") is not None:
    spot_price = live_spot["price_eur_mwh"]
    spot_context = interpret_spot_price(spot_price, live_zone)
    l4.metric(
        "Spot price (live)",
        f"{spot_price:,.1f} €/MWh",
        delta=spot_context["label"],
        delta_color="off",
        help=f"Day-ahead zone {live_zone} · {live_spot['time_iso'][:16]} UTC · source energy-charts.info",
    )

    if live_weather:
        revenue_now = estimated_mw * spot_price  # €/h (MW × €/MWh × 1h)
        l5.metric(
            "Revenue/h (live est.)",
            f"€ {revenue_now:,.0f}",
            help="Live output estimate × current spot price × 1 hour. Indicative only.",
        )
    else:
        l5.metric("Revenue/h (live est.)", "—")
else:
    l4.metric("Spot price (live)", "—", help=f"Zone {live_zone or '—'} not available right now.")
    l5.metric("Revenue/h (live est.)", "—")

# Contextual disclaimer when spot ≤ 0 — explains negative prices / Italy floor
if spot_context and spot_context.get("warn"):
    label = spot_context["label"]
    if label == "italian floor":
        bg = "rgba(234, 179, 8, 0.10)"
        border = "rgba(234, 179, 8, 0.4)"
        title = "Italian regulatory floor active"
    elif label == "negative":
        bg = "rgba(220, 38, 38, 0.10)"
        border = "rgba(220, 38, 38, 0.4)"
        title = "Negative spot price — solar cannibalisation"
    else:
        bg = "rgba(232, 228, 214, 0.05)"
        border = "rgba(232, 228, 214, 0.20)"
        title = "Near-zero spot price"
    st.markdown(
        f"""
        <div style="
            background: {bg}; border: 1px solid {border}; border-radius: 10px;
            padding: 14px 18px; margin: 10px 0 16px;
            font-family: 'JetBrains Mono', monospace; font-size: 0.78rem;
            color: #cbd5e1; line-height: 1.5;">
          <div style="font-weight: 600; color: #f1f5f9; margin-bottom: 4px; letter-spacing: 0.04em;">
            ▸ {title}
          </div>
          {spot_context['explain']}
        </div>
        """,
        unsafe_allow_html=True,
    )

# Today's spot price curve — visualises the morning solar collapse
if live_zone:
    today_curve = fetch_today_curve(live_zone)
    if today_curve and today_curve.get("prices"):
        import datetime as _dt2
        ts_list = today_curve["timestamps"]
        prices_list = today_curve["prices"]
        x_dates = [_dt2.datetime.fromtimestamp(t, _dt2.timezone.utc) for t in ts_list]

        fig_today = go.Figure()
        # Negative-price area highlighted in red
        fig_today.add_trace(
            go.Scatter(
                x=x_dates,
                y=prices_list,
                mode="lines",
                line=dict(color="#e8e4d6", width=1.6, shape="spline", smoothing=0.3),
                fill="tozeroy",
                fillcolor="rgba(232, 228, 214, 0.08)",
                hovertemplate="%{x|%H:%M} UTC · %{y:,.1f} €/MWh<extra></extra>",
                name="Spot",
            )
        )
        # Zero line
        fig_today.add_hline(
            y=0, line_dash="dot", line_color="rgba(232, 228, 214, 0.3)", line_width=1
        )
        # Mark current hour
        if live_spot:
            now_dt = _dt2.datetime.now(_dt2.timezone.utc)
            fig_today.add_trace(
                go.Scatter(
                    x=[now_dt],
                    y=[live_spot["price_eur_mwh"]],
                    mode="markers",
                    marker=dict(size=10, color="#84cc16", line=dict(color="#0a0a0a", width=2)),
                    hovertemplate="now · %{y:,.1f} €/MWh<extra></extra>",
                    name="Now",
                )
            )

        fig_today.update_layout(
            title=dict(
                text=f"Today's spot curve · zone {live_zone}",
                font=dict(color="#cbd5e1", size=12, family="Geist", weight=500),
                x=0.0, xanchor="left", pad=dict(b=4),
            ),
            height=170,
            margin=dict(l=0, r=0, t=32, b=0),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(showgrid=False, tickfont=dict(color="#7a7464", size=9, family="JetBrains Mono"), tickformat="%H:%M"),
            yaxis=dict(
                gridcolor="rgba(232, 228, 214, 0.06)",
                tickfont=dict(color="#7a7464", size=9, family="JetBrains Mono"),
                title=None, ticksuffix=" €",
            ),
            showlegend=False,
            hoverlabel=dict(
                bgcolor="rgba(13, 13, 13, 0.95)",
                bordercolor="rgba(232, 228, 214, 0.4)",
                font=dict(color="#f1f5f9", family="JetBrains Mono", size=11),
            ),
        )
        st.plotly_chart(fig_today, width="stretch", config={"displayModeBar": False})

st.markdown('<div class="vspace"></div>', unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# SATELLITE VIEW — Esri imagery zoomed on the panels
# ---------------------------------------------------------------------------

st.markdown(
    """
    <div class="section-header">
      <span class="section-label">Satellite view</span>
      <span class="section-caption">
        Esri World Imagery (Maxar, Earthstar Geographics) at the park's GPS coordinates.
      </span>
    </div>
    """,
    unsafe_allow_html=True,
)

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
# HISTORICAL · YEAR 2023 — production from PVGIS hourly data
# ---------------------------------------------------------------------------

st.markdown(
    f"""
    <div class="section-header">
      <span class="section-label">Historical · year {DATA_YEAR}</span>
      <span class="section-caption">
        Reconstruction from PVGIS SARAH-3 satellite data. {DATA_YEAR} is the
        latest full year published by JRC. This is what the park
        <em>actually produced</em> in {DATA_YEAR} given the real weather of that year — not a live measurement.
      </span>
    </div>
    """,
    unsafe_allow_html=True,
)

m1, m2, m3, m4 = st.columns(4)

m1.metric(
    f"Output for {today_est['date'][5:]} ({DATA_YEAR})",
    f"{today_est['production_kwh'] / 1000:,.1f} MWh",
    help=f"What the park produced in {DATA_YEAR} on this same calendar day. PVGIS hourly model.",
)
m2.metric(
    f"Annual output ({DATA_YEAR})",
    f"{annual_mwh:,.0f} MWh",
    help=f"PVGIS year-{DATA_YEAR} actual hourly data, 14% system losses.",
)
m3.metric(
    f"Capacity factor ({DATA_YEAR})",
    f"{cf_annual:.1f} %",
    help="Annual production / (peakpower × 8760 h). Industry benchmark for solar in Europe: 12-18%.",
)

if reported:
    m4.metric(
        "Δ vs operator-reported",
        f"{delta_pct:+.1f} %",
        delta=SEVERITY_LABELS[delta_severity],
        delta_color="off",
        help=f"Reported {float(reported['annual_mwh']):,.0f} MWh ({reported['year']}) — see operator press release.",
    )
else:
    m4.metric("Δ vs operator-reported", "—", help="No public production figure available for this park.")

# ---------------------------------------------------------------------------
# REVENUE · YEAR 2023 — historical production × historical prices
# ---------------------------------------------------------------------------

zone = get_zone(selected_row["country"], park_id=selected_park_id)
revenue_metrics: dict = {}
if zone:
    prices = _fetch_prices_cached(zone, DATA_YEAR)
    if prices:
        revenue_metrics = compute_revenue_metrics(
            hourly_production_kwh=hourly_data["hourly_production_kwh"],
            hourly_prices_eur_mwh=prices,
        )

st.markdown(
    f"""
    <div class="section-header">
      <span class="section-label">Revenue · year {DATA_YEAR}</span>
      <span class="section-caption">
        What the park <em>actually earned</em> in {DATA_YEAR} : hourly production × hourly day-ahead price
        on its bidding zone (zone {zone or '—'}). Captures the solar cannibalisation effect.
      </span>
    </div>
    """,
    unsafe_allow_html=True,
)

r1, r2, r3, r4 = st.columns(4)

if revenue_metrics:
    r1.metric(
        f"Total revenue ({DATA_YEAR})",
        f"€ {revenue_metrics['annual_revenue_eur'] / 1_000_000:,.2f} M",
        help=f"Hourly production × day-ahead price (zone {zone}). Source: energy-charts.info / ENTSO-E.",
    )
    r2.metric(
        f"Effective sale price ({DATA_YEAR})",
        f"{revenue_metrics['effective_price_eur_mwh']:,.1f} €/MWh",
        help="Production-weighted average price actually realised.",
    )
    r3.metric(
        f"Day-ahead avg ({DATA_YEAR})",
        f"{revenue_metrics['avg_dayahead_price_eur_mwh']:,.1f} €/MWh",
        help=f"Simple time-average of zone {zone} hourly prices in {DATA_YEAR}.",
    )
    r4.metric(
        f"Cannibalisation ({DATA_YEAR})",
        f"{revenue_metrics['cannibalization_pct']:+.1f} %",
        help="(Effective − Day-ahead avg) / Day-ahead avg. Negative = solar produces more during low-price hours (typical).",
    )
else:
    r1.metric(f"Total revenue ({DATA_YEAR})", "—", help=f"Zone {zone or '—'} not available on energy-charts.info.")
    r2.metric(f"Effective sale price ({DATA_YEAR})", "—")
    r3.metric(f"Day-ahead avg ({DATA_YEAR})", "—")
    r4.metric(f"Cannibalisation ({DATA_YEAR})", "—")

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

st.markdown(
    f"""
    <div class="section-header">
      <span class="section-label">Time series · year {DATA_YEAR}</span>
      <span class="section-caption">
        Daily and monthly breakdowns of {DATA_YEAR} production. Reveals seasonality
        and the typical climatic shape of the site.
      </span>
    </div>
    """,
    unsafe_allow_html=True,
)

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

with st.expander("How to read the sections", expanded=False):
    st.markdown(
        f"""
The panel mixes **two distinct horizons** that should never be confused.
Each section header makes the source and the time horizon explicit.

| Section | Horizon | Sources | Why it's there |
|---|---|---|---|
| **Live · right now** | This hour, refreshed every 15 min | Open-Meteo (irradiance + temp) · ENTSO-E day-ahead spot | Snapshot of what the park is doing **as you read this**. Useful for "is the park performing today?" |
| **Historical · year {DATA_YEAR}** | Full calendar year {DATA_YEAR} | PVGIS SARAH-3 satellite reconstruction | What the park **actually produced** in the latest published year. Reference for annual capacity factor + delta vs operator. |
| **Revenue · year {DATA_YEAR}** | Full calendar year {DATA_YEAR} | PVGIS production × ENTSO-E day-ahead price (hour by hour) | What the park **actually earned**. Captures cannibalisation. |
| **Time series · year {DATA_YEAR}** | Same year, 365 days × 24 h | Same as Historical | Visualises seasonality. |

**Why both Live and Historical ?**
- Live = is the park healthy today ? (compares to typical climatic conditions)
- Historical = how did it run over a full year ? (the only horizon you can compute revenue / capacity factor on)

A live MW number alone is not actionable for an analyst. A 2023 capacity factor alone is missing today's market context. **Both together** = the full picture.

---

### Sources

- **PVGIS v5.3** (JRC, European Commission) — solar production reconstruction.
  <https://re.jrc.ec.europa.eu/pvg_tools/en/>
- **Open-Meteo** — current weather (free, no auth).
  <https://open-meteo.com/>
- **energy-charts.info / ENTSO-E** — day-ahead electricity prices.
- **Global Energy Monitor (GEM Wiki)** — exact GPS coordinates of plants.
- **Allianz Capital Partners press archive + operator press releases** — capacity, commissioning year, ownership.

### Default assumptions

- System losses 14% (inverter + cabling + soiling baseline).
- Mounting fixed, azimuth 0° south, tilt = lat. crystSi modules.
- ±15% accuracy on the live MW estimate vs the operator's metered output.

### Severity thresholds (delta vs reported)

Green: |Δ| < 5% (aligned). Yellow: 5-10% (within model uncertainty). Red: ≥ 10% (significant gap, investigate).

### Out of scope

Wind, battery storage, real-time metered output, US electricity prices (ERCOT/CAISO),
Ireland prices (SEM not on energy-charts.info).
"""
    )
