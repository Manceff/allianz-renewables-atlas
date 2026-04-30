"""Atlas — landing page solaire ACP.

Globe terrestre orthographique sur fond starfield, markers cliquables
sur les 11 parcs solaires Allianz Capital Partners cartographiés
publiquement entre 2010 et 2026.

Click (selectbox) sur un parc → panel détail avec :
- Terminal data (production du jour, ensoleillement, delta vs reported)
- Heatmap 365×24 (saisonnalité × profil journalier)
- Bar chart 12 mois (estimé + reported)
- Capacity factor mensuel
- Intervalle de confiance (loss 10/14/18%)

Style : JARVIS / Tesla console — dark navy, accent cyan, glass panels.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

# Streamlit ajoute src/ à sys.path mais pas la racine ; on l'ajoute pour `from src.lib.X`
_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.lib.confidence_interval import compute_pvgis_range
from src.lib.parks_loader import load_parks_index
from src.lib.pvgis_fetch import fetch_pvgis_hourly
from src.lib.reported_production import load_reported_production
from src.lib.solar_metrics import (
    capacity_factor_annual,
    capacity_factor_monthly,
    estimate_for_date,
    hourly_heatmap_matrix,
    monthly_aggregates,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Page config + CSS injection
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Atlas — Allianz Renewables",
    page_icon="🌍",
    layout="wide",
    initial_sidebar_state="collapsed",
)

CSS_PATH = Path(__file__).resolve().parent.parent / "assets" / "style.css"
if CSS_PATH.exists():
    st.markdown(f"<style>{CSS_PATH.read_text()}</style>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PORTFOLIO_SWEEP_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "portfolio_sweep.json"

SEVERITY_COLORS = {
    "green": "#10b981",
    "yellow": "#facc15",
    "red": "#f87171",
    "none": "#64748b",
}

MONTH_NAMES_FR = ["Jan", "Fév", "Mar", "Avr", "Mai", "Juin", "Juil", "Août", "Sep", "Oct", "Nov", "Déc"]


# ---------------------------------------------------------------------------
# Data loaders (cached)
# ---------------------------------------------------------------------------


@st.cache_data
def _load_parks_df() -> pd.DataFrame:
    idx = load_parks_index()
    rows = []
    for p in idx.parks:
        rows.append(
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
                "notes": p.notes or "",
            }
        )
    return pd.DataFrame(rows)


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
    """Return park_id → {annual_mwh, year, source_url}."""
    rep = load_reported_production()
    return {pid: r.model_dump(mode="json") for pid, r in rep.items()}


@st.cache_data(ttl=86400, show_spinner=False)
def _fetch_hourly_cached(
    park_id: str, lat: float, lon: float, peakpower_mw: float
) -> dict:
    """Wrapper cached pour fetch_pvgis_hourly. Park_id pour invalidation."""
    return fetch_pvgis_hourly(lat=lat, lon=lon, peakpower_mw=peakpower_mw)


@st.cache_data(ttl=86400, show_spinner=False)
def _fetch_ci_cached(park_id: str, lat: float, lon: float, peakpower_mw: float):
    """Wrapper cached pour compute_pvgis_range."""
    return compute_pvgis_range(lat=lat, lon=lon, peakpower_mw=peakpower_mw)


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

st.markdown(
    """
    <div style="text-align: center; padding: 1.5rem 0 0.5rem;">
        <h1 style="margin: 0; font-size: 2.2rem; color: #f1f5f9;">
            🌍 Allianz Renewables Atlas
        </h1>
        <p style="color: #94a3b8; font-size: 0.95rem; margin-top: 0.25rem;">
            Cartographie publique des parcs solaires détenus directement par
            Allianz Capital Partners · 2010-2026
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

parks_df = _load_parks_df()
severity_map = _load_severity_map()
reported_map = _load_reported()

# ---------------------------------------------------------------------------
# Top metrics
# ---------------------------------------------------------------------------

c1, c2, c3, c4 = st.columns(4)
c1.metric("Parcs solaires", f"{len(parks_df)}")
c2.metric("Capacité installée", f"{parks_df['capacity_mwp'].sum():,.0f} MWp")
c3.metric("Pays couverts", f"{parks_df['country'].nunique()}")
c4.metric("Avec delta calculé", f"{len(reported_map)}/{len(parks_df)}")

