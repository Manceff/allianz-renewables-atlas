"""Page Monograph — analyse approfondie du parc solaire Ourika (PT, 46 MWp).

Showcase analyste : header sourcé, production mensuelle PVGIS, sensitivity loss
10/14/18%, méthodologie collapsible, sources URL clickables. Toute valeur affichée
est traçable à un fichier dans `data/`.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.lib.confidence_interval import compute_pvgis_range
from src.lib.parks_loader import get_park_by_id

logger = logging.getLogger(__name__)

st.set_page_config(
    page_title="Ourika Monograph",
    page_icon="🔬",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Constantes & chemins
# ---------------------------------------------------------------------------

PARK_ID = "ourika"
ROOT = Path(__file__).resolve().parent.parent.parent
PARK_DIR = ROOT / "data" / "parks" / PARK_ID
PVGIS_PATH = PARK_DIR / "production_estimated.json"
PVGIS_MONTHLY_PATH = PARK_DIR / "pvgis_monthly.json"
DELTA_PATH = PARK_DIR / "delta.json"

REPORTED_ANNUAL_MWH = 80_000.0
REPORTED_YEAR = 2018
REPORTED_SOURCE = "Allianz Capital Partners press release (25 octobre 2018)"

# Severity colors — alignées sur compute_delta.py
SEVERITY_COLORS = {
    "green": "#16a34a",
    "yellow": "#eab308",
    "red": "#dc2626",
}

GITHUB_RAW_BASE = (
    "https://raw.githubusercontent.com/Manceff/allianz-renewables-atlas/main/data"
)

MONTH_LABELS = [
    "Jan", "Fév", "Mar", "Avr", "Mai", "Juin",
    "Juil", "Août", "Sep", "Oct", "Nov", "Déc",
]


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def _load_monthly_kwh() -> list[float]:
    """Lit la production mensuelle PVGIS (12 valeurs en kWh).

    Privilégie `pvgis_monthly.json` (compact) puis fallback sur
    `production_estimated.json` (sortie PVGIS complète).
    """
    if PVGIS_MONTHLY_PATH.exists():
        with open(PVGIS_MONTHLY_PATH, encoding="utf-8") as f:
            data = json.load(f)
        monthly = data.get("monthly_production_kwh")
        if isinstance(monthly, list) and len(monthly) == 12:
            return [float(v) for v in monthly]
    if PVGIS_PATH.exists():
        with open(PVGIS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        monthly = data.get("monthly_production_kwh", [])
        if isinstance(monthly, list) and len(monthly) == 12:
            return [float(v) for v in monthly]
    return []


def _load_pvgis_inputs() -> dict | None:
    """Récupère les inputs effectifs envoyés à PVGIS (lat, lon, tilt, loss…)."""
    if not PVGIS_PATH.exists():
        return None
    with open(PVGIS_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("inputs")


def _load_delta() -> dict | None:
    if not DELTA_PATH.exists():
        return None
    with open(DELTA_PATH, encoding="utf-8") as f:
        return json.load(f)


@st.cache_data(ttl=3600, show_spinner="Calcul de la sensibilité PVGIS…")
def _cached_sensitivity(lat: float, lon: float, peakpower_mw: float) -> dict:
    """Wrapper cache 1h autour de compute_pvgis_range pour éviter les hits PVGIS répétés.

    Retourne un dict (et non un Pydantic model) pour que Streamlit puisse hasher
    proprement le résultat en cache.
    """
    ci = compute_pvgis_range(lat=lat, lon=lon, peakpower_mw=peakpower_mw)
    return {
        "low_mwh": ci.low_mwh,
        "mid_mwh": ci.mid_mwh,
        "high_mwh": ci.high_mwh,
        "scenarios": [
            {"loss_pct": s.loss_pct, "annual_kwh": s.annual_kwh}
            for s in ci.scenarios
        ],
    }


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

park = get_park_by_id(PARK_ID)
if park is None:
    st.error("Parc Ourika introuvable dans `data/parks_index.yaml`.")
    st.stop()

st.title("🔬 Ourika Solar Park — Monograph")
st.caption(
    f"Portugal · {park.capacity_mwp:,.0f} MWp · "
    f"Commissioned {park.commissioning_year} · "
    f"Operator: {park.operator} · "
    f"{park.allianz_stake_pct:.0f}% Allianz Capital Partners stake"
)

st.link_button("📄 Allianz Capital Partners — press release source", park.press_release_url)

st.divider()

# ---------------------------------------------------------------------------
# Section 1 — Geographic context
# ---------------------------------------------------------------------------

st.header("1. Contexte géographique")

lat, lon = park.lat, park.lon

col_geo_a, col_geo_b = st.columns([2, 1])

with col_geo_a:
    try:
        import folium
        from streamlit_folium import st_folium

        fmap = folium.Map(
            location=[lat, lon],
            zoom_start=11,
            tiles="OpenStreetMap",
        )
        folium.Marker(
            location=[lat, lon],
            tooltip=park.name,
            popup=f"{park.name}<br>{park.capacity_mwp:,.0f} MWp · {park.commissioning_year}",
            icon=folium.Icon(color="orange", icon="solar-panel", prefix="fa"),
        ).add_to(fmap)
        st_folium(fmap, width=None, height=360, returned_objects=[])
    except ImportError:
        st.info("Folium non disponible — fallback texte.")

with col_geo_b:
    st.metric("Latitude", f"{lat:.4f}°")
    st.metric("Longitude", f"{lon:.4f}°")
    st.markdown(
        f"[🗺 Voir sur OpenStreetMap]"
        f"(https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=11/{lat}/{lon})"
    )
    st.caption(
        "Localisation : Ourique, district de Beja, Alentejo (PT). Coordonnées "
        "issues de `data/parks_index.yaml`."
    )

st.divider()

# ---------------------------------------------------------------------------
# Section 2 — Production estimée mensuelle (PVGIS)
# ---------------------------------------------------------------------------

st.header("2. Production estimée mensuelle (PVGIS)")

monthly_kwh = _load_monthly_kwh()

if not monthly_kwh:
    st.warning(
        "Production mensuelle PVGIS indisponible — exécuter `scripts/precompute_all.py` "
        "pour régénérer `data/parks/ourika/production_estimated.json`."
    )
else:
    monthly_avg_proxy_kwh = (REPORTED_ANNUAL_MWH * 1000.0) / 12.0

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=MONTH_LABELS,
            y=monthly_kwh,
            name="PVGIS — loss 14%",
            marker_color="#fbbf24",
            hovertemplate="%{x} : %{y:,.0f} kWh<extra></extra>",
        )
    )
    fig.add_hline(
        y=monthly_avg_proxy_kwh,
        line_dash="dash",
        line_color="#475569",
        annotation_text=(
            f"Moyenne si production égale ({monthly_avg_proxy_kwh / 1000:,.0f} MWh/mois) — proxy"
        ),
        annotation_position="top right",
    )
    fig.update_layout(
        title="Production estimée mensuelle (PVGIS, loss=14%)",
        xaxis_title="Mois",
        yaxis_title="Production (kWh)",
        showlegend=False,
        height=420,
        margin=dict(l=20, r=20, t=60, b=40),
    )
    st.plotly_chart(fig, width="stretch")

    annual_estimated_mwh = sum(monthly_kwh) / 1000.0
    col_m1, col_m2, col_m3 = st.columns(3)
    col_m1.metric(
        "Estimation annuelle PVGIS",
        f"{annual_estimated_mwh:,.0f} MWh",
        help="Somme des 12 mois PVGIS (loss=14%, TMY 2005-2020).",
    )
    col_m2.metric(
        "Reporté Allianz PR (2018)",
        f"{REPORTED_ANNUAL_MWH:,.0f} MWh",
        help="Estimation commissioning : 23 000 foyers × ~3.5 MWh.",
    )
    delta_pct_est = (annual_estimated_mwh - REPORTED_ANNUAL_MWH) / REPORTED_ANNUAL_MWH * 100.0
    col_m3.metric(
        "Écart vs reporté",
        f"{annual_estimated_mwh - REPORTED_ANNUAL_MWH:+,.0f} MWh",
        delta=f"{delta_pct_est:+.1f}%",
        delta_color="inverse",
    )

st.divider()

# ---------------------------------------------------------------------------
# Section 3 — Sensitivity analysis (loss parameter)
# ---------------------------------------------------------------------------

st.header("3. Sensitivity analysis — paramètre `loss`")

st.markdown(
    "Le paramètre PVGIS `loss` est le principal levier d'incertitude. Trois scénarios "
    "(10% / 14% / 18%) bornent l'estimation annuelle. Reported figure affichée séparément."
)

st.markdown(
    f"**Reported (Allianz PR {REPORTED_YEAR}) — {REPORTED_ANNUAL_MWH:,.0f} MWh/an.** "
    f"Source : {REPORTED_SOURCE}."
)

try:
    sensitivity = _cached_sensitivity(
        lat=float(lat),
        lon=float(lon),
        peakpower_mw=float(park.capacity_mwp),
    )
except Exception as exc:  # noqa: BLE001 — l'analyste doit voir l'erreur, pas un crash
    logger.warning("Sensibilité PVGIS indisponible : %s", exc)
    st.warning(
        "Sensibilité PVGIS indisponible (réseau ou endpoint JRC). "
        "Réessayer dans quelques minutes."
    )
else:
    # On reconstruit un tableau ordonné par loss croissant (10 → 18%)
    by_loss = sorted(sensitivity["scenarios"], key=lambda s: s["loss_pct"])

    rows = []
    for scenario in by_loss:
        loss_pct = scenario["loss_pct"]
        annual_mwh = scenario["annual_kwh"] / 1000.0
        delta_pct = (annual_mwh - REPORTED_ANNUAL_MWH) / REPORTED_ANNUAL_MWH * 100.0
        if loss_pct <= 10.0:
            label = f"{loss_pct:.0f}% (high)"
        elif loss_pct >= 18.0:
            label = f"{loss_pct:.0f}% (low)"
        else:
            label = f"{loss_pct:.0f}% (mid)"
        rows.append(
            {
                "Loss scenario": label,
                "Annual estimate (MWh)": f"{annual_mwh:,.0f}",
                "Delta vs reported": f"{delta_pct:+.1f}%",
            }
        )

    st.table(pd.DataFrame(rows))

    st.caption(
        f"Encadrement : low={sensitivity['low_mwh']:,.0f} MWh · "
        f"mid={sensitivity['mid_mwh']:,.0f} MWh · "
        f"high={sensitivity['high_mwh']:,.0f} MWh "
        "(low = pertes max, high = pertes min). Cache 1h."
    )

st.divider()

# ---------------------------------------------------------------------------
# Section 4 — Méthodologie (collapsible)
# ---------------------------------------------------------------------------

with st.expander("📐 Méthodologie", expanded=False):
    inputs = _load_pvgis_inputs()
    tilt_used = f"{inputs['tilt_deg']:.1f}°" if inputs else "lat - 10°"
    azimuth_used = f"{inputs['azimuth_deg']:.0f}° (sud)" if inputs else "0° (sud)"

    st.markdown(
        f"""
