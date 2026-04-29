"""Page Globe — terre 3D interactive avec markers pour chaque parc Allianz Renewables.

Stack : Plotly scatter_geo en projection orthographic (vraie sphère 3D rotative,
fiable cross-browser, vs PyDeck _GlobeView qui dégrade en MapView Mercator dans
Streamlit 1.56). Filtres pays/techno/capacité + toggle couleur tech/severity.

Voir CLAUDE.md pour les conventions et README pour la vision.
"""

from __future__ import annotations

import json
import logging

import streamlit as st
import yaml
from pathlib import Path

import pandas as pd
import plotly.express as px

logger = logging.getLogger(__name__)

st.set_page_config(page_title="Globe — Allianz Renewables Atlas", page_icon="🌍", layout="wide")

st.title("🌍 Globe interactif")
st.caption(
    "Terre 3D rotative avec les 23 parcs Renewables d'Allianz Capital Partners cartographiés. "
    "Click + drag pour faire tourner. Couleur par technologie ou par sévérité du delta."
)

# ---- Chargement des parcs depuis parks_index.yaml ----
PARKS_INDEX = Path(__file__).resolve().parent.parent.parent / "data" / "parks_index.yaml"
PORTFOLIO_SWEEP = Path(__file__).resolve().parent.parent.parent / "data" / "portfolio_sweep.json"

# Couleurs sévérité delta (green/yellow/red), grey si pas d'entrée dans portfolio_sweep.json
SEVERITY_COLORS = {
    "green": "#22c55e",
    "yellow": "#eab308",
    "red": "#ef4444",
    "none": "#b4b4b4",
}

# Couleurs par technologie (cohérentes avec IC Snapshot et la légende)
TECHNOLOGY_COLORS = {
    "solar": "#fbbf24",          # jaune
    "onshore_wind": "#22c55e",   # vert
    "offshore_wind": "#3b82f6",  # bleu
    "battery_storage": "#a855f7",  # violet
}


@st.cache_data
def load_severity_map() -> dict[str, str]:
    """Charge `data/portfolio_sweep.json` → {park_id: severity}.

    Fichier absent ou JSON malformé → dict vide (fallback "none" côté coloration).
    """
    if not PORTFOLIO_SWEEP.exists():
        return {}
    try:
        with open(PORTFOLIO_SWEEP) as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("portfolio_sweep.json illisible: %s", exc)
        return {}
    entries = data.get("entries", []) if isinstance(data, dict) else []
    return {e.get("park_id"): e.get("severity") for e in entries if e.get("park_id")}


@st.cache_data
def load_parks() -> pd.DataFrame:
    """Charge la liste des parcs depuis parks_index.yaml et retourne un DataFrame."""
    if not PARKS_INDEX.exists():
        return pd.DataFrame()
    with open(PARKS_INDEX) as f:
        data = yaml.safe_load(f)
    parks = data.get("parks", [])
    df = pd.DataFrame(parks)
    if df.empty:
        return df
    df["lat"] = df["coordinates"].apply(lambda c: c[0] if c else None)
    df["lon"] = df["coordinates"].apply(lambda c: c[1] if c else None)
    return df


df = load_parks()

if df.empty:
    st.error(
        "Aucun parc dans `data/parks_index.yaml`. Voir Phase 1 du README — cartographie initiale requise."
    )
    st.stop()

# ---- Sidebar : filtres ----
st.sidebar.header("Filtres")

countries = sorted(df["country"].unique().tolist())
selected_countries = st.sidebar.multiselect("Pays", countries, default=countries)

technologies = sorted(df["technology"].unique().tolist())
selected_technologies = st.sidebar.multiselect("Technologie", technologies, default=technologies)

min_capacity = st.sidebar.slider(
    "Capacité minimale (MW)",
    min_value=0,
    max_value=int(df["capacity_mwp"].dropna().max()) if df["capacity_mwp"].notna().any() else 1000,
    value=0,
    step=10,
)

color_mode = st.sidebar.radio(
    "Color markers by",
    ["Technology", "Delta severity"],
    index=0,
)

# ---- Application des filtres ----
filtered = df[
    (df["country"].isin(selected_countries))
    & (df["technology"].isin(selected_technologies))
    & ((df["capacity_mwp"].fillna(0) >= min_capacity))
].copy()

# ---- Stats agrégées ----
col1, col2, col3, col4 = st.columns(4)
col1.metric("Parcs filtrés", len(filtered))
col2.metric(
    "Capacité totale",
    f"{filtered['capacity_mwp'].sum():,.0f} MW" if filtered["capacity_mwp"].notna().any() else "n/c",
)
col3.metric("Pays couverts", len(filtered["country"].unique()))
col4.metric("Sur 150+ ACP", f"{len(filtered)} / 150+")

st.divider()

# ---- Plotly scatter_geo orthographic (vrai globe sphérique) ----
# Color column selon le mode choisi
if color_mode == "Delta severity":
    severity_map = load_severity_map()
    filtered["severity"] = filtered["id"].map(severity_map).fillna("none")
    color_col = "severity"
    color_map = SEVERITY_COLORS
else:
    color_col = "technology"
    color_map = TECHNOLOGY_COLORS

# Taille proportionnelle à la capacité, plafonnée pour lisibilité
filtered["marker_size"] = filtered["capacity_mwp"].fillna(20).clip(lower=15, upper=80)

fig = px.scatter_geo(
    filtered,
    lat="lat",
    lon="lon",
    size="marker_size",
    color=color_col,
    color_discrete_map=color_map,
    hover_name="name",
    hover_data={
        "country": True,
        "technology": True,
        "capacity_mwp": ":,.0f",
        "operator": True,
        "commissioning_year": True,
        "lat": False,
        "lon": False,
        "marker_size": False,
        color_col: True,
    },
    projection="orthographic",
)

fig.update_geos(
    showland=True,
    landcolor="#dbeafe",
    showocean=True,
    oceancolor="#1e3a8a",
    showcountries=True,
    countrycolor="#64748b",
    showcoastlines=True,
    coastlinecolor="#475569",
    showframe=True,
    framecolor="#94a3b8",
    bgcolor="rgba(0,0,0,0)",
    center=dict(lat=30, lon=10),
    projection_rotation=dict(lon=10, lat=30, roll=0),
)

fig.update_layout(
    height=600,
    margin=dict(l=0, r=0, t=0, b=0),
    legend=dict(
        orientation="h",
        yanchor="bottom",
        y=-0.05,
        xanchor="center",
        x=0.5,
    ),
)

# Markers : bordure sombre pour la lisibilité
fig.update_traces(marker=dict(line=dict(width=1, color="#1f2937")))

st.plotly_chart(fig, width="stretch", config={"scrollZoom": True})

st.caption(
    "💡 Drag pour faire tourner le globe. Hover sur un marker pour les détails. "
    "Pour la page détaillée d'un parc, va dans **Spotlight** dans la sidebar."
)

st.divider()

# ---- Légende ----
st.subheader("Légende — Technologies")
leg_col1, leg_col2, leg_col3, leg_col4 = st.columns(4)
leg_col1.markdown("🟡 **Solaire PV**")
leg_col2.markdown("🟢 **Onshore wind**")
leg_col3.markdown("🔵 **Offshore wind**")
leg_col4.markdown("🟣 **Battery storage**")

st.markdown(
    "**Note méthodologique** : la cartographie couvre les parcs publiquement identifiables depuis "
    "les press releases d'Allianz Capital Partners. Le reste du portefeuille (>120 parcs) est "
    "détenu indirectement via des fonds infrastructure sans nom public des assets sous-jacents."
)
