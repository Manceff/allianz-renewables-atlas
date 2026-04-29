"""Page IC Snapshot — vue 30 secondes pour Investment Committee.

Single-screen pulse du portefeuille Renewables ACP : capacité, pays, techno,
couverture delta. Doit tenir sur viewport 1440x900 sans scroll.

Layout :
- Row 1 : 4 metric cards (capacity, parks, countries, Δ-covered).
- Row 2 : carte spatiale (Plotly scatter_geo, sévérité) + donut techno.
- Row 3 : donut pays + table Top 5.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.lib.parks_loader import load_parks_index
from src.lib.portfolio_aggregates import compute_aggregates

logger = logging.getLogger(__name__)

st.set_page_config(
    page_title="IC Snapshot — Atlas",
    page_icon="📈",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent.parent
PORTFOLIO_SWEEP = ROOT / "data" / "portfolio_sweep.json"

# Couleurs métier
TECHNOLOGY_COLORS = {
    "solar": "#fbbf24",
    "onshore_wind": "#3b82f6",
    "offshore_wind": "#1e3a8a",
    "battery_storage": "#22c55e",
}

SEVERITY_COLORS = {
    "green": "#22c55e",
    "yellow": "#eab308",
    "red": "#ef4444",
}
DEFAULT_SEVERITY_COLOR = "#b4b4b4"


# ---------------------------------------------------------------------------
# Loaders (cachés)
# ---------------------------------------------------------------------------


@st.cache_data
def _load_aggregates() -> dict:
    """Calcule les agrégats portfolio et retourne un dict (hashable cache)."""
    idx = load_parks_index()
    agg = compute_aggregates(idx.parks)
    return agg.model_dump()


@st.cache_data
def _load_parks_df() -> pd.DataFrame:
    """Charge la liste des parcs en DataFrame pour la carte et le top5."""
    idx = load_parks_index()
    rows = []
    for p in idx.parks:
        rows.append(
            {
                "id": p.id,
                "name": p.name,
                "country": p.country,
                "technology": p.technology.value,
                "capacity_mwp": p.capacity_mwp,
                "lat": p.lat,
                "lon": p.lon,
            }
        )
    return pd.DataFrame(rows)


@st.cache_data
def _load_severity_map() -> dict[str, str]:
    """Charge `data/portfolio_sweep.json` et retourne {park_id: severity}.

    Retourne un dict vide en cas d'absence ou de JSON malformé.
    """
    if not PORTFOLIO_SWEEP.exists():
        return {}
    try:
        with open(PORTFOLIO_SWEEP, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("portfolio_sweep.json illisible: %s", exc)
        return {}
    entries = data.get("entries", []) if isinstance(data, dict) else []
    return {e["park_id"]: e.get("severity", "green") for e in entries if e.get("park_id")}


@st.cache_data
def _load_sweep_capacity() -> float:
    """Somme des capacités MWp couvertes par `portfolio_sweep.json` (0 si absent)."""
    if not PORTFOLIO_SWEEP.exists():
        return 0.0
    try:
        with open(PORTFOLIO_SWEEP, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return 0.0
    entries = data.get("entries", []) if isinstance(data, dict) else []
    return float(sum(e.get("capacity_mwp", 0.0) for e in entries))


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

st.title("📈 IC Snapshot — Allianz Renewables Atlas")
st.caption(
    "Lecture 30 secondes du portefeuille Renewables ACP. "
    "Sources publiques uniquement — voir Methodology pour le détail."
)

agg = _load_aggregates()
parks_df = _load_parks_df()
severity_map = _load_severity_map()
sweep_capacity = _load_sweep_capacity()

total_capacity_mw = float(agg["total_capacity_mw"])
coverage_pct = (sweep_capacity / total_capacity_mw * 100.0) if total_capacity_mw > 0 else 0.0

# ---------------------------------------------------------------------------
# Row 1 — Top metric cards
# ---------------------------------------------------------------------------

c1, c2, c3, c4 = st.columns(4)
c1.metric("Capacité totale", f"{total_capacity_mw:,.0f} MW")
c2.metric(
    "Parcs cartographiés",
    f"{agg['count_parks']}",
    help=f"Sur {agg['count_countries']} pays — 23 / 150+ ACP publiquement identifiables.",
)
c3.metric("Pays", f"{agg['count_countries']}")
c4.metric(
    "Δ-couverts",
    f"{coverage_pct:.0f}%",
    help=(
        "Part de la capacité totale (MW) ayant un delta estimée vs publiée calculé "
        "dans `data/portfolio_sweep.json`."
    ),
)

st.divider()

# ---------------------------------------------------------------------------
# Row 2 — Carte spatiale + donut techno
# ---------------------------------------------------------------------------

row2_left, row2_right = st.columns(2)

with row2_left:
    st.subheader("Empreinte géographique")
    map_df = parks_df.copy()
    map_df["severity"] = map_df["id"].map(severity_map).fillna("none")
    map_df["color"] = map_df["severity"].map(SEVERITY_COLORS).fillna(DEFAULT_SEVERITY_COLOR)
    map_df["size"] = map_df["capacity_mwp"].fillna(20).clip(lower=20)

    fig_map = px.scatter_geo(
        map_df,
        lat="lat",
        lon="lon",
        size="size",
        color="severity",
        color_discrete_map={
            "green": SEVERITY_COLORS["green"],
            "yellow": SEVERITY_COLORS["yellow"],
            "red": SEVERITY_COLORS["red"],
            "none": DEFAULT_SEVERITY_COLOR,
        },
        hover_name="name",
        hover_data={
            "country": True,
            "technology": True,
            "capacity_mwp": ":,.0f",
            "severity": True,
            "lat": False,
            "lon": False,
            "size": False,
        },
        projection="orthographic",
    )
    fig_map.update_geos(
        showland=True,
        landcolor="#e2e8f0",
        showocean=True,
        oceancolor="#cbd5e1",
        showcountries=True,
        countrycolor="#94a3b8",
        showcoastlines=True,
        coastlinecolor="#64748b",
        center=dict(lat=45, lon=5),
    )
    fig_map.update_layout(
        height=350,
        margin=dict(l=0, r=0, t=0, b=0),
        showlegend=False,
    )
    st.plotly_chart(fig_map, width="stretch")
    st.caption("Coloration par sévérité du delta (vert/jaune/rouge — gris = non couvert).")

with row2_right:
    st.subheader("Capacité par technologie")
    tech_dict = agg["capacity_by_tech"]
    tech_labels = list(tech_dict.keys())
    tech_values = list(tech_dict.values())
    tech_colors = [TECHNOLOGY_COLORS.get(t, "#9ca3af") for t in tech_labels]

    fig_tech = go.Figure(
        data=[
            go.Pie(
                labels=tech_labels,
                values=tech_values,
                hole=0.55,
                marker=dict(colors=tech_colors),
                textinfo="label+percent",
                hovertemplate="%{label}<br>%{value:,.0f} MW (%{percent})<extra></extra>",
            )
        ]
    )
    fig_tech.update_layout(
        height=350,
        margin=dict(l=0, r=0, t=10, b=0),
        showlegend=False,
        annotations=[
            dict(
                text=f"{total_capacity_mw:,.0f}<br><span style='font-size:12px'>MW</span>",
                x=0.5,
                y=0.5,
                font_size=18,
                showarrow=False,
            )
        ],
    )
    st.plotly_chart(fig_tech, width="stretch")

# ---------------------------------------------------------------------------
# Row 3 — Donut pays + table Top 5
# ---------------------------------------------------------------------------

row3_left, row3_right = st.columns(2)

with row3_left:
    st.subheader("Capacité par pays")
    country_dict = agg["capacity_by_country"]
    sorted_countries = sorted(country_dict.items(), key=lambda kv: kv[1], reverse=True)
    country_labels = [c for c, _ in sorted_countries]
    country_values = [v for _, v in sorted_countries]

    fig_country = go.Figure(
        data=[
            go.Pie(
                labels=country_labels,
                values=country_values,
                hole=0.55,
                marker=dict(colors=px.colors.qualitative.Set2),
                textinfo="label+percent",
                hovertemplate="%{label}<br>%{value:,.0f} MW (%{percent})<extra></extra>",
            )
        ]
    )
    fig_country.update_layout(
        height=350,
        margin=dict(l=0, r=0, t=10, b=0),
        showlegend=False,
    )
    st.plotly_chart(fig_country, width="stretch")

with row3_right:
    st.subheader("Top 5 parcs par capacité")
    top5_ids = agg["top5_by_capacity"]
    by_id = {row["id"]: row for _, row in parks_df.iterrows()}

    top5_rows = []
    for pid in top5_ids:
        p = by_id.get(pid)
        if p is None:
            continue
        top5_rows.append(
            {
                "Park": p["name"],
                "Country": p["country"],
                "Tech": p["technology"],
                "Capacity (MWp)": (
                    f"{p['capacity_mwp']:,.0f}" if pd.notna(p["capacity_mwp"]) else "n/c"
                ),
            }
        )
    top5_df = pd.DataFrame(top5_rows)
    st.dataframe(top5_df, hide_index=True, width="stretch")

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------

st.caption(
    "Snapshot generated from `data/portfolio_sweep.json` and `data/parks_index.yaml` — "
    "public sources only."
)

st.markdown(
    """
    <button onclick="window.print()"
        style="background:#003781;color:white;border:none;padding:6px 14px;
               border-radius:4px;cursor:pointer;font-size:13px;">
        Print to PDF
    </button>
    """,
    unsafe_allow_html=True,
)