- **Endpoint** : PVGIS PVcalc v5.2 (JRC EU), TMY agrégé 2005-2020.
- **Loss default** : 14% (PVGIS) — variation 10% / 18% pour borner l'estimation.
- **Tilt** : `{tilt_used}` — fixed mounting, pas de tracker single-axis ou dual-axis.
- **Azimuth** : `{azimuth_used}` — orientation plein sud par convention.
- **Reported figure** : 80 000 MWh/an — dérivé de l'estimation commissioning Allianz PR
  (~23 000 foyers × ~3.5 MWh/foyer/an, moyenne EU). Pas une mesure opérateur live.
- **Severity thresholds** (`compute_delta.py`) :
  - 🟢 GREEN : `|delta| < 5%` — alignée avec l'estimation.
  - 🟡 YELLOW : `5% ≤ |delta| < 10%` — modéré, à vérifier.
  - 🔴 RED : `|delta| ≥ 10%` — significatif, investiguer.

Voir la **page 5 (📐 Methodology)** pour le détail complet des hypothèses et limites.
"""
    )

# Affichage delta existant (depuis delta.json)
delta = _load_delta()
if delta:
    severity = delta.get("severity", "green")
    color = SEVERITY_COLORS.get(severity, "#475569")
    emoji = {"green": "🟢", "yellow": "🟡", "red": "🔴"}.get(severity, "⚪")
    st.markdown(
        f"<div style='border-left: 4px solid {color}; padding: 8px 12px; "
        f"background: rgba(148,163,184,0.08); border-radius: 4px;'>"
        f"<strong>{emoji} Severity {severity.upper()}</strong> — "
        f"{delta.get('interpretation', '')}"
        f"</div>",
        unsafe_allow_html=True,
    )

st.divider()

# ---------------------------------------------------------------------------
# Section 5 — Sources
# ---------------------------------------------------------------------------

st.header("5. Sources")

st.markdown(
    f"""
- **Allianz Capital Partners — press release Ourika (oct. 2018)** :
  [{park.press_release_url}]({park.press_release_url})
- **PVGIS officiel (JRC, European Commission)** :
  [https://re.jrc.ec.europa.eu/pvg_tools/en/](https://re.jrc.ec.europa.eu/pvg_tools/en/)
- **`data/parks_index.yaml`** (master index, GitHub raw) :
  [{GITHUB_RAW_BASE}/parks_index.yaml]({GITHUB_RAW_BASE}/parks_index.yaml)
- **`data/reported_production.yaml`** (production publiée seed, GitHub raw) :
  [{GITHUB_RAW_BASE}/reported_production.yaml]({GITHUB_RAW_BASE}/reported_production.yaml)
"""
)

st.caption(
    "Démonstration construite sur sources publiques uniquement (JRC EU Commission, "
    "Allianz Capital Partners press releases). Aucune affiliation Allianz."
)