st.markdown("<br>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Globe — Plotly orthographic
# ---------------------------------------------------------------------------

parks_df["severity"] = parks_df["id"].map(severity_map).fillna("none")
parks_df["color"] = parks_df["severity"].map(SEVERITY_COLORS)
parks_df["marker_size"] = parks_df["capacity_mwp"].clip(lower=15, upper=80)

fig = px.scatter_geo(
    parks_df,
    lat="lat",
    lon="lon",
    size="marker_size",
    color="severity",
    color_discrete_map=SEVERITY_COLORS,
    hover_name="name",
    hover_data={
        "country": True,
        "capacity_mwp": ":.1f",
        "operator": True,
        "commissioning_year": True,
        "lat": False,
        "lon": False,
        "marker_size": False,
        "severity": False,
        "color": False,
    },
    projection="orthographic",
)

fig.update_geos(
    showland=True,
    landcolor="#1e3a5f",
    showocean=True,
    oceancolor="#0a0e1a",
    showcountries=True,
    countrycolor="rgba(125, 211, 252, 0.2)",
    showcoastlines=True,
    coastlinecolor="rgba(125, 211, 252, 0.3)",
    showframe=False,
    bgcolor="rgba(0,0,0,0)",
    projection_rotation=dict(lon=5, lat=35, roll=0),
)

fig.update_layout(
    height=560,
    margin=dict(l=0, r=0, t=0, b=0),
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    showlegend=False,
)

# Markers : halo lumineux (line: cyan glow)
fig.update_traces(marker=dict(line=dict(width=1.5, color="rgba(125, 211, 252, 0.6)")))

st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

# ---------------------------------------------------------------------------
# Park selector + Detail panel
# ---------------------------------------------------------------------------

st.markdown("<br>", unsafe_allow_html=True)


def _label(row) -> str:
    sev = row["severity"]
    badge = {"green": "🟢", "yellow": "🟡", "red": "🔴", "none": "⚪"}[sev]
    return f"{badge}  {row['name']}  ·  {row['country']}  ·  {row['capacity_mwp']:.1f} MWp"


parks_df["_label"] = parks_df.apply(_label, axis=1)

selected_label = st.selectbox(
    "Sélectionne un parc pour voir son analyse détaillée",
    options=["—"] + parks_df["_label"].tolist(),
    index=0,
)

if selected_label == "—":
    st.markdown(
        """
        <div style="text-align: center; color: #64748b; padding: 2rem 0; font-style: italic;">
            ↑ Sélectionne un parc dans la liste pour ouvrir son analyse fine
            (production estimée, saisonnalité, capacity factor, intervalle de confiance).
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.stop()

selected_row = parks_df[parks_df["_label"] == selected_label].iloc[0]
park_id = selected_row["id"]

# ---------------------------------------------------------------------------
# Detail panel — fetch PVGIS data
# ---------------------------------------------------------------------------

with st.spinner(f"Calcul PVGIS pour {selected_row['name']} (TMY 2019)…"):
    try:
        hourly_data = _fetch_hourly_cached(
            park_id=park_id,
            lat=selected_row["lat"],
            lon=selected_row["lon"],
            peakpower_mw=selected_row["capacity_mwp"],
        )
    except Exception as e:
        st.error(f"⚠️ PVGIS seriescalc a échoué pour ce parc : {e}")
        st.stop()

    try:
        ci = _fetch_ci_cached(
            park_id=park_id,
            lat=selected_row["lat"],
            lon=selected_row["lon"],
            peakpower_mw=selected_row["capacity_mwp"],
        )
    except Exception as e:
        logger.warning(f"CI failed for {park_id}: {e}")
        ci = None

# Today's estimate
today_est = estimate_for_date(
    hourly_kwh=hourly_data["hourly_production_kwh"],
    irradiance_wm2=hourly_data["hourly_irradiance_wm2"],
)

# Annual + monthly
annual_kwh = hourly_data["annual_total_kwh"]
annual_mwh = annual_kwh / 1000.0
cf_annual = capacity_factor_annual(
    hourly_data["hourly_production_kwh"], peakpower_mw=selected_row["capacity_mwp"]
)
cf_monthly = capacity_factor_monthly(
    hourly_data["hourly_production_kwh"], peakpower_mw=selected_row["capacity_mwp"]
)
monthly = monthly_aggregates(hourly_data["hourly_production_kwh"])

# Reported (si dispo)
reported = reported_map.get(park_id)
delta_pct = None
delta_severity = "none"
if reported and reported.get("annual_mwh"):
    rep_mwh = float(reported["annual_mwh"])
    delta_pct = (annual_mwh - rep_mwh) / rep_mwh * 100.0
    if abs(delta_pct) < 5:
        delta_severity = "green"
    elif abs(delta_pct) < 10:
        delta_severity = "yellow"
    else:
        delta_severity = "red"

# ---------------------------------------------------------------------------
# Terminal-style data panel
# ---------------------------------------------------------------------------

severity_badge = {"green": "🟢 GREEN", "yellow": "🟡 YELLOW", "red": "🔴 RED", "none": "⚪ N/A"}
delta_badge_class = f"badge-{delta_severity}"

terminal_html = f"""
<div class="terminal-panel">
  <div class="term-prompt">▸ park.{park_id}</div>
  <div class="term-meta">{selected_row['name']} · {selected_row['country']} · commissioning {selected_row['commissioning_year']} · operator {selected_row['operator']}</div>
  <div class="term-divider"></div>

  <div><span class="term-label">Production estimée — {today_est['date']}</span><span class="term-value">{today_est['production_kwh']:>10,.0f}  kWh</span></div>
  <div class="term-meta" style="margin-left: 220px;">moyenne climatique TMY 2019 pour ce jour de l'année</div>

  <div><span class="term-label">Ensoleillement du jour</span><span class="term-value">{today_est['avg_irradiance_kwh_m2']:>10.2f}  kWh/m²/jour</span></div>
  <div><span class="term-label">Heures de soleil utiles</span><span class="term-value">{today_est['sunshine_hours']:>10}  h</span></div>

  <div class="term-divider"></div>

  <div><span class="term-label">Capacité installée</span><span class="term-value">{selected_row['capacity_mwp']:>10,.1f}  MWp</span></div>
  <div><span class="term-label">Production annuelle estimée</span><span class="term-value">{annual_mwh:>10,.0f}  MWh</span></div>
  <div><span class="term-label">Capacity factor annuel</span><span class="term-value">{cf_annual:>10.1f}  %</span></div>

  <div class="term-divider"></div>
"""

if reported:
    terminal_html += f"""
  <div><span class="term-label">Production publiée</span><span class="term-value">{float(reported['annual_mwh']):>10,.0f}  MWh ({reported['year']})</span></div>
  <div><span class="term-label">Δ vs publié</span><span class="term-value {delta_badge_class}">{delta_pct:>+10.1f}  %  ·  {severity_badge[delta_severity]}</span></div>
  <div class="term-meta" style="margin-left: 220px;">source : <a href="{reported.get('source_url', '#')}" target="_blank" style="color: #7dd3fc;">press release</a></div>
"""
else:
    terminal_html += """
  <div><span class="term-label">Production publiée</span><span class="term-value badge-grey">— non disclosed publiquement</span></div>
  <div class="term-meta" style="margin-left: 220px;">aucune source fiable identifiée pour calcul du delta</div>
"""

terminal_html += """
</div>
"""

st.markdown(terminal_html, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Heatmap 365 × 24 — saisonnalité × profil journalier (le wow chart)
# ---------------------------------------------------------------------------

st.markdown("##### 🔥 Heatmap saisonnalité — production horaire (kWh) sur l'année type")

heatmap = hourly_heatmap_matrix(hourly_data["hourly_production_kwh"])
day_labels = pd.date_range("2019-01-01", "2019-12-31").strftime("%d %b").tolist()

fig_heat = go.Figure(
    data=go.Heatmap(
        z=heatmap,
        x=day_labels,
        y=[f"{h:02d}h" for h in range(24)],
        colorscale=[
            [0.0, "#0a0e1a"],
            [0.05, "#1e3a5f"],
            [0.3, "#3b82f6"],
            [0.6, "#facc15"],
            [1.0, "#fbbf24"],
        ],
        hovertemplate="%{y} · %{x}<br>%{z:.0f} kWh<extra></extra>",
        showscale=True,
        colorbar=dict(
            title=dict(text="kWh", side="right"),
            thickness=12,
            tickfont=dict(color="#94a3b8", size=10),
        ),
    )
)

fig_heat.update_layout(
    height=320,
    margin=dict(l=0, r=0, t=10, b=0),
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    xaxis=dict(
        showgrid=False,
        tickfont=dict(color="#94a3b8", size=9),
        nticks=12,
    ),
    yaxis=dict(
        showgrid=False,
        autorange="reversed",
        tickfont=dict(color="#94a3b8", size=9),
        nticks=8,
    ),
)

st.plotly_chart(fig_heat, width="stretch", config={"displayModeBar": False})

# ---------------------------------------------------------------------------
# Row : Bar chart 12 mois + Capacity factor mensuel
# ---------------------------------------------------------------------------

st.markdown("<br>", unsafe_allow_html=True)
col_left, col_right = st.columns(2)

with col_left:
    st.markdown("##### 📊 Production mensuelle estimée (MWh)")
    monthly_mwh = [m["production_mwh"] for m in monthly]
    fig_bar = go.Figure()
    fig_bar.add_trace(
        go.Bar(
            x=MONTH_NAMES_FR,
            y=monthly_mwh,
            marker=dict(color="#7dd3fc", line=dict(width=0)),
            hovertemplate="%{x} · %{y:,.0f} MWh<extra></extra>",
            name="Estimé PVGIS",
        )
    )
    if reported:
        avg_monthly_reported = float(reported["annual_mwh"]) / 12.0
        fig_bar.add_hline(
            y=avg_monthly_reported,
            line_dash="dash",
            line_color="#facc15",
            annotation_text=f"Reported avg : {avg_monthly_reported:,.0f} MWh/mo",
            annotation_position="top right",
            annotation_font=dict(color="#facc15", size=10),
        )
    fig_bar.update_layout(
        height=280,
        margin=dict(l=0, r=0, t=10, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(showgrid=False, tickfont=dict(color="#94a3b8")),
        yaxis=dict(
            gridcolor="rgba(125, 211, 252, 0.1)",
            tickfont=dict(color="#94a3b8"),
            title=None,
        ),
        showlegend=False,
    )
    st.plotly_chart(fig_bar, width="stretch", config={"displayModeBar": False})

with col_right:
    st.markdown("##### 📈 Capacity factor mensuel (%)")
    fig_cf = go.Figure()
    fig_cf.add_trace(
        go.Scatter(
            x=MONTH_NAMES_FR,
            y=cf_monthly,
            mode="lines+markers",
            line=dict(color="#7dd3fc", width=2),
            marker=dict(size=8, color="#7dd3fc", line=dict(color="#0a0e1a", width=2)),
            fill="tozeroy",
            fillcolor="rgba(125, 211, 252, 0.1)",
            hovertemplate="%{x} · %{y:.1f} %<extra></extra>",
        )
    )
    fig_cf.update_layout(
        height=280,
        margin=dict(l=0, r=0, t=10, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(showgrid=False, tickfont=dict(color="#94a3b8")),
        yaxis=dict(
            gridcolor="rgba(125, 211, 252, 0.1)",
            tickfont=dict(color="#94a3b8"),
            title=None,
            ticksuffix=" %",
        ),
        showlegend=False,
    )
    st.plotly_chart(fig_cf, width="stretch", config={"displayModeBar": False})

# ---------------------------------------------------------------------------
# Confidence interval (loss sensitivity)
# ---------------------------------------------------------------------------

if ci is not None:
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("##### 🎯 Intervalle de confiance — sensibilité aux pertes système")

    sens_rows = []
    for s in ci.scenarios:
        annual_mwh_s = s.annual_kwh / 1000.0
        delta_s = None
        if reported:
            delta_s = (annual_mwh_s - float(reported["annual_mwh"])) / float(reported["annual_mwh"]) * 100.0
        sens_rows.append(
            {
                "Scénario loss": f"{s.loss_pct:.0f} %",
                "Production annuelle (MWh)": f"{annual_mwh_s:,.0f}",
                "Δ vs publié": f"{delta_s:+.1f} %" if delta_s is not None else "—",
            }
        )
    sens_df = pd.DataFrame(sens_rows)
    st.dataframe(sens_df, hide_index=True, width="stretch")

    st.caption(
        f"low = {ci.low_mwh:,.0f} MWh · mid = {ci.mid_mwh:,.0f} MWh · high = {ci.high_mwh:,.0f} MWh"
    )

# ---------------------------------------------------------------------------
# Footer — provenance + methodology link
# ---------------------------------------------------------------------------

st.markdown("<br>", unsafe_allow_html=True)
st.markdown(
    f"""
    <div class="provenance" style="text-align: center;">
      Source : PVGIS v5.2 (JRC European Commission, gratuit) · TMY 2019 ·
      pertes système 14% · {selected_row['operator']} ·
      <a href="{selected_row['press_release_url']}" target="_blank" style="color: #7dd3fc;">press release</a>
      · voir <a href="/Methodology" style="color: #7dd3fc;">page Methodology</a>
      pour l'explication du climat moyen vs météo réelle.
    </div>
    """,
    unsafe_allow_html=True,
)
