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
SUB_SITE_OVERRIDES_PATH = _ROOT / "data" / "sub_site_overrides.yaml"


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


def _load_sub_site_overrides() -> dict[str, dict[str, list[float]]]:
    """Per-portfolio overrides : {park_id: {site_name: [lat, lon]}}."""
    if not SUB_SITE_OVERRIDES_PATH.exists():
        return {}
    with open(SUB_SITE_OVERRIDES_PATH) as f:
        return yaml.safe_load(f) or {}


def _save_sub_site_override(park_id: str, site_name: str, lat: float, lon: float) -> None:
    overrides = _load_sub_site_overrides()
    overrides.setdefault(park_id, {})[site_name] = [round(float(lat), 6), round(float(lon), 6)]
    with open(SUB_SITE_OVERRIDES_PATH, "w") as f:
        yaml.safe_dump(overrides, f, default_flow_style=False, sort_keys=True, allow_unicode=True)


def _delete_sub_site_override(park_id: str, site_name: str) -> None:
    overrides = _load_sub_site_overrides()
    if park_id in overrides and site_name in overrides[park_id]:
        del overrides[park_id][site_name]
        if not overrides[park_id]:
            del overrides[park_id]
        with open(SUB_SITE_OVERRIDES_PATH, "w") as f:
            yaml.safe_dump(overrides, f, default_flow_style=False, sort_keys=True, allow_unicode=True)


SUB_SITE_VERIFIED_PATH = _ROOT / "data" / "sub_site_verified_built.yaml"


def _load_sub_site_verified() -> dict[str, dict[str, bool]]:
    """User-curated 'visually confirmed built' flag per sub-site, set via the focus button.

    Bypasses the SEAI lag: SEAI flips Contracted→Connected only after final commissioning,
    which can be 3-12 months after panels are physically posed. This file holds the user's
    visual verifications from satellite imagery.
    """
    if not SUB_SITE_VERIFIED_PATH.exists():
        return {}
    with open(SUB_SITE_VERIFIED_PATH) as f:
        return yaml.safe_load(f) or {}


def _toggle_sub_site_verified(park_id: str, site_name: str) -> bool:
    data = _load_sub_site_verified()
    park_data = data.setdefault(park_id, {})
    if park_data.get(site_name):
        del park_data[site_name]
        if not park_data:
            del data[park_id]
        new_state = False
    else:
        park_data[site_name] = True
        new_state = True
    with open(SUB_SITE_VERIFIED_PATH, "w") as f:
        yaml.safe_dump(data, f, default_flow_style=False, sort_keys=True, allow_unicode=True)
    return new_state


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


@st.cache_data(ttl=900, show_spinner=False)  # 15 min refresh — matches energy-charts 15-min slot resolution
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


def _build_satellite_html(
    lat: float,
    lon: float,
    label: str,
    sites_count: int = 1,
    sub_sites: list[dict] | None = None,
    focused_sub_idx: int | None = None,
) -> str:
    """Render a satellite map.

    For single-site parks : zoom 14, single marker on the panels.
    For multi-site portfolios with `sub_sites` provided (ex. Elgin Ireland) : zoom auto-fit on
    bounding box of all sub-sites. If `focused_sub_idx` is set, jump to that site at zoom 16
    and highlight its marker. Real markers at commune-level coordinates with name/county/capacity tooltips.
    For multi-site portfolios without `sub_sites` (ex. Brindisi) : zoom 8, scatter `sites_count`
    deterministic random sub-markers as a visual proxy.
    """
    import json as _json
    label_safe = label.replace("'", "&#39;").replace('"', "&quot;")
    multi = sites_count > 1
    has_real_subs = bool(sub_sites)
    sub_sites_json = _json.dumps(sub_sites or [])
    focused_json = _json.dumps(focused_sub_idx)
    initial_zoom = 8 if multi else 14
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
    .setView([{lat}, {lon}], {initial_zoom});
  L.tileLayer(
    'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}',
    {{ maxZoom: 18, attribution: 'Esri, Maxar, Earthstar Geographics' }}
  ).addTo(map);

  const multi = {str(multi).lower()};
  const N = {sites_count};
  const subSites = {sub_sites_json};
  const hasRealSubs = {str(has_real_subs).lower()};
  const focusedIdx = {focused_json};
  if (multi && hasRealSubs) {{
    // Real sub-sites — render markers at commune-level coords with rich popups
    const points = subSites.map(s => [s.lat, s.lon]);
    subSites.forEach((s, i) => {{
      const isFocused = (i === focusedIdx);
      const isOverridden = !!s.is_overridden;
      const isVerified = !!s.is_verified_built;
      const isEsbEnergised = !!s.is_esb_energised;
      // Priority: focused (lime) > ESB energised (lime, official) > verified visual (lime) > overridden (blue) > default (cream)
      let baseColor = '#e8e4d6';
      if (isOverridden) baseColor = '#7dd3fc';
      if (isVerified) baseColor = '#84cc16';
      if (isEsbEnergised) baseColor = '#84cc16';
      if (isFocused) baseColor = '#84cc16';
      const marker = L.circleMarker([s.lat, s.lon], {{
        radius: isFocused ? 9 : (isEsbEnergised || isVerified ? 7 : 5),
        color: baseColor,
        weight: isFocused ? 2.5 : (isEsbEnergised || isVerified ? 2 : 1.5),
        fillColor: baseColor,
        fillOpacity: isFocused ? 0.95 : (isEsbEnergised || isVerified ? 0.95 : 0.9),
      }}).addTo(map);
      let tags = '';
      if (isOverridden) tags += '<span style="color:#7dd3fc; font-size:10px; margin-left:6px; letter-spacing:0.06em;">[CORRECTED]</span>';
      if (isEsbEnergised) {{
        const dateLabel = s.esb_connect_date ? ' · ' + s.esb_connect_date : '';
        tags += '<span style="color:#84cc16; font-size:10px; margin-left:6px; font-weight:600; letter-spacing:0.08em;">ENERGISED' + dateLabel + '</span>';
      }} else if (isVerified) {{
        tags += '<span style="color:#84cc16; font-size:10px; margin-left:6px; font-weight:600; letter-spacing:0.08em;">BUILT</span>';
      }}
      const offerLine = s.offer_type ? '<div style="color: #eab308; font-size: 10px; margin-top: 2px; letter-spacing:0.04em;">' + s.offer_type + ' · non-firm, curtailment risk</div>' : '';
      marker.bindPopup(
        '<div style="font-family: Geist, sans-serif; font-size: 12px; min-width: 200px;">' +
        '<div style="font-weight: 600; color: #f1f5f9; margin-bottom: 3px;">' + s.name + tags + '</div>' +
        '<div style="color: #94a3b8; font-size: 11px;">Co. ' + s.county + ' · ' + s.capacity_mw.toFixed(1) + ' MW</div>' +
        offerLine +
        '<div style="color: #7a7464; font-size: 10px; margin-top: 4px;">' + s.lat.toFixed(4) + ', ' + s.lon.toFixed(4) + '</div>' +
        '</div>'
      );
      marker.bindTooltip(s.name + ' · ' + s.capacity_mw.toFixed(1) + ' MW', {{
        permanent: false, direction: 'top', offset: [0, -8],
      }});
      if (isFocused) marker.openPopup();
    }});
    // Centroid pin (subtle, hidden when focused on a single site)
    if (focusedIdx === null) {{
      L.circleMarker([{lat}, {lon}], {{
        radius: 4, color: '#84cc16', weight: 1.5,
        fillColor: '#84cc16', fillOpacity: 0.5,
      }}).addTo(map).bindPopup('Portfolio centroid · {sites_count} known candidate sites');
    }}
    // Either focus on a specific site (zoom 16) or fit bounds of all sites
    if (focusedIdx !== null && subSites[focusedIdx]) {{
      const f = subSites[focusedIdx];
      map.setView([f.lat, f.lon], 16);
    }} else if (points.length > 0) {{
      map.fitBounds(L.latLngBounds(points), {{ padding: [40, 40] }});
    }}
  }} else if (multi) {{
    // Fallback : portfolio without sub-site coords — illustrative random scatter
    L.circle([{lat}, {lon}], {{
      radius: 25000, color: '#e8e4d6', weight: 1.2, opacity: 0.55,
      fillColor: '#e8e4d6', fillOpacity: 0.05,
      dashArray: '6, 6',
    }}).addTo(map).bindPopup('Region of {label_safe} — exact sub-site addresses not public');
    let seed = N * 9301 + 49297;
    function rand() {{ seed = (seed * 1597 + 51749) % 244944; return seed / 244944; }}
    for (let i = 0; i < N; i++) {{
      const angle = rand() * 2 * Math.PI;
      const r = (0.4 + rand() * 0.5) * 0.18;
      const dlat = r * Math.cos(angle);
      const dlon = r * Math.sin(angle) / Math.cos({lat} * Math.PI / 180);
      L.circleMarker([{lat} + dlat, {lon} + dlon], {{
        radius: 4, color: '#e8e4d6', weight: 1.5,
        fillColor: '#e8e4d6', fillOpacity: 0.85,
      }}).addTo(map);
    }}
    L.circleMarker([{lat}, {lon}], {{
      radius: 6, color: '#84cc16', weight: 2,
      fillColor: '#84cc16', fillOpacity: 0.6,
    }}).addTo(map).bindPopup('Portfolio centroid · {sites_count} sites');
  }} else {{
    L.circleMarker([{lat}, {lon}], {{
      radius: 14, color: '#e8e4d6', weight: 2,
      fillColor: '#e8e4d6', fillOpacity: 0.12,
    }}).addTo(map).bindPopup('{label_safe}');
    L.circleMarker([{lat}, {lon}], {{
      radius: 5, color: '#e8e4d6', weight: 2,
      fillColor: '#e8e4d6', fillOpacity: 0.95,
    }}).addTo(map);
  }}
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

