"""Allianz Renewables Atlas — single-page entry point.

Globe Earth from space (globe.gl + NASA Blue Marble) avec click natif
sur les markers via custom Streamlit component → panel détail direct.
Vue satellite Esri + PVGIS year-2023 actual hourly data.
"""

from __future__ import annotations

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
from src.lib.backtest import (
    backtest_recent_period,
    get_recent_window,
)
from src.lib.electricity_prices import (
    compute_revenue_metrics,
    fetch_current_spot_price,
    fetch_hourly_prices,
    fetch_period_prices,
    fetch_today_curve,
    get_fallback_price,
    get_zone,
    interpret_spot_price,
)
from src.lib.live_weather import fetch_current_weather
from src.lib.parks_loader import load_parks_index
from src.lib.reported_production import load_reported_production
from src.lib.solar_model import compute_hourly_production, estimate_instant_output_mw
from src.lib.solar_metrics import (
    capacity_factor_annual,
    hourly_to_daily,
    monthly_aggregates_from_timestamps,
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
ARCHIVE_LAG_DAYS = 6           # Open-Meteo Archive publishes with ~5-day lag, +1 safety
T12M_DAYS = 365

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
def _fetch_hourly_cached(park_id: str, lat: float, lon: float, peakpower_mw: float, year: int) -> dict | None:
    """pvlib + Open-Meteo Archive — covers 2023, 2024, 2025 uniformly. PVGIS-grade."""
    return compute_hourly_production(
        park_id=park_id, lat=lat, lon=lon, capacity_mwp=peakpower_mw, year=year,
    )


@st.cache_data(ttl=86400, show_spinner=False)
def _fetch_prices_cached(zone: str, year: int) -> list[float] | None:
    return fetch_hourly_prices(zone, year)


@st.cache_data(ttl=900, show_spinner=False)  # 15 min refresh
def _fetch_live_weather_cached(lat: float, lon: float) -> dict | None:
    return fetch_current_weather(lat, lon)


@st.cache_data(ttl=1800, show_spinner=False)  # 30 min refresh
def _fetch_live_spot_cached(zone: str) -> dict | None:
    return fetch_current_spot_price(zone)


@st.cache_data(ttl=86400, show_spinner=False)  # daily refresh — recent window changes once per day
def _backtest_recent_cached(park_id: str, lat: float, lon: float, capacity: float, zone: str | None, days: int) -> dict | None:
    start, end = get_recent_window(days=days, end_offset_days=5)
    return backtest_recent_period(lat=lat, lon=lon, capacity_mwp=capacity, zone=zone, start=start, end=end)


@st.cache_data(ttl=86400, show_spinner=False)
def _backtest_baseline_cached(
    park_id: str, hourly_kwh_tuple: tuple, baseline_year: int, zone: str | None, days: int
) -> dict | None:
    from src.lib.backtest import backtest_baseline_period
    start, end = get_recent_window(days=days, end_offset_days=5)
    return backtest_baseline_period(
        list(hourly_kwh_tuple), baseline_year=baseline_year, zone=zone, start=start, end=end
    )


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

c1, c2, c3 = st.columns(3)
c1.metric(
    "Total parks tracked",
    f"{len(parks_df)}",
    help="Solar PV assets owned directly by Allianz Capital Partners with public press releases.",
)
c2.metric(
    "Combined nameplate capacity",
    f"{parks_df['capacity_mwp'].sum():,.0f} MWp",
    help="Sum of peak DC capacity across all parks. Each park's capacity is sourced from its acquisition press release.",
)
c3.metric(
    "Countries",
    f"{parks_df['country'].nunique()}",
    help=", ".join(sorted(parks_df["country"].unique())),
)

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
          satellite imagery and pvlib production analysis.
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

# T12M rolling window — last 12 months of available data
import datetime as _dt_mod
_today = _dt_mod.date.today()
T12M_END = _today - _dt_mod.timedelta(days=ARCHIVE_LAG_DAYS)
T12M_START = T12M_END - _dt_mod.timedelta(days=T12M_DAYS - 1)

# Same window 1 year before for year-on-year comparison
T12M_END_PREV = T12M_END - _dt_mod.timedelta(days=365)
T12M_START_PREV = T12M_START - _dt_mod.timedelta(days=365)

# Compute production over T12M and the previous T12M
from src.lib.solar_model import compute_period_production

@st.cache_data(ttl=86400, show_spinner=False)
def _compute_t12m_cached(park_id, lat, lon, capacity, start_iso, end_iso):
    return compute_period_production(
        lat=lat, lon=lon, capacity_mwp=capacity,
        start_date=_dt_mod.date.fromisoformat(start_iso),
        end_date=_dt_mod.date.fromisoformat(end_iso),
    )

with st.spinner("Computing trailing 12 months…"):
    period_data = _compute_t12m_cached(
        park_id=selected_park_id,
        lat=float(selected_row["lat"]),
        lon=float(selected_row["lon"]),
        capacity=float(selected_row["capacity_mwp"]),
        start_iso=T12M_START.isoformat(),
        end_iso=T12M_END.isoformat(),
    )
    period_data_prev = _compute_t12m_cached(
        park_id=selected_park_id + "_prev",
        lat=float(selected_row["lat"]),
        lon=float(selected_row["lon"]),
        capacity=float(selected_row["capacity_mwp"]),
        start_iso=T12M_START_PREV.isoformat(),
        end_iso=T12M_END_PREV.isoformat(),
    )

if not period_data:
    st.error(f"Could not compute T12M production for {selected_row['name']}")
    st.stop()

# Convert to the shape the rest of the panel expects
hourly_data = {
    "hourly_production_kwh": period_data["hourly_production_kwh"],
    "hourly_irradiance_wm2": [],   # not needed downstream
    "timestamps": period_data["timestamps"],
}
DATA_YEAR_LABEL = f"{T12M_START.isoformat()} → {T12M_END.isoformat()}"

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

    estimated_mw = estimate_instant_output_mw(
        lat=float(selected_row["lat"]),
        lon=float(selected_row["lon"]),
        capacity_mwp=float(selected_row["capacity_mwp"]),
        ghi_w_m2=live_weather["ghi_w_m2"],
        dni_w_m2=live_weather.get("dni_w_m2", 0.0),
        dhi_w_m2=live_weather.get("diffuse_w_m2", 0.0),
        temp_c=live_weather["temp_c"],
        wind_ms=live_weather.get("wind_ms", 1.0),
        time_iso=live_weather.get("time_iso") or "",
    )
    cf_now = (estimated_mw / float(selected_row["capacity_mwp"]) * 100.0) if selected_row["capacity_mwp"] else 0.0

    # Bridge live ↔ historical : compare to "same hour 1 year ago" (prior-year T12M window)
    import datetime as _dt
    _now_utc = _dt.datetime.now(_dt.timezone.utc)
    typical_mw_this_hour: float | None = None
    if period_data_prev:
        # find the index in hourly_data_prev whose timestamp matches (now - 1 year) at the hour
        target = _now_utc - _dt.timedelta(days=365)
        target_iso_prefix = target.strftime("%Y-%m-%dT%H")
        for i, ts in enumerate(period_data_prev["timestamps"]):
            if ts.startswith(target_iso_prefix):
                typical_mw_this_hour = period_data_prev["hourly_production_kwh"][i] / 1000.0
                break
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
            f"Same hour one year ago : {typical_mw_this_hour:.1f} MW." if typical_mw_this_hour else
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

# T12M annual aggregate
annual_kwh = sum(hourly_data["hourly_production_kwh"])
annual_mwh = annual_kwh / 1000.0
cf_annual = capacity_factor_annual(
    hourly_data["hourly_production_kwh"], peakpower_mw=selected_row["capacity_mwp"]
)
monthly = monthly_aggregates_from_timestamps(
    hourly_data["hourly_production_kwh"], hourly_data["timestamps"]
)

# Yesterday's output (J-1 — last full day in T12M data)
import datetime as _dtmod2
_yest = T12M_END  # last day in our data window
_yest_idx_start = (T12M_DAYS - 1) * 24
_yest_idx_end = T12M_DAYS * 24
yesterday_kwh = sum(hourly_data["hourly_production_kwh"][_yest_idx_start:_yest_idx_end])
yesterday_mwh = yesterday_kwh / 1000.0

# Same calendar day 1 year before (from T12M_START_PREV window)
yest_prev_mwh = None
if period_data_prev:
    prev_idx_start = (T12M_DAYS - 1) * 24
    prev_idx_end = T12M_DAYS * 24
    yest_prev_kwh = sum(period_data_prev["hourly_production_kwh"][prev_idx_start:prev_idx_end])
    yest_prev_mwh = yest_prev_kwh / 1000.0

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
# HISTORICAL · last 12 months (T12M rolling)
# ---------------------------------------------------------------------------

st.markdown(
    f"""
    <div class="section-header">
      <span class="section-label">Historical · last 12 months</span>
      <span class="section-caption">
        Rolling window <b>{T12M_START.isoformat()} → {T12M_END.isoformat()}</b>.
        Full pvlib reconstruction (Open-Meteo Archive 5-day lag, Hay-Davies POA,
        Sandia cell temp, PVWatts DC, inverter clipping, 14% losses).
        Validated within ±2-5% of PVGIS-grade output.
      </span>
    </div>
    """,
    unsafe_allow_html=True,
)

m1, m2, m3, m4 = st.columns(4)

# J-1 output with year-on-year comparison
yest_delta_label = ""
if yest_prev_mwh and yest_prev_mwh > 0.01:
    d_yest = (yesterday_mwh - yest_prev_mwh) / yest_prev_mwh * 100.0
    yest_delta_label = f"{d_yest:+.0f}% vs same day −1 year"

m1.metric(
    f"Output {_yest.strftime('%d %b')}",
    f"{yesterday_mwh:,.1f} MWh",
    delta=yest_delta_label or None,
    delta_color="off",
    help=(
        f"Production for the last full day available ({_yest.isoformat()}). "
        f"The Open-Meteo Archive lag means today is incomplete; we display the latest closed day. "
        f"Same day in {_yest.year - 1}: {yest_prev_mwh:,.1f} MWh." if yest_prev_mwh else
        f"Production for {_yest.isoformat()}, the last fully-available day in the Open-Meteo Archive."
    ),
)
m2.metric(
    "T12M output",
    f"{annual_mwh:,.0f} MWh",
    help=f"Total production over the rolling 365-day window {T12M_START.isoformat()} → {T12M_END.isoformat()}.",
)
m3.metric(
    "Capacity factor (T12M)",
    f"{cf_annual:.1f} %",
    help=(
        "Capacity factor = annual production / (nameplate capacity × 8 760 h). "
        "Measures how much of the theoretical maximum the asset achieves over the year. "
        "European solar benchmarks: 11-13% (northern), 15-18% (Iberia), 19-21% (sun-belt US/Spain south)."
    ),
)

if reported:
    m4.metric(
        "Δ vs operator press release",
        f"{delta_pct:+.1f} %",
        delta=SEVERITY_LABELS[delta_severity],
        delta_color="off",
        help=(
            f"Compares our T12M reconstruction ({annual_mwh:,.0f} MWh) to the operator-reported figure "
            f"({float(reported['annual_mwh']):,.0f} MWh, {reported['year']}). "
            "Reasons for non-zero delta: panel degradation since commissioning, real losses different from 14%, "
            "press-release rounding, geometry assumptions different from reality."
        ),
    )
else:
    m4.metric(
        "Δ vs operator press release",
        "—",
        help=(
            "No public annual production figure was identified in the operator's press release for this park. "
            "Common for small / multi-site portfolios."
        ),
    )

# ---------------------------------------------------------------------------
# REVENUE · YEAR 2023 — historical production × historical prices
# ---------------------------------------------------------------------------

zone = get_zone(selected_row["country"], park_id=selected_park_id)
fallback_price = get_fallback_price(selected_park_id)
revenue_metrics: dict = {}
revenue_source = ""
period_prices: dict | None = None

@st.cache_data(ttl=86400, show_spinner=False)
def _fetch_period_prices_cached(zone: str, start_iso: str, end_iso: str) -> dict | None:
    return fetch_period_prices(zone, start_iso, end_iso)

if zone:
    period_prices = _fetch_period_prices_cached(zone, T12M_START.isoformat(), T12M_END.isoformat())
    if period_prices and period_prices.get("prices_eur_mwh"):
        revenue_metrics = compute_revenue_metrics(
            hourly_production_kwh=hourly_data["hourly_production_kwh"],
            hourly_prices_eur_mwh=period_prices["prices_eur_mwh"],
        )
        revenue_source = f"hourly day-ahead zone {zone}"

# Fallback : flat annual avg price for US/Ireland zones not on energy-charts
if not revenue_metrics and fallback_price is not None:
    flat_prices = [fallback_price] * len(hourly_data["hourly_production_kwh"])
    revenue_metrics = compute_revenue_metrics(
        hourly_production_kwh=hourly_data["hourly_production_kwh"],
        hourly_prices_eur_mwh=flat_prices,
    )
    revenue_source = f"flat annual avg ({fallback_price:.0f} €/MWh) — hourly data not available"

_revenue_caption = revenue_source or f"Zone {zone or '—'} not available — revenue cannot be computed."

st.markdown(
    f"""
    <div class="section-header">
      <span class="section-label">Revenue · last 12 months</span>
      <span class="section-caption">
        Hourly production × hourly day-ahead spot price for each of the 8&nbsp;760 hours
        in the rolling year ({T12M_START.isoformat()} → {T12M_END.isoformat()}).
        Source : <b>{_revenue_caption}</b>.
      </span>
    </div>
    """,
    unsafe_allow_html=True,
)

r1, r2, r3, r4 = st.columns(4)

if revenue_metrics:
    r1.metric(
        "Total revenue (T12M)",
        f"€ {revenue_metrics['annual_revenue_eur'] / 1_000_000:,.2f} M",
        help=(
            "Total euros earned over the last 12 months. "
            "Computed by summing, for each hour : production_MWh × spot_price_EUR_per_MWh. "
            "Captures actual market conditions hour by hour, including negative spot prices and the regulatory floor at 0 €/MWh in Italy."
        ),
    )
    r2.metric(
        "Effective sale price (T12M)",
        f"{revenue_metrics['effective_price_eur_mwh']:,.1f} €/MWh",
        help=(
            "The price actually realised on each MWh sold, weighted by when production happened. "
            "Formula : total_revenue / total_production_mwh. "
            "Differs from the simple market average because the park doesn't produce evenly — it produces a lot at midday "
            "(when prices are pushed down by solar oversupply) and nothing at night (when prices spike). "
            "This is the asset's true revenue per MWh — what really lands on the cash flow."
        ),
    )
    r3.metric(
        "Day-ahead avg (T12M)",
        f"{revenue_metrics['avg_dayahead_price_eur_mwh']:,.1f} €/MWh",
        help=(
            "Simple arithmetic mean of all 8 760 hourly day-ahead market prices on the asset's bidding zone. "
            "Reference market level — what the typical hour was priced at on average. "
            "An asset would earn this much per MWh ONLY if it produced flat across all hours. "
            "Solar parks earn less because their generation is concentrated in low-price hours."
        ),
    )
    cann = revenue_metrics["cannibalization_pct"]
    r4.metric(
        "Cannibalisation (T12M)",
        f"{cann:+.1f} %",
        help=(
            "Difference between the effective sale price and the day-ahead average, in % of the average. "
            "Formula : (effective − day_ahead_avg) / day_ahead_avg. "
            "Negative = the asset earns less than the market average per MWh because solar concentrates production at midday "
            "when oversupply pushes prices down. "
            "Worsens with the solar penetration rate of the zone — Iberia 2026 typically sees -50 to -80% cannibalisation. "
            "The risk #1 of merchant solar today, and the main argument for PPAs, batteries, and east/west tracking."
        ),
    )
else:
    r1.metric("Total revenue (T12M)", "—", help="No price data available for this zone over this window.")
    r2.metric("Effective sale price (T12M)", "—")
    r3.metric("Day-ahead avg (T12M)", "—")
    r4.metric("Cannibalisation (T12M)", "—")

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

# ---------------------------------------------------------------------------
# BACKTEST · Recent N days vs {DATA_YEAR} same period
# ---------------------------------------------------------------------------

_baseline_year_for_backtest = T12M_END.year - 1

st.markdown(
    f"""
    <div class="section-header">
      <span class="section-label">Backtest · recent vs {_baseline_year_for_backtest}</span>
      <span class="section-caption">
        Same calendar window, two different years. Recent = Open-Meteo archive (last available days,
        5-day publishing lag) priced at current spot. Baseline = pvlib reconstruction of {_baseline_year_for_backtest} priced at {_baseline_year_for_backtest} spot.
        Surfaces how the market context for this asset has evolved over the year.
      </span>
    </div>
    """,
    unsafe_allow_html=True,
)

bt_col_toggle, _ = st.columns([1, 4])
with bt_col_toggle:
    bt_window = st.radio(
        "Window",
        options=[7, 30],
        format_func=lambda d: f"Last {d} days",
        horizontal=True,
        key=f"bt-window-{selected_park_id}",
        label_visibility="collapsed",
    )

bt_zone = get_zone(selected_row["country"], park_id=selected_park_id)
bt_recent = _backtest_recent_cached(
    park_id=selected_park_id,
    lat=float(selected_row["lat"]),
    lon=float(selected_row["lon"]),
    capacity=float(selected_row["capacity_mwp"]),
    zone=bt_zone,
    days=bt_window,
)
bt_old = _backtest_baseline_cached(
    park_id=selected_park_id,
    hourly_kwh_tuple=tuple(hourly_data["hourly_production_kwh"]),
    baseline_year=_baseline_year_for_backtest,
    zone=bt_zone,
    days=bt_window,
)

if bt_recent and bt_old:
    bt_start, bt_end = get_recent_window(days=bt_window, end_offset_days=5)
    bt_old_start = bt_start.replace(year=_baseline_year_for_backtest)
    bt_old_end = bt_end.replace(year=_baseline_year_for_backtest)
    st.markdown(
        f"<div style='font-family: \"JetBrains Mono\", monospace; font-size: 0.72rem; "
        f"color: var(--text-muted); margin: 8px 0 14px; letter-spacing: 0.04em;'>"
        f"Recent window : <b style='color:var(--text-secondary);'>{bt_start} → {bt_end}</b> · "
        f"compared to <b style='color:var(--text-secondary);'>{bt_old_start} → {bt_old_end}</b>"
        f"</div>",
        unsafe_allow_html=True,
    )

    bt1, bt2, bt3, bt4 = st.columns(4)

    # Production (climatic — same site, slightly different weather year by year)
    delta_prod = (bt_recent["production_mwh"] - bt_old["production_mwh"]) / bt_old["production_mwh"] * 100 if bt_old["production_mwh"] else 0
    bt1.metric(
        f"Production ({bt_window}d)",
        f"{bt_recent['production_mwh']:,.0f} MWh",
        delta=f"{delta_prod:+.1f}% vs {_baseline_year_for_backtest}",
        delta_color="off",
        help=f"{_baseline_year_for_backtest} same window: {bt_old['production_mwh']:,.0f} MWh. Climatic variation between two years.",
    )

    # Revenue (the key signal)
    if bt_recent.get("revenue_eur") is not None and bt_old.get("revenue_eur"):
        delta_rev = (bt_recent["revenue_eur"] - bt_old["revenue_eur"]) / bt_old["revenue_eur"] * 100
        rev_recent_k = bt_recent["revenue_eur"] / 1000.0
        bt2.metric(
            f"Revenue ({bt_window}d)",
            f"€ {rev_recent_k:,.0f} k",
            delta=f"{delta_rev:+.1f}% vs {_baseline_year_for_backtest}",
            delta_color="off",
            help=f"{_baseline_year_for_backtest} same window: € {bt_old['revenue_eur']/1000:,.0f}k. Captures market evolution.",
        )
    else:
        bt2.metric(f"Revenue ({bt_window}d)", "—", help=f"Zone {bt_zone or '—'} not available.")

    # Effective price
    if bt_recent.get("effective_price_eur_mwh") is not None and bt_old.get("effective_price_eur_mwh"):
        delta_eff = bt_recent["effective_price_eur_mwh"] - bt_old["effective_price_eur_mwh"]
        bt3.metric(
            f"Effective price ({bt_window}d)",
            f"{bt_recent['effective_price_eur_mwh']:,.1f} €/MWh",
            delta=f"{delta_eff:+.1f} vs {_baseline_year_for_backtest}",
            delta_color="off",
            help=f"{_baseline_year_for_backtest} same window: {bt_old['effective_price_eur_mwh']:.1f} €/MWh.",
        )
    else:
        bt3.metric(f"Effective price ({bt_window}d)", "—")

    # Cannibalisation
    if bt_recent.get("cannibalisation_pct") is not None and bt_old.get("cannibalisation_pct") is not None:
        delta_cann = bt_recent["cannibalisation_pct"] - bt_old["cannibalisation_pct"]
        bt4.metric(
            f"Cannibalisation ({bt_window}d)",
            f"{bt_recent['cannibalisation_pct']:+.1f} %",
            delta=f"{delta_cann:+.1f} pts vs {_baseline_year_for_backtest}",
            delta_color="off",
            help=f"{_baseline_year_for_backtest} same window: {bt_old['cannibalisation_pct']:+.1f}%. Negative delta = cannibalisation worsened.",
        )
    else:
        bt4.metric(f"Cannibalisation ({bt_window}d)", "—")

    # ----- Daily production + daily revenue, full T12M window -----
    st.markdown('<div class="vspace"></div>', unsafe_allow_html=True)

    daily_kwh_t12m = hourly_to_daily(hourly_data["hourly_production_kwh"])
    daily_mwh_t12m = [v / 1000.0 for v in daily_kwh_t12m]
    day_dates_t12m = pd.date_range(T12M_START.isoformat(), periods=len(daily_mwh_t12m), freq="D")

    # Daily revenue : per-hour production × per-hour price aggregated to days
    daily_rev_eur: list[float | None] = []
    if revenue_metrics and (period_prices and period_prices.get("prices_eur_mwh") or fallback_price is not None):
        if period_prices and period_prices.get("prices_eur_mwh"):
            hp = period_prices["prices_eur_mwh"]
        else:
            hp = [fallback_price or 0.0] * len(hourly_data["hourly_production_kwh"])
        hk = hourly_data["hourly_production_kwh"]
        for d in range(len(daily_mwh_t12m)):
            i0 = d * 24
            i1 = i0 + 24
            rev = sum((hk[i] / 1000.0) * (hp[i] if hp[i] is not None else 0.0) for i in range(i0, min(i1, len(hk))))
            daily_rev_eur.append(rev)

    fig_ts = go.Figure()
    fig_ts.add_trace(go.Scatter(
        x=day_dates_t12m,
        y=daily_mwh_t12m,
        name="Daily production",
        mode="lines",
        line=dict(color="#e8e4d6", width=1.6, shape="spline", smoothing=0.3),
        fill="tozeroy",
        fillcolor="rgba(232, 228, 214, 0.08)",
        hovertemplate="%{x|%d %b %Y} · %{y:,.1f} MWh<extra></extra>",
        yaxis="y",
    ))
    if daily_rev_eur:
        fig_ts.add_trace(go.Scatter(
            x=day_dates_t12m,
            y=[r / 1000.0 for r in daily_rev_eur],
            name="Daily revenue",
            mode="lines",
            line=dict(color="rgba(125, 211, 252, 0.85)", width=1.4, shape="spline", smoothing=0.3),
            hovertemplate="%{x|%d %b %Y} · € %{y:,.1f} k<extra></extra>",
            yaxis="y2",
        ))
    fig_ts.update_layout(
        title=dict(
            text=f"Daily production & revenue · T12M ({T12M_START.isoformat()} → {T12M_END.isoformat()})",
            font=dict(color="#f1f5f9", size=13, family="Geist", weight=500),
            x=0.0, xanchor="left", pad=dict(b=8),
        ),
        height=260,
        margin=dict(l=0, r=0, t=44, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(showgrid=False, tickfont=dict(color="#64748b", size=10, family="JetBrains Mono"), tickformat="%b %y", dtick="M1"),
        yaxis=dict(
            gridcolor="rgba(148, 163, 184, 0.06)",
            tickfont=dict(color="#cbd5e1", size=10, family="JetBrains Mono"),
            ticksuffix=" MWh",
            title=None,
        ),
        yaxis2=dict(
            overlaying="y", side="right", showgrid=False,
            tickfont=dict(color="rgba(125, 211, 252, 0.95)", size=10, family="JetBrains Mono"),
            ticksuffix=" k€",
            title=None,
        ),
        legend=dict(
            orientation="h", x=0, y=1.18, xanchor="left", yanchor="top",
            font=dict(color="#94a3b8", size=10, family="JetBrains Mono"),
            bgcolor="rgba(0,0,0,0)",
        ),
        hoverlabel=dict(
            bgcolor="rgba(13, 19, 32, 0.95)",
            bordercolor="rgba(232, 228, 214, 0.4)",
            font=dict(color="#f1f5f9", family="JetBrains Mono", size=11),
        ),
    )
    st.plotly_chart(fig_ts, width="stretch", config={"displayModeBar": False})
elif bt_recent and not bt_old:
    st.info(f"{_baseline_year_for_backtest} backtest unavailable for this zone.")
elif not bt_recent:
    st.info("Recent backtest unavailable — Open-Meteo archive or spot prices fetch failed.")

# ---------------------------------------------------------------------------
# TIME SERIES · year 2023
# ---------------------------------------------------------------------------

st.markdown(
    f"""
    <div class="section-header">
      <span class="section-label">Time series · last 12 months</span>
      <span class="section-caption">
        Daily and monthly breakdowns of T12M production ({T12M_START.isoformat()} → {T12M_END.isoformat()}).
        Reveals seasonality and the typical climatic shape of the site.
      </span>
    </div>
    """,
    unsafe_allow_html=True,
)

daily_kwh = hourly_to_daily(hourly_data["hourly_production_kwh"])
daily_mwh = [v / 1000.0 for v in daily_kwh]
day_dates = pd.date_range(T12M_START.isoformat(), periods=len(daily_mwh), freq="D")

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
        text="Daily output · T12M",
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

monthly_labels = [m["label"] for m in monthly]
monthly_mwh = [m["production_mwh"] for m in monthly]
fig_monthly = go.Figure()
fig_monthly.add_trace(
    go.Bar(
        x=monthly_labels,
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
        text="Monthly production · T12M",
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
# About this data
# ---------------------------------------------------------------------------

st.markdown('<div class="vspace"></div>', unsafe_allow_html=True)

with st.expander("How to read the sections", expanded=False):
    st.markdown(
        f"""
The panel mixes **two distinct horizons** that should never be confused.
Each section header makes the source and the time horizon explicit.

| Section | Horizon | Sources | Why it's there |
|---|---|---|---|
| **Live · right now** | This hour, refreshed every 15 min | Open-Meteo (irradiance + temp) · ENTSO-E day-ahead spot | Snapshot of what the park is doing **as you read this**. Useful for "is the park performing today?" |
| **Historical · last 12 months** | Rolling T12M ({T12M_START.isoformat()} → {T12M_END.isoformat()}) | pvlib + Open-Meteo Archive (ECMWF reanalysis, 5-day lag) | What the park produced in the most recent 365 days. PVGIS-grade physics. Reference for annual capacity factor + delta vs operator. |
| **Revenue · last 12 months** | Same T12M window | pvlib production × hourly day-ahead price (or US/IE flat fallback) | What the park earned in the trailing year. Captures cannibalisation. |
| **Backtest · recent vs prior year** | Last 7-30 days vs same window prior year | pvlib + spot prices, both years | How market context for this asset has evolved year-on-year. |
| **Time series · last 12 months** | Same T12M window, daily and monthly | Same as Historical | Visualises seasonality. |

**Why both Live and Historical ?**
- Live = is the park healthy today ? (compares to typical climatic conditions)
- Historical = how did it run over a full year ? (the only horizon you can compute revenue / capacity factor on)

A live MW number alone is not actionable for an analyst. A capacity factor alone is missing today's market context. **Both together** = the full picture.

---

### Sources

- **pvlib** (open-source Python library) — solar production physics
  (POA transposition, cell temperature, DC/AC modelling). Industry standard.
  <https://pvlib-python.readthedocs.io/>
- **Open-Meteo Archive** — historical hourly weather (GHI, DNI, DHI, T, wind)
  from ECMWF reanalysis, 5-day publishing lag, covers 1940-today.
  <https://open-meteo.com/>
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
