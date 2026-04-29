"""Page Méthodologie — sources, formules, hypothèses, limites.

Destinataire : analyste Allianz Investment Management. Ton factuel, sourcé,
sans marketing. Référence du code : `src/lib/compute_delta.py`.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Methodology — Allianz Renewables Atlas",
    page_icon="📐",
    layout="wide",
)

st.title("📐 Methodology")

st.markdown(
    "Cette page documente les sources, formules, hypothèses et limites "
    "qui sous-tendent les chiffres affichés dans l'atlas. Toute valeur "
    "présentée ailleurs dans l'application doit être traçable à un élément "
    "listé ci-dessous."
)

st.divider()

# ---- 1. Sources ----
st.header("1. Sources")

st.markdown(
    """
- **PVGIS v5.2** (JRC, European Commission) — outil de référence européen
  pour l'estimation de production photovoltaïque.
  <https://re.jrc.ec.europa.eu/pvg_tools/en/>
- **`data/parks_index.yaml`** — liste master des parcs, curée à la main
  depuis les press releases publiques d'Allianz Capital Partners et
  d'Allianz Group. Une URL source est conservée dans le YAML par parc.
  Voir le fichier dans le dépôt GitHub (`data/parks_index.yaml`).
- **`data/reported_production.yaml`** — chiffres de production publiés,
  curés à la main depuis les communiqués des opérateurs partenaires
  (WElink, EDP, RWE, Equinor, etc.). Une URL source est conservée par
  ligne pour permettre la vérification.
"""
)

st.divider()

# ---- 2. Formule PVGIS ----
st.header("2. Formule PVGIS")

st.markdown(
    """
L'endpoint PVGIS **PVcalc** calcule la production annuelle d'énergie
*E* (kWh/an) à partir des coordonnées du site, de la capacité installée
et d'un jeu d'hypothèses standardisées :

```
E ≈ peakpower (kWp) × specific_yield(lat, lon, tilt, azimuth) × (1 − loss/100)
```

où :

- **`specific_yield`** = irradiation annuelle moyenne × performance ratio,
  calculé par PVGIS sur la base d'une *Typical Meteorological Year* (TMY)
  agrégée sur la fenêtre 2005-2020.
- **`tilt`** et **`azimuth`** sont gérés en interne par PVGIS. Pour les
  parcs sans donnée publique sur la géométrie de l'installation, on
  applique une simplification : `tilt = lat` (axe nord-sud), `azimuth = 0`.
  Voir l'implémentation dans `src/lib/pvgis_fetch.py`.

Référence officielle PVGIS :
<https://joint-research-centre.ec.europa.eu/photovoltaic-geographical-information-system-pvgis_en>
"""
)

st.divider()

# ---- 3. Hypothèses ----
st.header("3. Hypothèses (default values)")

hypotheses_df = pd.DataFrame(
    [
        {
            "Paramètre": "Loss",
            "Valeur": "14%",
            "Justification": (
                "Default PVGIS — couvre inverter + cabling + mismatch + "
                "soiling baseline."
            ),
        },
        {
            "Paramètre": "TMY",
            "Valeur": "2005-2020",
            "Justification": (
                "Typical Meteorological Year — pas de météo live, "
                "fenêtre 16 ans agrégée."
            ),
        },
        {
            "Paramètre": "Mounting",
            "Valeur": "fixed",
            "Justification": "Pas de tracker (single-axis ou dual-axis).",
        },
        {
            "Paramètre": "Shading model",
            "Valeur": "none",
            "Justification": "Aucun modèle d'ombrage local appliqué.",
        },
        {
            "Paramètre": "Soiling model",
            "Valeur": "none",
            "Justification": (
                "Pas de modèle dédié au-delà du loss baseline 14%."
            ),
        },
        {
            "Paramètre": "Degradation",
            "Valeur": "none",
            "Justification": (
                "Estimations équivalent year-1, pas multi-year."
            ),
        },
    ]
)

st.dataframe(hypotheses_df, hide_index=True, width="stretch")

st.divider()

# ---- 4. Sensitivity analysis ----
st.header("4. Sensitivity analysis (loss parameter)")

st.markdown(
    "Le paramètre `loss` est le principal levier d'incertitude du modèle. "
    "Trois scénarios sont utilisés pour borner l'estimation :"
)

sensitivity_df = pd.DataFrame(
    [
        {
            "Loss scenario": "10%",
            "Description": (
                "Optimistic — clean panels, modern inverters."
            ),
            "Confidence interval role": "Upper bound (high)",
        },
        {
            "Loss scenario": "14%",
            "Description": (
                "PVGIS default — typical operating conditions."
            ),
            "Confidence interval role": "Central estimate (mid)",
        },
        {
            "Loss scenario": "18%",
            "Description": (
                "Conservative — older inverters or partial shading."
            ),
            "Confidence interval role": "Lower bound (low)",
        },
    ]
)

st.table(sensitivity_df)

st.divider()

# ---- 5. Limites ----
st.header("5. Limites")

st.markdown(
    """
- La majorité des parcs n'ont pas de production mensuelle publique →
  la comparaison estimée vs publiée est limitée à l'**annuel**.
- **Précision géocodage** : lat/lon à ±0.05° (≈ 5 km) pour les sites
  sans municipalité publiée.
- Les estimations PVGIS sont **TMY-based** : elles ne reflètent **pas**
  la météo d'une année spécifique.
- Le **Performance Ratio est implicite** dans la sortie PVGIS — pas de
  calibration site-specific disponible publiquement.
- La production **éolienne n'est PAS estimée** (PVGIS = solaire
  uniquement). Pour l'éolien, voir `windpowerlib` ou ERA5 — hors
  scope de cet atlas.
"""
)

st.divider()

# ---- 6. Severity thresholds ----
st.header("6. Severity thresholds")

st.markdown(
    """
La logique de coloration green/yellow/red des deltas
(estimée − publiée) / publiée est implémentée dans
`src/lib/compute_delta.py` (fonction `severity_from_relative_delta`) :

- **GREEN** — `|delta_pct| < 5%` : *aligned with estimate*.
- **YELLOW** — `5% ≤ |delta_pct| < 15%` : *monitor — within model
  uncertainty*.
- **RED** — `|delta_pct| ≥ 15%` : *significant gap — investigate
  site-level factors*.

Ces seuils sont **commentary-grade**, pas regulatory : ils visent à
piloter la lecture analyste, pas à servir de seuil de conformité.
"""
)