st.markdown(
    """
    <div class="atlas-header">
      <h1 class="atlas-title">Allianz Renewables Atlas</h1>
      <p class="atlas-tag">
        Projet personnel initi&eacute; par Mancef Ferrah dans le cadre d'une
        candidature en alternance Investment Management. Atlas exploratoire
        des parcs solaires actifs d'Allianz Capital Partners, identifi&eacute;s
        via sources publiques uniquement.
      </p>
    </div>
    """,
    unsafe_allow_html=True,
)

parks_df = _load_parks_df()
reported_map = _load_reported()

# ---------------------------------------------------------------------------
# Atlas key figures — single inline pill bar (replaces generic 3-card grid)
# ---------------------------------------------------------------------------

# Atlas KPIs — distinguish effectively owned from "in atlas for context"
from src.lib.parks_loader import load_parks_index as _load_idx_for_kpi
_idx_kpi = _load_idx_for_kpi()
_owned = [p for p in _idx_kpi.parks if not p.divested]
_n_parks = len(_owned)
_total_mwp = sum(p.capacity_mwp or 0 for p in _owned)
_n_countries = len({p.country for p in _owned})
_country_codes = " · ".join(sorted({p.country for p in _owned}))

st.markdown(
    f"""
    <div class="atlas-kpis">
      <div class="kpi">
        <span class="kpi-num">{_n_parks}</span>
        <span class="kpi-lbl">parks</span>
      </div>
      <div class="kpi-sep">/</div>
      <div class="kpi">
        <span class="kpi-num">{_total_mwp:,.0f}</span>
        <span class="kpi-lbl">MWp DC</span>
      </div>
      <div class="kpi-sep">/</div>
      <div class="kpi">
        <span class="kpi-num">{_n_countries}</span>
        <span class="kpi-lbl">countries</span>
        <span class="kpi-codes">{_country_codes}</span>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

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
          <span class="empty-prompt">—</span> Click a marker on the globe to open
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

# ---------------------------------------------------------------------------
# Forward-sale portfolios: branch to minimal panel (no T12M / Live / Backtest)
# ---------------------------------------------------------------------------

from src.lib.parks_loader import get_park_by_id as _get_park_for_status
_park_model_for_status = _get_park_for_status(selected_park_id)
_is_forward_sale = (
    _park_model_for_status is not None
    and _park_model_for_status.portfolio_status == "forward_sale"
)

if _is_forward_sale:
    from src.lib.portfolio_model import (
        compute_portfolio_typical_year,
        compute_portfolio_revenue_flat,
    )
    import datetime as _dt_fs

    # Park header
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
              <div class="stat-label">Nameplate (DC)</div>
              <div class="stat-value">{selected_row['capacity_mwp']:,.0f} <span class="stat-unit">MWp</span></div>
            </div>
            <div class="stat">
              <div class="stat-label">Acquisition</div>
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

    # Forward-sale context banner
    n_subs = len(_park_model_for_status.sub_sites or [])
    n_energised = sum(1 for s in (_park_model_for_status.sub_sites or []) if s.esb_status == "Energised")
    n_contracted = n_subs - n_energised
    mw_energised = sum(s.capacity_mw for s in (_park_model_for_status.sub_sites or []) if s.esb_status == "Energised")
    st.markdown(
        f"""
        <div style="
          margin: 14px 0 18px; padding: 14px 18px;
          background: rgba(125, 211, 252, 0.07);
          border: 1px solid rgba(125, 211, 252, 0.30);
          border-radius: 10px;
          font-family: 'JetBrains Mono', monospace; font-size: 0.78rem;
          color: #cbd5e1; line-height: 1.55;">
          <div style="font-weight: 600; color: #7dd3fc; margin-bottom: 6px; letter-spacing: 0.04em;">
            FORWARD-SALE PORTFOLIO — PARTIAL ENERGIZATION IN PROGRESS
          </div>
          Allianz acquired this {n_subs}-site portfolio in <b>December 2023</b> as a forward sale :
          permits + EirGrid grid-connection rights + RESS-2/3 state-secured revenue contracts.
          Per <b>ESB Networks DSO Q4 2025 report</b> (information correct 01/01/2026),
          <b>{n_energised} of {n_subs} sites are physically grid-connected</b>
          ({mw_energised:.1f} MWac active), {n_contracted} sites still contracted.
          <br><br>
          <span style="color: #fbbf24;">Curtailment risk:</span> the energised sites operate under
          <b>Non GPA / ECP-2.1</b> (non-firm) access — EirGrid may reduce output without compensation
          during grid congestion until network reinforcements ~2029-2030.
          <br><br>
          Live / T12M / backtest sections skipped (incomplete production history). Metrics below are
          <b>pvlib-projected</b> at each site's own GPS coords using site-specific Open-Meteo Archive weather.
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Compute per-site pvlib over a baseline calendar year
    @st.cache_data(ttl=86400, show_spinner=False)
    def _compute_portfolio_typical_cached(park_id: str, sub_sites_tuple: tuple, dc_ac: float) -> dict | None:
        sub_sites_list = [
            {"name": n, "lat": la, "lon": lo, "capacity_mw": mw}
            for (n, la, lo, mw) in sub_sites_tuple
        ]
        baseline_end = _dt_fs.date.today() - _dt_fs.timedelta(days=ARCHIVE_LAG_DAYS)
        baseline_start = baseline_end - _dt_fs.timedelta(days=T12M_DAYS - 1)
        return compute_portfolio_typical_year(
            sub_sites=sub_sites_list,
            baseline_start=baseline_start,
            baseline_end=baseline_end,
            dc_ac_ratio=dc_ac,
        )

    sub_sites_for_calc = tuple(
        (s.name, s.lat, s.lon, s.capacity_mw)
        for s in (_park_model_for_status.sub_sites or [])
    )

    with st.spinner(f"Computing pvlib for {n_subs} sites individually…"):
        portfolio = _compute_portfolio_typical_cached(
            selected_park_id, sub_sites_for_calc, _park_model_for_status.dc_ac_ratio,
        )

    if not portfolio:
        st.error("Portfolio production calculation failed.")
        st.stop()

    annual_mwh = portfolio["annual_total_mwh"]
    total_cap_ac = portfolio["total_capacity_mw_ac"]
    total_cap_dc = portfolio["total_capacity_mwp_dc"]
    cf_pct = (annual_mwh * 1000.0) / (total_cap_dc * 1000.0 * 8760.0) * 100.0

    # ----- Headline metrics -----
    st.markdown(
        f"""
        <div class="section-header section-first">
          <span class="section-label">Projected annual output (full energization)</span>
          <span class="section-caption">
            Hour-by-hour pvlib reconstruction — each of the {n_subs} sites computed at its
            <b>own GPS coordinates</b> using site-specific weather (Open-Meteo Archive).
            Aggregate is the sum across all sites. Baseline window : last 12 months of available weather.
          </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Load verified-built flags
    _verified_for_park = _load_sub_site_verified().get(selected_park_id, {})

    # Compute currently-confirmed subset
    verified_count = 0
    verified_mw_ac = 0.0
    verified_mwh = 0.0
    for s, calc in zip(_park_model_for_status.sub_sites or [], portfolio["per_site"]):
        if _verified_for_park.get(s.name):
            verified_count += 1
            verified_mw_ac += s.capacity_mw
            verified_mwh += calc["annual_mwh"]

    pm1, pm2, pm3, pm4 = st.columns(4)
    pm1.metric(
        "Projected annual output",
        f"{annual_mwh:,.0f} MWh",
        help=(
            "Sum of pvlib hourly outputs across all sub-sites over the last 365 days of available weather data, "
            "assuming all sites are fully energized at their nameplate capacity. Reality today is FAR lower "
            "because most sites are still under construction (see SEAI status column below)."
        ),
    )
    pm2.metric(
        "Total nameplate (AC / DC)",
        f"{total_cap_ac:,.1f} / {total_cap_dc:,.0f} MW",
        help=(
            f"AC export capacity (sum of contracted MW with EirGrid) / DC peak (panels), "
            f"using DC/AC over-build {_park_model_for_status.dc_ac_ratio:.2f}. "
            "DC is what the press release quotes (191 MWp), AC is what the grid sees (≈137 MW)."
        ),
    )
    pm3.metric(
        "Capacity factor",
        f"{cf_pct:.1f} %",
        help=(
            "Projected capacity factor across the portfolio. Irish solar typically achieves 11-13% "
            "due to high latitude + cloud cover. South-Iberia benchmarks for comparison: 19-22%."
        ),
    )

    if _park_model_for_status.ress_strike_price_eur_mwh:
        rev = compute_portfolio_revenue_flat(
            annual_production_mwh=annual_mwh,
            strike_price_eur_mwh=_park_model_for_status.ress_strike_price_eur_mwh,
        )
        pm4.metric(
            "Projected annual revenue",
            f"€ {rev['annual_revenue_meur']:.2f} M",
            help=(
                f"Annual MWh × RESS strike price ({_park_model_for_status.ress_strike_price_eur_mwh:.0f} €/MWh weighted avg, "
                f"RESS-2/3 2-way CfD). State-backed contract neutralises wholesale price volatility and "
                f"solar cannibalisation — the project earns the strike price on every MWh sold for ~15 years."
            ),
        )
    else:
        pm4.metric("Projected annual revenue", "—", help="No RESS strike price configured.")

    # Currently-producing subset = ESB Energised OR user verified-built (whichever flag is set)
    energised_count = 0
    energised_mw_ac = 0.0
    energised_mwh = 0.0
    energised_dates = []
    for s, calc in zip(_park_model_for_status.sub_sites or [], portfolio["per_site"]):
        if s.esb_status == "Energised" or _verified_for_park.get(s.name):
            energised_count += 1
            energised_mw_ac += s.capacity_mw
            energised_mwh += calc["annual_mwh"]
            if s.esb_connect_date:
                energised_dates.append(s.esb_connect_date)
    if energised_count > 0:
        energised_revenue_meur = (
            energised_mwh * (_park_model_for_status.ress_strike_price_eur_mwh or 0) / 1_000_000.0
        )
        date_range = (
            f"earliest connection {min(energised_dates)}" if energised_dates else "ESB-confirmed"
        )
        st.markdown(
            f"""
            <div style="margin: 10px 0 14px; padding: 10px 14px;
              background: rgba(132, 204, 22, 0.07);
              border-left: 3px solid #84cc16;
              border-radius: 4px;
              font-family: 'JetBrains Mono', monospace; font-size: 0.74rem;
              color: #cbd5e1; letter-spacing: 0.02em;">
              <span style="color: #84cc16; font-weight: 600;">CURRENTLY PRODUCING (ESB Networks Q4 2025 confirmed)</span>
              &nbsp;&nbsp;
              <b style="color:#f1f5f9;">{energised_count}/{len(_park_model_for_status.sub_sites or [])} sites</b>
              &nbsp;·&nbsp; {energised_mw_ac:.1f} MW (AC)
              &nbsp;·&nbsp; <b style="color:#f1f5f9;">{energised_mwh:,.0f} MWh/yr</b> (pvlib projection)
              &nbsp;·&nbsp; € {energised_revenue_meur:.2f} M revenue/yr
              <div style="margin-top:4px; color:#7a7464; font-size:0.72rem;">
                {date_range} · all on Non-GPA / ECP-2.1 (non-firm, curtailment risk).
                Remaining {annual_mwh - energised_mwh:,.0f} MWh from {len(_park_model_for_status.sub_sites or [])-energised_count} sites pending construction completion.
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f"""
            <div style="margin: 10px 0 14px; padding: 10px 14px;
              background: rgba(100, 116, 139, 0.06);
              border-left: 3px solid rgba(100, 116, 139, 0.5);
              border-radius: 4px;
              font-family: 'JetBrains Mono', monospace; font-size: 0.72rem;
              color: #94a3b8; letter-spacing: 0.02em;">
              <span style="color: #cbd5e1;">No site visually confirmed built yet.</span>
              Click a site button below, open in Google Maps satellite,
              and toggle "Confirm built" if you spot the panel array.
              Currently confirmed sites will accrue MWh / revenue here.
            </div>
            """,
            unsafe_allow_html=True,
        )

    # ----- Per-site breakdown -----
    st.markdown(
        """
        <div class="section-header">
          <span class="section-label">Per-site breakdown</span>
          <span class="section-caption">
            EirGrid canonical project data (Firm Access 2024 Review) + SEAI Solar Atlas (precise GPS + connection status)
            + pvlib annual output computed at each site's coordinates. Cap factors vary by latitude and microclimate.
          </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    import pandas as pd_ps
    rows = []
    for s, calc in zip(_park_model_for_status.sub_sites or [], portfolio["per_site"]):
        is_energised = s.esb_status == "Energised"
        is_verified_user = bool(_verified_for_park.get(s.name))
        # ESB authoritative wins; user verified is a fallback indicator
        if is_energised:
            built_marker = "ENERGISED"
        elif is_verified_user:
            built_marker = "BUILT"
        else:
            built_marker = "—"
        rows.append({
            "Built?": built_marker,
            "Site (commune)": s.name,
            "EirGrid name": s.eirgrid_name or "—",
            "EirGrid code": s.eirgrid_code or "—",
            "Co.": s.county,
            "MW (AC)": s.capacity_mw,
            "Annual MWh (pvlib)": int(calc["annual_mwh"]),
            "CF %": round(calc["capacity_factor_pct"], 1),
            "ESB status": s.esb_status or "—",
            "Connected": s.esb_connect_date or "—",
            "Offer type": s.offer_type or "—",
            "Firm access": s.firm_access or "—",
        })
    df_subs = pd_ps.DataFrame(rows)
    st.dataframe(df_subs, use_container_width=True, hide_index=True)

    # ----- Sub-sites caption + map -----
    if _park_model_for_status.sub_sites_caption:
        st.markdown(
            f"""
            <div style="margin: 14px 0 8px; padding: 10px 14px;
              background: rgba(232, 228, 214, 0.04);
              border: 1px solid rgba(232, 228, 214, 0.18);
              border-radius: 8px;
              font-family: 'JetBrains Mono', monospace; font-size: 0.72rem;
              color: #94a3b8; line-height: 1.5;">
              {_park_model_for_status.sub_sites_caption}
            </div>
            """,
            unsafe_allow_html=True,
        )

    # ----- Map (re-use the multi-site renderer) -----
    st.markdown(
        """
        <div class="section-header">
          <span class="section-label">Site locations</span>
          <span class="section-caption">
            Real GPS coordinates from SEAI Solar Atlas. Click a button to focus on any site,
            double-click on the panels to override the position.
          </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    _sub_sites_payload_fs = []
    _sub_site_overrides_fs = _load_sub_site_overrides().get(selected_park_id, {})
    for s in _park_model_for_status.sub_sites:
        ov = _sub_site_overrides_fs.get(s.name)
        _sub_sites_payload_fs.append({
            "name": s.name,
            "county": s.county,
            "capacity_mw": s.capacity_mw,
            "lat": float(ov[0]) if ov else s.lat,
            "lon": float(ov[1]) if ov else s.lon,
            "is_overridden": ov is not None,
            "original_lat": s.lat,
            "original_lon": s.lon,
            "is_verified_built": bool(_verified_for_park.get(s.name)),
            "is_esb_energised": s.esb_status == "Energised",
            "esb_connect_date": s.esb_connect_date or "",
            "offer_type": s.offer_type or "",
        })

    _focus_key_fs = f"sat-focus-{selected_park_id}"
    _focused_idx_fs = st.session_state.get(_focus_key_fs)

    _per_row_fs = 6
    _items_fs = [("Overview", None)] + [(s["name"], i) for i, s in enumerate(_sub_sites_payload_fs)]
    for _row_start in range(0, len(_items_fs), _per_row_fs):
        _row = _items_fs[_row_start : _row_start + _per_row_fs]
        _cols = st.columns(_per_row_fs)
        for _ci, (_label, _idx_val) in enumerate(_row):
            _btn_key = f"focus-fs-{selected_park_id}-{_idx_val if _idx_val is not None else 'all'}"
            _is_active = _focused_idx_fs == _idx_val
            if _cols[_ci].button(
                _label, key=_btn_key, use_container_width=True,
                type=("primary" if _is_active else "secondary"),
            ):
                st.session_state[_focus_key_fs] = _idx_val
                st.rerun()

    if _focused_idx_fs is not None and 0 <= _focused_idx_fs < len(_sub_sites_payload_fs):
        _fs_pt = _sub_sites_payload_fs[_focused_idx_fs]
        from src.components.coord_picker import coord_picker as _coord_picker_fs
        _picker_label = f"{_fs_pt['name']} · Co. {_fs_pt['county']} · {_fs_pt['capacity_mw']:.1f} MW"
        _new_coords = _coord_picker_fs(
            lat=float(_fs_pt["lat"]), lon=float(_fs_pt["lon"]),
            label=_picker_label, height=420,
            key=f"sub-coord-picker-fs-{selected_park_id}-{_focused_idx_fs}",
        )
        if _new_coords:
            _new_lat, _new_lon = float(_new_coords[0]), float(_new_coords[1])
            _existing = _sub_site_overrides_fs.get(_fs_pt["name"])
            _is_new_save = (not _existing) or (
                abs(_existing[0] - _new_lat) > 1e-5 or abs(_existing[1] - _new_lon) > 1e-5
            )
            if _is_new_save:
                _save_sub_site_override(selected_park_id, _fs_pt["name"], _new_lat, _new_lon)
                st.cache_data.clear()
                st.success(f"Position saved for {_fs_pt['name']} → {_new_lat:.5f}, {_new_lon:.5f}")
                st.rerun()
        _gmaps = f"https://www.google.com/maps/@{_fs_pt['lat']},{_fs_pt['lon']},17z/data=!3m1!1e3"
        _osm = f"https://www.openstreetmap.org/?mlat={_fs_pt['lat']}&mlon={_fs_pt['lon']}#map=16/{_fs_pt['lat']}/{_fs_pt['lon']}"
        _verified_tag = (
            '<span style="color:#84cc16; font-weight:600; margin-left:10px; '
            'background:rgba(132,204,22,0.15); padding:2px 8px; border-radius:4px; font-size:0.72rem;">'
            'VERIFIED BUILT</span>'
            if _fs_pt["is_verified_built"] else ""
        )
        st.markdown(
            f"""<div style="margin: 8px 0 4px; padding: 10px 14px;
              background: rgba(132, 204, 22, 0.05);
              border: 1px solid rgba(132, 204, 22, 0.25);
              border-radius: 8px;
              font-family: 'JetBrains Mono', monospace; font-size: 0.74rem;
              color: #cbd5e1; letter-spacing: 0.02em;">
              <span style="color: #84cc16; font-weight: 600;">{_fs_pt['name']}</span>{_verified_tag}
              &nbsp;·&nbsp; Co. {_fs_pt['county']} &nbsp;·&nbsp; {_fs_pt['capacity_mw']:.1f} MW &nbsp;·&nbsp;
              <code style="color: #f1f5f9; background: rgba(232, 228, 214, 0.08); padding: 1px 6px; border-radius: 3px;">{_fs_pt['lat']}, {_fs_pt['lon']}</code>
              <div style="margin-top: 6px; font-size: 0.72rem;">
                <a href="{_gmaps}" target="_blank" style="color: #7dd3fc; margin-right: 14px;">Open in Google Maps ↗</a>
                <a href="{_osm}" target="_blank" style="color: #7dd3fc;">OSM ↗</a>
              </div>
            </div>""",
            unsafe_allow_html=True,
        )

        # Toggle "Confirm built" / "Mark not built"
        _vbtn_cols = st.columns([3, 1])
        _verified_now = _fs_pt["is_verified_built"]
        _btn_label = "Mark not built" if _verified_now else "Confirm built"
        _btn_help = (
            "This site is currently flagged as visually confirmed built. "
            "Click to remove the flag if it was a mistake."
            if _verified_now else
            "After checking Google Maps satellite at the coords above and confirming you see the panel array, "
            "click this button. The site contributes to the 'Currently confirmed built' subset metrics, "
            "the marker turns green on the map, and the per-site table shows BUILT."
        )
        _vbtn_cols[0].caption(_btn_help)
        if _vbtn_cols[1].button(
            _btn_label,
            key=f"verify-built-{selected_park_id}-{_focused_idx_fs}",
            use_container_width=True,
            type=("primary" if not _verified_now else "secondary"),
        ):
            _toggle_sub_site_verified(selected_park_id, _fs_pt["name"])
            st.cache_data.clear()
            st.rerun()
    else:
        components.html(
            _build_satellite_html(
                lat=float(selected_row["lat"]),
                lon=float(selected_row["lon"]),
                label=selected_row["name"],
                sites_count=len(_sub_sites_payload_fs),
                sub_sites=_sub_sites_payload_fs,
                focused_sub_idx=None,
            ),
            height=400,
            scrolling=False,
        )

    st.stop()  # Skip Live / T12M / Backtest sections for forward-sale portfolios

# T12M rolling window — aligned to whole calendar months ending on the last
# COMPLETE month available (subject to Open-Meteo Archive ~5-day lag).
# This avoids the "partial-month" stub at both ends of the window that made
# the monthly bar chart look broken (e.g. Apr 25 with only 1 day of data).
import calendar as _cal
import datetime as _dt_mod

_today = _dt_mod.date.today()
_cutoff = _today - _dt_mod.timedelta(days=ARCHIVE_LAG_DAYS)

# Pick the last fully-available month
_last_day_of_cutoff_month = _cal.monthrange(_cutoff.year, _cutoff.month)[1]
if _cutoff.day >= _last_day_of_cutoff_month:
    # Cutoff IS at or past the last day of its month — use that month as end
    T12M_END = _dt_mod.date(_cutoff.year, _cutoff.month, _last_day_of_cutoff_month)
else:
    # Cutoff is mid-month — fall back to end of previous month
    _prev_m = _cutoff.month - 1
    _prev_y = _cutoff.year
    if _prev_m == 0:
        _prev_m = 12
        _prev_y -= 1
    T12M_END = _dt_mod.date(_prev_y, _prev_m, _cal.monthrange(_prev_y, _prev_m)[1])

# Start = first day of the month 11 months before T12M_END
_start_m = T12M_END.month + 1
_start_y = T12M_END.year - 1
if _start_m > 12:
    _start_m -= 12
    _start_y += 1
T12M_START = _dt_mod.date(_start_y, _start_m, 1)

# Same window 1 year before for year-on-year comparison
T12M_END_PREV = _dt_mod.date(T12M_END.year - 1, T12M_END.month, T12M_END.day)
T12M_START_PREV = _dt_mod.date(T12M_START.year - 1, T12M_START.month, T12M_START.day)

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
# Detail panel — common computations needed by Revenue, Historical, etc.
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
# Number of days in the window is dynamic (365 or 366 for leap years), derive from dates.
_yest = T12M_END  # last day in our data window
_n_days_t12m = (T12M_END - T12M_START).days + 1
_yest_idx_start = (_n_days_t12m - 1) * 24
_yest_idx_end = _n_days_t12m * 24
yesterday_kwh = sum(hourly_data["hourly_production_kwh"][_yest_idx_start:_yest_idx_end])
yesterday_mwh = yesterday_kwh / 1000.0

# Same calendar day 1 year before (from T12M_START_PREV window)
yest_prev_mwh = None
if period_data_prev:
    _n_days_prev = (T12M_END_PREV - T12M_START_PREV).days + 1
    prev_idx_start = (_n_days_prev - 1) * 24
    prev_idx_end = _n_days_prev * 24
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
# Park header
# ---------------------------------------------------------------------------

# Divested / failed-deal banner — render before the header
if _park_model_for_status and _park_model_for_status.divested:
    _banner_label = _park_model_for_status.divestment_label or "DIVESTED ASSET — HISTORICAL TRACEABILITY ONLY"
    st.markdown(
        f"""
        <div style="
          margin: 14px 0 10px; padding: 12px 16px;
          background: rgba(202, 138, 4, 0.06);
          border-left: 3px solid var(--severity-amber);
          border-radius: 4px;
          font-family: 'JetBrains Mono', monospace; font-size: 0.74rem;
          color: var(--text-secondary); line-height: 1.55;">
          <span style="color: var(--severity-amber); font-weight: 600; letter-spacing: 0.06em; text-transform: uppercase;">{_banner_label}</span>
          <div style="margin-top: 6px; color: var(--text-muted); font-size: 0.72rem;">
            {_park_model_for_status.divestment_note or "Allianz no longer owns this asset."}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

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
# Common pricing/FiT lookup — hoisted here so Live section (downstream)
# can use is_fit_locked, fit_price, etc. The full revenue calc runs later.
# ---------------------------------------------------------------------------

zone = get_zone(selected_row["country"], park_id=selected_park_id)
fallback_price = get_fallback_price(selected_park_id)
from src.lib.parks_loader import get_park_by_id as _get_park_for_fit2
from src.lib.electricity_prices import get_us_zone
from src.lib.electricity_prices_us import (
    fetch_caiso_period_prices,
    fetch_caiso_current_spot,
    park_currency,
    format_money,
    format_price,
)
_park_obj_for_fit = _get_park_for_fit2(selected_park_id)
fit_price = _park_obj_for_fit.fit_strike_price_eur_mwh if _park_obj_for_fit else None
fit_scheme = _park_obj_for_fit.fit_scheme if _park_obj_for_fit else None
fit_expiry = _park_obj_for_fit.fit_expiry_year if _park_obj_for_fit else None
is_fit_locked = fit_price is not None

# US RTO routing: gridstatus for CAISO (real hourly LMP). ERCOT MIS is locked
# behind login since 2025 — keep flat-fallback for Galloway with a clear note.
_us_zone = get_us_zone(selected_park_id)
_currency = park_currency(zone, _us_zone)  # 'USD' for US parks, 'EUR' otherwise
_is_us_caiso = _us_zone == "US-CAISO"
_is_us_ercot = _us_zone == "US-ERCOT"

# ---------------------------------------------------------------------------
# SATELLITE VIEW — Esri imagery zoomed on the panels
# ---------------------------------------------------------------------------

import re as _re_sat
from src.lib.parks_loader import get_park_by_id as _get_park_by_id
_sites_match = _re_sat.search(r"\((\d+)\s+sites?", selected_row["name"])
_sites_count = int(_sites_match.group(1)) if _sites_match else 1

# Look up the raw park model to access sub_sites if present
_park_model = _get_park_by_id(selected_park_id)
_sub_sites_payload = None
_sub_site_overrides_for_park: dict[str, list[float]] = {}
if _park_model and _park_model.sub_sites:
    _all_sub_overrides = _load_sub_site_overrides()
    _sub_site_overrides_for_park = _all_sub_overrides.get(selected_park_id, {})
    _sub_sites_payload = []
    for s in _park_model.sub_sites:
        _ov = _sub_site_overrides_for_park.get(s.name)
        _lat = float(_ov[0]) if _ov else s.lat
        _lon = float(_ov[1]) if _ov else s.lon
        _sub_sites_payload.append({
            "name": s.name,
            "county": s.county,
            "capacity_mw": s.capacity_mw,
            "lat": _lat,
            "lon": _lon,
            "is_overridden": _ov is not None,
            "original_lat": s.lat,
            "original_lon": s.lon,
        })

if _sub_sites_payload:
    _sat_caption = (
        _park_model.sub_sites_caption
        or f"Multi-site portfolio · {len(_sub_sites_payload)} known sub-sites — markers at commune-level GPS."
    )
elif _sites_count > 1:
    _sat_caption = (
        f"Multi-site portfolio · {_sites_count} sites distributed in this region. "
        f"Exact addresses are not public — markers are illustrative only, "
        f"placed inside a 25-km radius around the portfolio centroid."
    )
else:
    _sat_caption = "Esri World Imagery (Maxar, Earthstar Geographics) at the park's GPS coordinates."

st.markdown(
    f"""
    <div class="section-header">
      <span class="section-label">Satellite view</span>
      <span class="section-caption">{_sat_caption}</span>
    </div>
    """,
    unsafe_allow_html=True,
)

# Focus selector for portfolios with real sub_sites
_focus_key = f"sat-focus-{selected_park_id}"
_focused_idx: int | None = st.session_state.get(_focus_key)
if _sub_sites_payload:
    _per_row = 6
    _items: list[tuple[str, int | None]] = [("Overview", None)] + [
        (s["name"], i) for i, s in enumerate(_sub_sites_payload)
    ]
    for _row_start in range(0, len(_items), _per_row):
        _row = _items[_row_start : _row_start + _per_row]
        _cols = st.columns(_per_row)
        for _ci, (_label, _idx_val) in enumerate(_row):
            _btn_key = f"focus-btn-{selected_park_id}-{_idx_val if _idx_val is not None else 'all'}"
            _is_active = _focused_idx == _idx_val
            if _cols[_ci].button(
                _label,
                key=_btn_key,
                use_container_width=True,
                type=("primary" if _is_active else "secondary"),
            ):
                st.session_state[_focus_key] = _idx_val
                st.rerun()

# When a sub-site is focused, switch to the coord_picker component (dblclick → save).
# Otherwise render the full overview map with all 17 markers.
if _sub_sites_payload and _focused_idx is not None and 0 <= _focused_idx < len(_sub_sites_payload):
    _fs = _sub_sites_payload[_focused_idx]
    from src.components.coord_picker import coord_picker as _coord_picker

    _picker_label = f"{_fs['name']} · Co. {_fs['county']} · {_fs['capacity_mw']:.1f} MW"
    _new_coords = _coord_picker(
        lat=float(_fs["lat"]),
        lon=float(_fs["lon"]),
        label=_picker_label,
        height=420,
        key=f"sub-coord-picker-{selected_park_id}-{_focused_idx}",
    )
    if _new_coords:
        _new_lat, _new_lon = float(_new_coords[0]), float(_new_coords[1])
        _existing = _sub_site_overrides_for_park.get(_fs["name"])
        _is_new_save = (not _existing) or (
            abs(_existing[0] - _new_lat) > 1e-5 or abs(_existing[1] - _new_lon) > 1e-5
        )
        if _is_new_save:
            _save_sub_site_override(selected_park_id, _fs["name"], _new_lat, _new_lon)
            st.cache_data.clear()
            st.success(f"Position saved for {_fs['name']} → {_new_lat:.5f}, {_new_lon:.5f}")
            st.rerun()

    # Focus banner with site context + quick links + reset action
    _gmaps = f"https://www.google.com/maps/@{_fs['lat']},{_fs['lon']},17z/data=!3m1!1e3"
    _osm = f"https://www.openstreetmap.org/?mlat={_fs['lat']}&mlon={_fs['lon']}#map=16/{_fs['lat']}/{_fs['lon']}"
    _overpass = (
        "https://overpass-turbo.eu/?Q="
        + f"%5Bout%3Ajson%5D%5Btimeout%3A25%5D%3B%0Anwr%5B%22power%22%3D%22plant%22%5D%5B%22plant%3Asource%22%3D%22solar%22%5D%28around%3A8000%2C{_fs['lat']}%2C{_fs['lon']}%29%3B%0Aout+geom%3B"
    )
    _override_tag = (
        '<span style="color:#7dd3fc; font-size:0.7rem; margin-left:8px; '
        'background:rgba(125,211,252,0.12); padding:1px 6px; border-radius:3px;">corrected</span>'
        if _fs["is_overridden"] else ""
    )
    st.markdown(
        f"""
        <div style="
            margin: 8px 0 4px; padding: 10px 14px;
            background: rgba(132, 204, 22, 0.05);
            border: 1px solid rgba(132, 204, 22, 0.25);
            border-radius: 8px;
            font-family: 'JetBrains Mono', monospace; font-size: 0.74rem;
            color: #cbd5e1; letter-spacing: 0.02em;">
          <span style="color: #84cc16; font-weight: 600;">{_fs['name']}</span>{_override_tag}
          &nbsp;·&nbsp; Co. {_fs['county']} &nbsp;·&nbsp; {_fs['capacity_mw']:.1f} MW &nbsp;·&nbsp;
          <code style="color: #f1f5f9; background: rgba(232, 228, 214, 0.08); padding: 1px 6px; border-radius: 3px;">{_fs['lat']}, {_fs['lon']}</code>
          <div style="margin-top: 6px; font-size: 0.72rem;">
            <span style="color: #84cc16;">Double-click on the panels to save new coords.</span>
            <a href="{_gmaps}" target="_blank" style="color: #7dd3fc; margin-left: 14px; margin-right: 14px;">Open in Google Maps ↗</a>
            <a href="{_osm}" target="_blank" style="color: #7dd3fc; margin-right: 14px;">OSM ↗</a>
            <a href="{_overpass}" target="_blank" style="color: #7dd3fc;">Overpass query ↗</a>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if _fs["is_overridden"]:
        _r_cols = st.columns([5, 1])
        _r_cols[0].caption(
            f"Original commune coords: {_fs['original_lat']:.6f}, {_fs['original_lon']:.6f} — current is corrected."
        )
        if _r_cols[1].button(
            "Reset to original",
            key=f"reset-coord-{selected_park_id}-{_focused_idx}",
            use_container_width=True,
        ):
            _delete_sub_site_override(selected_park_id, _fs["name"])
            st.cache_data.clear()
            st.info(f"Position reset to original for {_fs['name']}")
            st.rerun()

else:
    # Overview mode — render all sub-sites at once
    components.html(
        _build_satellite_html(
            lat=float(selected_row["lat"]),
            lon=float(selected_row["lon"]),
            label=selected_row["name"],
            sites_count=_sites_count,
            sub_sites=_sub_sites_payload,
            focused_sub_idx=None,
        ),
        height=360,
        scrolling=False,
    )

# ---------------------------------------------------------------------------
# LIVE STATUS — current weather + estimated output + current spot price
# ---------------------------------------------------------------------------

live_weather = _fetch_live_weather_cached(
    float(selected_row["lat"]), float(selected_row["lon"])
)
live_zone = get_zone(selected_row["country"], park_id=selected_park_id)
live_spot = _fetch_live_spot_cached(live_zone) if live_zone else None

# Resolve park's local time + day/night state to disambiguate "Sun = 0 W/m²"
# from "data missing" — important for US parks where the user is often
# checking from EU daytime but the panels are still in pre-dawn dark.
_park_local_time = (live_weather or {}).get("time_iso", "")[:16] if live_weather else ""
_park_local_hour_label = _park_local_time[-5:] if _park_local_time else "—"
_is_night_at_park = bool(live_weather) and live_weather["ghi_w_m2"] < 5.0
_night_caption_extra = (
    f" — <b style='color:#fbbf24;'>before sunrise / night at park ({_park_local_hour_label} local)</b>, panels not producing."
    if _is_night_at_park else ""
)

_time_badge_color = "#eab308" if _is_night_at_park else "#a8a294"
_time_badge_state = "OFF" if _is_night_at_park else "ON"
_time_badge_html = (
    f'<span style="display:inline-flex; align-items:center; gap:10px; margin-left:18px; padding:4px 12px; '
    f'background:rgba(168,162,148,0.06); border:1px solid rgba(168,162,148,0.18); '
    f'border-radius:3px; font-family:\'JetBrains Mono\', monospace; font-size:0.78rem; '
    f'font-weight:500; color:{_time_badge_color}; letter-spacing:0.05em;">'
    f'<span style="font-size:0.6rem; opacity:0.7; letter-spacing:0.18em;">PARK LOCAL</span>'
    f'<span style="font-feature-settings:\'tnum\'; font-size:0.92rem; font-weight:500;">{_park_local_hour_label}</span>'
    f'<span style="font-size:0.62rem; padding:1px 5px; background:rgba({"234,179,8" if _is_night_at_park else "168,162,148"},0.15); '
    f'border-radius:2px; letter-spacing:0.1em;">{_time_badge_state}</span>'
    f'</span>'
)
st.markdown(
    f"""
    <div class="section-header section-first section-live">
      <span class="section-label">Live · right now</span>{_time_badge_html}
      <span class="section-caption">
        Weather refreshed every 15 min (Open-Meteo) · spot price from ENTSO-E day-ahead.{_night_caption_extra}
      </span>
    </div>
    """,
    unsafe_allow_html=True,
)

l1, l2, l3, l4, l5 = st.columns(5)

if live_weather:
    cloud = live_weather["cloud_cover_pct"]
    cloud_label = "clear" if cloud < 25 else ("partly" if cloud < 75 else "overcast")
    if _is_night_at_park:
        sun_delta = f"night at park ({_park_local_hour_label})"
    else:
        sun_delta = cloud_label
    l1.metric(
        "Sun (live)",
        f"{live_weather['ghi_w_m2']:,.0f} W/m²",
        delta=sun_delta,
        delta_color="off",
        help=(
            f"Global Horizontal Irradiance at the park's GPS coords, refreshed every 15 min by Open-Meteo. "
            f"Park local time: {_park_local_hour_label}. Cloud cover {cloud:.0f}%. "
            + (
                "GHI is near zero because it's nighttime at the park. "
                "When you're checking from Europe (e.g. 14:00 CET), Texas is at ~06:00 (just after sunrise), "
                "California at ~04:00 (still dark) — solar panels physically cannot produce. "
                "The Time series chart below shows historical T12M production (sun-related but past data) "
                "so don't be confused: time series independent of current hour."
                if _is_night_at_park else
                "Open-Meteo aggregates ECMWF + GFS + Meteo-France etc., updates every ~15 min."
            )
        ),
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
_live_fallback_price = get_fallback_price(selected_park_id)

# Park timezone resolution. Country code → IANA TZ; US parks need an
# override since CA (Pacific) and TX (Central) share country "US".
_COUNTRY_TZ = {
    "IT": "Europe/Rome",
    "PT": "Europe/Lisbon",
    "FR": "Europe/Paris",
    "ES": "Europe/Madrid",
}
_PARK_TZ_OVERRIDE = {
    "lotus-solar-farm": "America/Los_Angeles",
    "galloway-2": "America/Chicago",
}
_park_tz_name = _PARK_TZ_OVERRIDE.get(selected_park_id) or _COUNTRY_TZ.get(
    selected_row["country"], "UTC"
)


def _local_time_str(iso_utc: str, tz_name: str = _park_tz_name) -> str:
    """Convert a UTC ISO timestamp to 'HH:MM TZABBR' in the park's local timezone.

    Always renders in the asset's local time (Europe/Rome for Manzano, etc.).
    The TZ abbreviation (CEST/CET/PDT/CDT) makes the timezone explicit without
    leaking UTC into the UI.
    """
    if not iso_utc:
        return "—"
    try:
        from datetime import datetime as _dt_loc
        from zoneinfo import ZoneInfo
        dt_utc = _dt_loc.fromisoformat(iso_utc.replace("Z", "+00:00"))
        local = dt_utc.astimezone(ZoneInfo(tz_name))
        abbr = local.strftime("%Z") or tz_name.split("/")[-1]
        return f"{local.strftime('%H:%M')} {abbr}"
    except (ValueError, TypeError, Exception):
        return iso_utc[11:16] if len(iso_utc) >= 16 else iso_utc


# Italian Conto Energia: dual revenue (state-paid FiT + wholesale market sale).
# Show the COMBINED €/MWh and revenue/h, refreshed every 15 min via live spot.
if is_fit_locked:
    spot_addon = 0.0
    spot_addon_label = "FiT only (spot unavailable)"
    spot_time_label = ""
    if live_spot and live_spot.get("price_eur_mwh") is not None:
        spot_addon = live_spot["price_eur_mwh"]
        spot_time_label = _local_time_str(live_spot.get("time_iso", ""))
        spot_addon_label = f"+ {spot_addon:.0f} spot @ {spot_time_label}"
    total_price_now = fit_price + spot_addon
    l4.metric(
        "Realised €/MWh (FiT + spot)",
        f"{total_price_now:.0f} €/MWh",
        delta=spot_addon_label,
        delta_color="off",
        help=(
            f"Italian Conto Energia plants >1 MW receive TWO payments per MWh produced: "
            f"(1) a state-secured incentive of €{fit_price:.0f}/MWh, locked until {fit_expiry}, "
            f"plus (2) the wholesale market sale at the current zonal spot. "
            f"Right now: FiT €{fit_price:.0f}/MWh + spot €{spot_addon:.0f}/MWh "
            f"= total €{total_price_now:.0f}/MWh. Spot refreshes every 15 min."
        ),
    )
    if live_weather:
        revenue_now = estimated_mw * total_price_now
        l5.metric(
            "Revenue/h (live)",
            f"€ {revenue_now:,.0f}",
            delta=f"@ {total_price_now:.0f} €/MWh",
            delta_color="off",
            help=(
                f"Live output ({estimated_mw:.2f} MW) × realised price (FiT + current spot, "
                f"€{total_price_now:.0f}/MWh). Updates every 15 min."
            ),
        )
    else:
        l5.metric("Revenue/h (live)", "—")
elif live_spot and live_spot.get("price_eur_mwh") is not None:
    spot_price = live_spot["price_eur_mwh"]
    spot_context = interpret_spot_price(spot_price, live_zone)
    _spot_time_label = _local_time_str(live_spot.get("time_iso", ""))
    l4.metric(
        "Spot price (live)",
        f"{spot_price:,.1f} €/MWh",
        delta=spot_context["label"],
        delta_color="off",
        help=(
            f"Day-ahead zone {live_zone}, settled slot at {_spot_time_label}. "
            "Source: energy-charts.info (ENTSO-E mirror). Refreshed every 15 min, slots are 15-min wide since Oct 2025."
        ),
    )
    if live_weather:
        revenue_now = estimated_mw * spot_price
        l5.metric(
            "Revenue/h (live)",
            f"€ {revenue_now:,.0f}",
            delta=f"@ {spot_price:.0f} €/MWh",
            delta_color="off",
            help=(
                f"Live output ({estimated_mw:.2f} MW) × current spot ({spot_price:.1f} €/MWh) × 1 hour. "
                "Updates every 15 min."
            ),
        )
    else:
        l5.metric("Revenue/h (live)", "—")
elif _is_us_caiso:
    # CAISO SP15 (Lotus) — real LMP via gridstatus.OASIS, USD native
    @st.cache_data(ttl=900, show_spinner=False)
    def _fetch_caiso_live_cached(zone: str) -> dict | None:
        return fetch_caiso_current_spot(zone)

    caiso_live = _fetch_caiso_live_cached(_us_zone)
    if caiso_live and caiso_live.get("price_usd_mwh") is not None:
        usd_spot = caiso_live["price_usd_mwh"]
        l4.metric(
            "Spot price (CAISO SP15)",
            f"$ {usd_spot:,.1f}/MWh",
            delta=caiso_live["time_iso"][:16].replace("T", " "),
            delta_color="off",
            help=(
                f"Real day-ahead LMP at trading hub TH_SP15_GEN-APND, fetched live via gridstatus.OASIS. "
                f"Settlement timestamp: {caiso_live['time_iso']}. CAISO publishes the next-day market "
                "around 13:00 PT, so the most recent settled hour is shown."
            ),
        )
        if live_weather:
            revenue_now = estimated_mw * usd_spot
            l5.metric(
                "Revenue/h (live est.)",
                f"$ {revenue_now:,.0f}",
                help="Live output × current CAISO SP15 LMP × 1 hour. Real wholesale exposure (Lotus has a 20-yr PPA with SCE — actual cash flow is locked at PPA strike, not spot).",
            )
        else:
            l5.metric("Revenue/h (live est.)", "—")
    else:
        # CAISO fetch failed (transient OASIS outage) → show "—" honestly.
        l4.metric(
            "Spot price (CAISO SP15)",
            "—",
            delta="OASIS unavailable",
            delta_color="off",
            help=(
                "CAISO OASIS public endpoint did not return data on this query — could be a transient "
                "rate-limit or OASIS outage. Try refreshing the page in a few minutes. "
                "No flat proxy shown to avoid misleading numbers."
            ),
        )
        l5.metric("Revenue/h", "—", help="Spot price unavailable — see tooltip.")
elif _is_us_ercot:
    # ERCOT West Hub (Galloway) — public MIS auth-walled since 2025.
    # No reliable hourly LMP without a registered account → show "—" honestly.
    l4.metric(
        "Spot price (ERCOT)",
        "—",
        delta="data unavailable",
        delta_color="off",
        help=(
            "ERCOT public MIS was retired in 2025 — hourly LMP at HB_WEST now requires a registered "
            "ERCOT account. Until credentials are configured for gridstatus, no live spot is shown "
            "rather than a misleading flat proxy. "
            "Asset note: Galloway 2 has a long-term PPA with EDF Energy Services for the BASF Freeport "
            "site — actual revenue is locked at the contracted PPA strike, not the wholesale spot."
        ),
    )
    l5.metric("Revenue/h", "—", help="Spot price unavailable for ERCOT — see Spot price tooltip.")
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
            {title}
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
        from zoneinfo import ZoneInfo as _ZI
        _park_tz = _ZI(_park_tz_name)
        ts_list = today_curve["timestamps"]
        prices_list = today_curve["prices"]
        # Convert UTC timestamps to park-local naive datetimes so Plotly renders
        # the x-axis directly in the asset's local hours (no UTC labels anywhere).
        x_dates = [
            _dt2.datetime.fromtimestamp(t, _dt2.timezone.utc).astimezone(_park_tz).replace(tzinfo=None)
            for t in ts_list
        ]

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
                hovertemplate="%{x|%H:%M} · %{y:,.1f} €/MWh<extra></extra>",
                name="Spot",
            )
        )
        # Zero line
        fig_today.add_hline(
            y=0, line_dash="dot", line_color="rgba(232, 228, 214, 0.3)", line_width=1
        )
        # Mark current hour (in park local time)
        if live_spot:
            now_local = _dt2.datetime.now(_dt2.timezone.utc).astimezone(_park_tz).replace(tzinfo=None)
            fig_today.add_trace(
                go.Scatter(
                    x=[now_local],
                    y=[live_spot["price_eur_mwh"]],
                    mode="markers",
                    marker=dict(size=10, color="#84cc16", line=dict(color="#0a0a0a", width=2)),
                    hovertemplate="now · %{y:,.1f} €/MWh<extra></extra>",
                    name="Now",
                )
            )

        fig_today.update_layout(
            title=dict(
                text=f"Today's spot curve · zone {live_zone} · {_park_tz_name.split('/')[-1].replace('_', ' ')} time",
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
# PRODUCTION TODAY — cumulative MWh since sunrise
# ---------------------------------------------------------------------------

st.markdown(
    """
    <div class="section-header">
      <span class="section-label">Production today</span>
      <span class="section-caption">
        Hourly output reconstructed from Open-Meteo today's GHI + temp at the park's coords,
        passed through the same pvlib-style estimator used for the live MW. Cumulative MWh
        since sunrise, plus the hour-by-hour bars so you can see today's curve develop.
      </span>
    </div>
    """,
    unsafe_allow_html=True,
)

@st.cache_data(ttl=600, show_spinner=False)
def _fetch_today_hourly_cached(lat: float, lon: float) -> dict | None:
    from src.lib.live_weather import fetch_today_hourly_weather
    return fetch_today_hourly_weather(lat, lon)

_today_hw = _fetch_today_hourly_cached(float(selected_row["lat"]), float(selected_row["lon"]))
if _today_hw and _today_hw.get("timestamps"):
    from src.lib.live_weather import estimate_current_output_mw as _est_mw
    _ts_today = _today_hw["timestamps"]
    _ghi_today = _today_hw["ghi_w_m2"]
    _temp_today = _today_hw["temp_c"]
    _is_past = _today_hw["is_past"]
    _cap = float(selected_row["capacity_mwp"])
    _hourly_mw_today = []
    for i in range(len(_ts_today)):
        if _is_past[i]:
            mw = _est_mw(capacity_mwp=_cap, ghi_w_m2=_ghi_today[i], temp_c=_temp_today[i])
            _hourly_mw_today.append(mw)
        else:
            _hourly_mw_today.append(0.0)
    _cum_mwh_today = sum(_hourly_mw_today)  # MW × 1h = MWh
    _sunrise_idx = next((i for i, mw in enumerate(_hourly_mw_today) if mw > 0.05), None)
    _sunrise_label = _ts_today[_sunrise_idx][-5:] if _sunrise_idx is not None else "—"
    _hours_since_sunrise = sum(1 for i, mw in enumerate(_hourly_mw_today) if i >= (_sunrise_idx or 0) and _is_past[i])

    pt1, pt2, pt3 = st.columns([1, 1, 2])
    pt1.metric(
        "Output today",
        f"{_cum_mwh_today:.1f} MWh",
        help=(
            f"Cumulative production since sunrise ({_sunrise_label}). "
            f"Reconstructed from Open-Meteo hourly GHI/temp at the park\'s coords using the "
            "same pvlib-style estimator as the live MW metric. Resets at midnight local time."
        ),
    )
    pt2.metric(
        "Sunrise (local)",
        _sunrise_label,
        delta=f"{_hours_since_sunrise} h ago" if _hours_since_sunrise else None,
        delta_color="off",
        help="Local timezone of the park. First hour where estimated output > 0.05 MW today.",
    )
    # Bar chart of today's hourly output
    import pandas as _pdpt
    _df_today = _pdpt.DataFrame({
        "hour": [t[-5:] for t in _ts_today],
        "mw": _hourly_mw_today,
        "is_past": _is_past,
    })
    fig_today_prod = go.Figure()
    fig_today_prod.add_trace(go.Bar(
        x=_df_today["hour"],
        y=[mw if past else 0 for mw, past in zip(_df_today["mw"], _df_today["is_past"])],
        marker=dict(color="#e8e4d6"),
        name="Hours past",
        hovertemplate="%{x} · %{y:.2f} MW<extra></extra>",
    ))
    fig_today_prod.update_layout(
        title=dict(
            text="Today\'s hourly output (estimated)",
            font=dict(color="#cbd5e1", size=12, family="Geist", weight=500),
            x=0.0, xanchor="left", pad=dict(b=4),
        ),
        height=160,
        margin=dict(l=0, r=0, t=32, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(showgrid=False, tickfont=dict(color="#7a7464", size=9, family="JetBrains Mono")),
        yaxis=dict(gridcolor="rgba(232, 228, 214, 0.06)", tickfont=dict(color="#7a7464", size=9, family="JetBrains Mono"), title=None, ticksuffix=" MW"),
        showlegend=False,
        hoverlabel=dict(bgcolor="rgba(13, 13, 13, 0.95)", bordercolor="rgba(232, 228, 214, 0.4)", font=dict(color="#f1f5f9", family="JetBrains Mono", size=11)),
    )
    pt3.plotly_chart(fig_today_prod, width="stretch", config={"displayModeBar": False})
else:
    st.info("Today\'s hourly weather unavailable — Production today section requires Open-Meteo forecast endpoint.")

st.markdown('<div class="vspace"></div>', unsafe_allow_html=True)
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
# REVENUE · YEAR 2023 — historical production × historical prices
# ---------------------------------------------------------------------------

# zone, fallback_price, fit_*, is_fit_locked already hoisted above (before Live section)
revenue_metrics: dict = {}
revenue_source = ""
period_prices: dict | None = None
fit_revenue_eur = 0.0
spot_revenue_eur = 0.0
spot_realized_price = None  # production-weighted spot avg (for cannibalisation calc)
spot_simple_avg = None      # time-weighted spot avg (for day-ahead reference)
spot_hours_covered = 0

@st.cache_data(ttl=86400, show_spinner=False)
def _fetch_period_prices_cached(zone: str, start_iso: str, end_iso: str) -> dict | None:
    return fetch_period_prices(zone, start_iso, end_iso)

# Fetch zonal spot prices (used both for spot-only revenue and FiT+spot dual-revenue)
if zone:
    period_prices = _fetch_period_prices_cached(zone, T12M_START.isoformat(), T12M_END.isoformat())

# Priority 1 : Italian FiT-locked asset (Conto Energia >1 MW) — DUAL revenue:
#   incentive tariff (FiT) PAID BY STATE on every MWh
#   PLUS market sale of energy at zonal hourly spot price
# Total = FiT × prod + spot_h × prod_h (each hour)
if is_fit_locked:
    hk = hourly_data["hourly_production_kwh"]
    total_kwh = sum(hk)
    fit_revenue_eur = (total_kwh / 1000.0) * fit_price  # MWh × €/MWh

    if period_prices and period_prices.get("prices_eur_mwh"):
        # Map hourly production to spot prices via timestamp matching
        spot_ts = period_prices["timestamps"]
        spot_p = period_prices["prices_eur_mwh"]
        spot_lookup = {ts: p for ts, p in zip(spot_ts, spot_p) if p is not None}
        prod_ts_iso = hourly_data["timestamps"]
        import datetime as _dtfit
        valid_spot_prices = []
        spot_weighted_sum = 0.0
        spot_weighted_prod_kwh = 0.0
        for i, ts_iso in enumerate(prod_ts_iso):
            if i >= len(hk): break
            try:
                ts_int = int(_dtfit.datetime.fromisoformat(ts_iso.replace("Z", "+00:00")).timestamp())
                ts_hour = ts_int - (ts_int % 3600)
                p = spot_lookup.get(ts_hour)
                if p is not None:
                    spot_weighted_sum += hk[i] / 1000.0 * p  # MWh × €/MWh
                    spot_weighted_prod_kwh += hk[i]
                    valid_spot_prices.append(p)
            except (ValueError, AttributeError):
                continue
        spot_revenue_eur = spot_weighted_sum
        spot_hours_covered = len(valid_spot_prices)
        if spot_weighted_prod_kwh > 0:
            spot_realized_price = spot_weighted_sum / (spot_weighted_prod_kwh / 1000.0)
        if valid_spot_prices:
            spot_simple_avg = sum(valid_spot_prices) / len(valid_spot_prices)

    total_revenue_eur = fit_revenue_eur + spot_revenue_eur
    total_mwh = total_kwh / 1000.0
    revenue_metrics = {
        "annual_revenue_eur": total_revenue_eur,
        "effective_price_eur_mwh": (total_revenue_eur / total_mwh) if total_mwh else 0.0,
        "avg_dayahead_price_eur_mwh": spot_simple_avg or 0.0,
        "cannibalization_pct": (
            ((spot_realized_price - spot_simple_avg) / spot_simple_avg * 100.0)
            if (spot_realized_price is not None and spot_simple_avg)
            else 0.0
        ),
    }
    coverage_pct = (spot_hours_covered / max(len(hk), 1)) * 100.0
    revenue_source = (
        f"FiT €{fit_price:.0f}/MWh ({fit_scheme.split('—')[0].strip() if fit_scheme else 'FiT'}, expires {fit_expiry}) "
        f"+ market sale at {zone or 'zone N/A'} hourly spot ({spot_hours_covered:,}/{len(hk):,} hours covered, {coverage_pct:.0f}%)"
    )

# Priority 2 : zonal hourly day-ahead prices only (merchant solar, no FiT)
elif zone and period_prices and period_prices.get("prices_eur_mwh"):
    revenue_metrics = compute_revenue_metrics(
        hourly_production_kwh=hourly_data["hourly_production_kwh"],
        hourly_prices_eur_mwh=period_prices["prices_eur_mwh"],
    )
    revenue_source = f"hourly day-ahead zone {zone}"

# Priority 2b : CAISO real hourly LMP via gridstatus (USD native)
@st.cache_data(ttl=86400, show_spinner=False)
def _fetch_caiso_period_cached(zone: str, start_iso: str, end_iso: str) -> dict | None:
    return fetch_caiso_period_prices(
        zone,
        _dt_mod.date.fromisoformat(start_iso),
        _dt_mod.date.fromisoformat(end_iso),
    )

us_caiso_data = None
if not revenue_metrics and _is_us_caiso:
    us_caiso_data = _fetch_caiso_period_cached(_us_zone, T12M_START.isoformat(), T12M_END.isoformat())
    if us_caiso_data and us_caiso_data.get("prices_usd_mwh"):
        # Build hourly_prices array aligned to production timestamps
        usd_lookup = {ts: p for ts, p in zip(us_caiso_data["timestamps"], us_caiso_data["prices_usd_mwh"]) if p is not None}
        hk = hourly_data["hourly_production_kwh"]
        prod_ts_iso = hourly_data["timestamps"]
        import datetime as _dtu
        spot_weighted_sum = 0.0
        spot_weighted_prod_kwh = 0.0
        valid_prices = []
        for i, ts_iso in enumerate(prod_ts_iso):
            if i >= len(hk): break
            try:
                ts_int = int(_dtu.datetime.fromisoformat(ts_iso.replace("Z", "+00:00")).timestamp())
                ts_hour = ts_int - (ts_int % 3600)
                p = usd_lookup.get(ts_hour)
                if p is not None:
                    spot_weighted_sum += (hk[i] / 1000.0) * p
                    spot_weighted_prod_kwh += hk[i]
                    valid_prices.append(p)
            except (ValueError, AttributeError):
                continue
        total_revenue_usd = spot_weighted_sum
        total_mwh = sum(hk) / 1000.0
        sp_realized = (spot_weighted_sum / (spot_weighted_prod_kwh / 1000.0)) if spot_weighted_prod_kwh else 0.0
        sp_simple = (sum(valid_prices) / len(valid_prices)) if valid_prices else 0.0
        revenue_metrics = {
            "annual_revenue_eur": total_revenue_usd,  # field reused; UI knows currency
            "effective_price_eur_mwh": sp_realized,
            "avg_dayahead_price_eur_mwh": sp_simple,
            "cannibalization_pct": ((sp_realized - sp_simple) / sp_simple * 100.0) if sp_simple else 0.0,
        }
        coverage_pct = (len(valid_prices) / max(len(hk), 1)) * 100.0
        revenue_source = (
            f"CAISO SP15 hourly day-ahead LMP via gridstatus.OASIS "
            f"({len(valid_prices):,}/{len(hk):,} hours covered, {coverage_pct:.0f}%) — USD native"
        )

# Priority 3 : last-resort flat fallback (rarely needed — only if a non-US, non-FiT, non-zonal park appears)
if not revenue_metrics and fallback_price is not None and not _is_us_ercot and not _is_us_caiso:
    flat_prices = [fallback_price] * len(hourly_data["hourly_production_kwh"])
    revenue_metrics = compute_revenue_metrics(
        hourly_production_kwh=hourly_data["hourly_production_kwh"],
        hourly_prices_eur_mwh=flat_prices,
    )
    revenue_source = f"flat annual avg ({fallback_price:.0f} €/MWh) — hourly data not available"

# Honest empty state for ERCOT (auth-walled)
if not revenue_metrics and _is_us_ercot:
    _revenue_caption = (
        "ERCOT public MIS auth-walled since 2025 — hourly LMP at HB_WEST not available without registered account. "
        "Revenue not computed (avoiding misleading proxy). Galloway 2 has a long-term PPA with EDF Energy Services — "
        "actual cash flow is locked at PPA strike, not wholesale spot."
    )
else:
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
    _revenue_amount = revenue_metrics["annual_revenue_eur"] / 1_000_000
    r1.metric(
        "Total revenue (T12M)",
        format_money(_revenue_amount, _currency, m_suffix=True),
        help=(
            f"Total earned over the last 12 months. Italian utility-scale plants (>1 MW) under "
            f"Conto Energia receive a DUAL revenue: (1) State-paid feed-in incentive at €{fit_price:.0f}/MWh on every "
            f"MWh produced (until {fit_expiry}), PLUS (2) sale of the same energy on the wholesale market at zonal "
            f"hourly spot price. Total = FiT × production + Σ(production_h × spot_h). "
            f"FiT portion: €{fit_revenue_eur/1_000_000:.2f} M (locked). Spot sale portion: €{spot_revenue_eur/1_000_000:.2f} M (variable)."
            if is_fit_locked else
            f"Total earned over the last 12 months. "
            f"Computed by summing, for each hour : production_MWh × spot_price ({_currency}/MWh). "
            "Captures actual market conditions hour by hour."
        ),
    )
    r2.metric(
        "Effective price (T12M)" + (" — FiT+spot" if is_fit_locked else ""),
        format_price(revenue_metrics["effective_price_eur_mwh"], _currency),
        help=(
            f"FiT strike + production-weighted realised spot. = Total revenue / total production_MWh. "
            f"Breakdown: €{fit_price:.0f}/MWh fixed FiT incentive (paid by State, until {fit_expiry}) "
            + (f"+ €{spot_realized_price:.1f}/MWh from market sale (production-weighted = post-cannibalisation)." if spot_realized_price is not None else "+ market sale data unavailable.")
            if is_fit_locked else
            "The price actually realised on each MWh sold, weighted by when production happened. "
            "Formula : total_revenue / total_production_mwh. "
            "Differs from the simple market average because the park doesn't produce evenly — it produces a lot at midday "
            "(when prices are pushed down by solar oversupply) and nothing at night (when prices spike). "
            "This is the asset's true revenue per MWh — what really lands on the cash flow."
        ),
    )
    if is_fit_locked:
        # Show market sale spot avg + cannibalisation (applies to spot portion only)
        if spot_simple_avg is not None and spot_realized_price is not None:
            r3.metric(
                "Spot day-ahead avg",
                f"{spot_simple_avg:.1f} €/MWh",
                delta=f"realised on prod: {spot_realized_price:.1f}",
                delta_color="off",
                help=(
                    f"Simple time-average of zone {zone} hourly day-ahead spot prices over the {spot_hours_covered:,} hours covered. "
                    f"The 'realised on prod' delta shows the production-weighted average ({spot_realized_price:.1f} €/MWh) — "
                    f"what the plant actually earned per MWh on the SPOT portion of its revenue (not counting FiT). "
                    "Lower than the simple average because solar concentrates production in low-price hours (cannibalisation)."
                ),
            )
            cann_spot = (spot_realized_price - spot_simple_avg) / spot_simple_avg * 100.0
            r4.metric(
                "Spot cannibalisation",
                f"{cann_spot:+.1f} %",
                help=(
                    "Cannibalisation on the SPOT portion of revenue only. "
                    "FiT portion (~€" + f"{fit_price:.0f}" + "/MWh) is locked and NOT cannibalised — paid on every MWh regardless of hour. "
                    f"Spot side captures Italian solar penetration effect: realised €{spot_realized_price:.1f}/MWh vs simple avg €{spot_simple_avg:.1f}/MWh. "
                    "When FiT expires, total revenue drops to spot-only and cannibalisation becomes the entire risk."
                ),
            )
        else:
            r3.metric("Spot day-ahead avg", "—", help=(
                f"Wholesale spot data unavailable for zone {zone or '—'} on this T12M window. "
                "energy-charts.info has limited Italian zone coverage (IT-North data only from Oct 2025). "
                "Total revenue shown is FiT-only — actual revenue is higher (FiT + market sale) but missing market data."
            ))
            r4.metric("Spot cannibalisation", "N/A", help="Spot data unavailable.")
    else:
        r3.metric(
            "Day-ahead avg (T12M)",
            format_price(revenue_metrics["avg_dayahead_price_eur_mwh"], _currency),
            help=(
                f"Simple arithmetic mean of all hourly day-ahead market prices on the asset's bidding zone, in {_currency}/MWh. "
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
