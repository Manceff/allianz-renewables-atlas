"""Page Spotlight — détail d'un parc spécifique.

Pour les solaires : pipeline analytique complet (image Sentinel-2 + production estimée PVGIS + delta).
Pour les éoliens : monitoring visuel uniquement (image satellite + métadonnées).

Voir specs/03-renewables-monitor.md (héritée du projet précédent) pour les détails.
"""

from __future__ import annotations

import json
from pathlib import Path

import streamlit as st
import yaml

st.set_page_config(page_title="Spotlight — Allianz Renewables Atlas", page_icon="📍", layout="wide")

st.title("📍 Spotlight Parc")

PARKS_INDEX = Path(__file__).resolve().parent.parent.parent / "data" / "parks_index.yaml"
PARKS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "parks"


@st.cache_data
def load_parks_list() -> list[dict]:
    if not PARKS_INDEX.exists():
        return []
    with open(PARKS_INDEX) as f:
        data = yaml.safe_load(f)
    return data.get("parks", [])


parks = load_parks_list()

if not parks:
    st.error("Aucun parc dans `data/parks_index.yaml`. Voir Phase 1 du README.")
    st.stop()

# ---- Sélecteur de parc en sidebar ----
selected_park = st.sidebar.selectbox(
    "Choisir un parc",
    parks,
    format_func=lambda p: f"{p['name']} ({p['country']}, {p['technology']})",
)

park_id = selected_park["id"]
park_dir = PARKS_DIR / park_id

# ---- Header ----
st.subheader(selected_park["name"])
st.caption(
    f"{selected_park['country']} · {selected_park['technology'].replace('_', ' ').title()} · "
    f"{selected_park.get('capacity_mwp', 'n/c')} MW · "
    f"Opérateur : {selected_park.get('operator', 'n/c')}"
)

# ---- Métadonnées en cards ----
col1, col2, col3, col4 = st.columns(4)
col1.metric("Capacité", f"{selected_park.get('capacity_mwp', 'n/c')} MW")
col2.metric("Pays", selected_park.get("country", "n/c"))
col3.metric("Mise en service", str(selected_park.get("commissioning_year", "n/c")))
col4.metric(
    "Stake Allianz",
    f"{selected_park.get('allianz_stake_pct')}%" if selected_park.get("allianz_stake_pct") else "n/c",
)

# ---- Image satellite ----
sentinel_path = park_dir / "sentinel.png"
if sentinel_path.exists():
    st.markdown("### 🛰 Image satellite Sentinel-2")
    st.image(str(sentinel_path), caption="Source : ESA Copernicus Sentinel-2", width="stretch")
else:
    st.warning(
        f"Image satellite non disponible pour {selected_park['name']}. "
        f"À générer via `scripts/precompute_all.py`."
    )

# ---- Production analysis (solaires uniquement) ----
if selected_park["technology"] == "solar" and selected_park.get("has_pvgis_estimate", False):
    st.markdown("### ⚡ Estimation de production (PVGIS)")

    prod_est_path = park_dir / "production_estimated.json"
    prod_rep_path = park_dir / "production_reported.json"
    delta_path = park_dir / "delta.json"

    if prod_est_path.exists():
        with open(prod_est_path) as f:
            prod_est = json.load(f)

        # Affichage delta si dispo
        if delta_path.exists():
            with open(delta_path) as f:
                delta = json.load(f)

            col_a, col_b, col_c = st.columns(3)
            col_a.metric("Production estimée (PVGIS)", f"{delta.get('production_estimated_mwh', 0):,.0f} MWh")
            col_b.metric("Production publiée (opérateur)", f"{delta.get('production_reported_mwh', 0):,.0f} MWh")
            col_c.metric(
                "Delta",
                f"{delta.get('delta_mwh', 0):+,.0f} MWh",
                delta=f"{delta.get('delta_pct', 0):+.1f}%",
            )

            severity_emoji = {"green": "🟢", "yellow": "🟡", "red": "🔴"}
            st.info(
                f"{severity_emoji.get(delta.get('severity', 'green'), '🟢')} "
                f"{delta.get('interpretation', 'Pas d''interprétation disponible.')}"
            )

        # Chart mensuel si dispo
        monthly = prod_est.get("monthly_production_estimated", [])
        if monthly:
            try:
                import pandas as pd
                import plotly.express as px

                df = pd.DataFrame(monthly)
                df["period"] = df.apply(lambda r: f"{r['year']}-{r['month']:02d}", axis=1)
                fig = px.bar(
                    df,
                    x="period",
                    y="production_mwh",
                    title=f"Production estimée mensuelle — {selected_park['name']}",
                    labels={"period": "Mois", "production_mwh": "Production (MWh)"},
                    color_discrete_sequence=["#fbbf24"],
                )
                st.plotly_chart(fig, width="stretch")
            except ImportError:
                st.dataframe(monthly)
    else:
        st.warning("Données PVGIS non générées. Voir Phase 2 (precompute) du README.")

else:
    st.markdown("### 🌬 Monitoring visuel uniquement")
    st.info(
        f"Pour les parcs **{selected_park['technology'].replace('_', ' ')}**, l'estimation de "
        f"production demande une stack distincte (windpowerlib + données vent ERA5). En v1, "
        f"seul le monitoring visuel est implémenté. Extension v2 prévue."
    )

# ---- Notes ----
if selected_park.get("notes"):
    st.markdown("### 📝 Notes")
    st.markdown(f"> {selected_park['notes']}")

# ---- Source ----
st.divider()
if selected_park.get("press_release_url"):
    st.markdown(f"📄 **Press release ACP source** : [{selected_park['press_release_url']}]({selected_park['press_release_url']})")

st.caption(
    "Démonstration construite sur sources publiques uniquement (ESA Copernicus, JRC EU Commission, "
    "Allianz Capital Partners press releases). Aucune affiliation Allianz."
)
