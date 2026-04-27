"""Page Globe — terre 3D interactive avec markers pour chaque parc Allianz Renewables.

Stack : PyDeck _GlobeView avec ScatterplotLayer (markers) + ColumnLayer (hauteur capacité).
Click sur un marker → navigation vers la page Spotlight (via st.session_state).

Voir CLAUDE.md pour les conventions et README pour la vision.
"""

from __future__ import annotations

import streamlit as st
import yaml
from pathlib import Path

import pydeck as pdk
import pandas as pd

st.set_page_config(page_title="Globe — Allianz Renewables Atlas", page_icon="🌍", layout="wide")

st.title("🌍 Globe interactif")
st.caption(
    "Terre 3D rotative avec les 23 parcs Renewables d'Allianz Capital Partners cartographiés. "
    "Hauteur proportionnelle à la capacité installée. Couleur par technologie."
)

# ---- Chargement des parcs depuis parks_index.yaml ----
PARKS_INDEX = Path(__file__).resolve().parent.parent.parent / "data" / "parks_index.yaml"


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
    # Extract lat/lon depuis coordinates [lat, lon]
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

# ---- Application des filtres ----
filtered = df[
    (df["country"].isin(selected_countries))
    & (df["technology"].isin(selected_technologies))
    & ((df["capacity_mwp"].fillna(0) >= min_capacity))
]

# ---- Stats agrégées ----
col1, col2, col3, col4 = st.columns(4)
col1.metric("Parcs filtrés", len(filtered))
col2.metric(
    "Capacité totale",
    f"{filtered['capacity_mwp'].sum():.0f} MW" if filtered["capacity_mwp"].notna().any() else "n/c",
)
col3.metric("Pays couverts", len(filtered["country"].unique()))
col4.metric("Sur 150+ ACP", f"{len(filtered)} / 150+")

st.divider()

# ---- PyDeck Globe ----
TECHNOLOGY_COLORS = {
    "solar": [251, 191, 36, 200],  # jaune
    "onshore_wind": [34, 197, 94, 200],  # vert
    "offshore_wind": [59, 130, 246, 200],  # bleu
    "battery_storage": [168, 85, 247, 200],  # violet
}

filtered_df = filtered.copy()
# .apply() au lieu de .map().fillna([liste]) — pandas refuse une liste comme valeur de fillna
filtered_df["color"] = filtered_df["technology"].apply(
    lambda t: TECHNOLOGY_COLORS.get(t, [128, 128, 128, 200])
)
filtered_df["height"] = filtered_df["capacity_mwp"].fillna(50) * 1000  # exagération visuelle pour 3D

# ScatterplotLayer pour les markers de base
scatter_layer = pdk.Layer(
    "ScatterplotLayer",
    data=filtered_df,
    get_position=["lon", "lat"],
    get_color="color",
    get_radius=30000,  # rayon en mètres
    pickable=True,
    auto_highlight=True,
)

# ColumnLayer pour la hauteur 3D (capacité)
column_layer = pdk.Layer(
    "ColumnLayer",
    data=filtered_df,
    get_position=["lon", "lat"],
    get_elevation="height",
    get_fill_color="color",
    radius=20000,
    pickable=True,
    auto_highlight=True,
    elevation_scale=10,
)

# View state initial : centré Europe, globe 3D rotatif
view_state = pdk.ViewState(
    longitude=10,
    latitude=48,
    zoom=1.2,
    pitch=0,
    bearing=0,
)

# _GlobeView pour rendu globe 3D (vs Mercator plat). Expérimental PyDeck mais marche.
globe_view = pdk.View(type="_GlobeView", controller=True)

# Tooltip au hover
tooltip = {
    "html": "<b>{name}</b><br/>"
    "{country} • {technology}<br/>"
    "{capacity_mwp} MW • {commissioning_year}<br/>"
    "Opérateur : {operator}",
    "style": {"backgroundColor": "#003781", "color": "white", "fontSize": "12px"},
}

deck = pdk.Deck(
    layers=[column_layer, scatter_layer],
    initial_view_state=view_state,
    views=[globe_view],
    tooltip=tooltip,
    map_provider=None,  # _GlobeView n'utilise pas de basemap classique
    parameters={"cull": True},
)

st.pydeck_chart(deck, use_container_width=True)

st.caption(
    "💡 Survole un marker pour les détails. Click + drag pour faire tourner. "
    "Pour ouvrir la page détaillée d'un parc, va dans **Spotlight** dans la sidebar et sélectionne le parc."
)

st.divider()

# ---- Légende ----
st.subheader("Légende")
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
