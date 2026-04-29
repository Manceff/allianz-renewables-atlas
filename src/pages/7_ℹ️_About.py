"""Page About / Méthodologie — transparence sur sources, scope, disclaimers."""

from __future__ import annotations

import streamlit as st
import pandas as pd

st.set_page_config(page_title="About — Allianz Renewables Atlas", page_icon="ℹ️", layout="wide")

st.title("ℹ️ About / Méthodologie")

st.markdown(
    """
## Pourquoi ce Lab

Cet atlas est une démonstration construite par **Mancef Ferrah**, étudiant en M1 Magistère Finance
à l'Université Paris 1 Panthéon-Sorbonne, en échange académique à l'Université de Bologne. Il
donne suite à un échange avec un analyste de l'équipe Alternative Assets d'Allianz Investment
Management à Paris La Défense.

L'objectif est de **cartographier visuellement les parcs Renewables d'Allianz Capital Partners
publiquement identifiables**, sur sources publiques uniquement. C'est une démonstration de
capacité technique, pas un produit fini.

Cet outil **n'est pas affilié à Allianz, ni à AIM, ni à aucune entité du groupe**. Les données
et interprétations sont les miennes.
"""
)

st.divider()

# ---- Sources ----
st.markdown("## Sources de données")

sources_df = pd.DataFrame(
    [
        {
            "Catégorie": "Imagerie satellite",
            "Source": "ESA Copernicus Sentinel-2",
            "License": "Copernicus License (libre redistribuable)",
        },
        {
            "Catégorie": "Production solaire estimée",
            "Source": "PVGIS — Joint Research Centre EU Commission",
            "License": "Public, sans clé API",
        },
        {
            "Catégorie": "Cartographie parcs",
            "Source": "Allianz Capital Partners Press Releases",
            "License": "Public corporate communications",
        },
        {
            "Catégorie": "Coordonnées GPS",
            "Source": "OpenStreetMap, The Wind Power Database",
            "License": "ODbL / public",
        },
        {
            "Catégorie": "Production publiée",
            "Source": "Press releases opérateurs (WElink, EDP, RWE, Equinor, etc.)",
            "License": "Public corporate communications",
        },
    ]
)

st.dataframe(sources_df, hide_index=True, width="stretch")

st.divider()

# ---- Périmètre ----
st.markdown("## Périmètre assumé")

st.markdown(
    """
**23 parcs cartographiés sur les 150+ revendiqués par Allianz Capital Partners.**

Le reste du portefeuille (>120 parcs) est détenu **indirectement via des fonds infrastructure**
(Macquarie Infrastructure Fund V, Brookfield Infrastructure Partners, Antin Infrastructure Partners,
etc.) sans que ACP ne nomme publiquement les assets sous-jacents. Cette fraction du portefeuille
n'est donc pas accessible à un observateur externe.

Le **compteur transparent** affiché sur le globe (*"23 parcs cartographiés / 150+ revendiqués"*)
assume cette limite de la donnée publique.
"""
)

st.divider()

# ---- Méthodologie analytique ----
st.markdown("## Méthodologie analytique")

st.markdown(
    """
### Pour les parcs solaires PV (5-7 parcs)

Pipeline complet :
1. **Imagerie** : récupération de l'image Sentinel-2 RGB la plus récente (cloud cover <20%) via Copernicus Data Space Ecosystem
2. **Irradiance** : récupération de l'historique d'irradiance via PVGIS PVcalc (un appel API JRC EU)
3. **Estimation production** : PVGIS calcule directement la production mensuelle à partir des coordonnées + capacité installée + tilt/azimuth (hypothèse standard latitude − 10°)
4. **Production publiée** : extraction manuelle depuis les rapports annuels ou ESG reports des opérateurs partenaires (WElink, EDP, etc.)
5. **Delta** : calcul (estimée - publiée) / publiée. Severity green si <5%, yellow si 5-10%, red si >10%

Marge d'erreur attendue : 5-15% (modèle PVGIS + hypothèses tilt/azimuth).

### Pour les parcs éoliens onshore et offshore

**v1 : monitoring visuel uniquement.** Image Sentinel-2 (ou Sentinel-1 SAR pour offshore) + métadonnées (capacité, opérateur, mise en service). Pas d'estimation de production en v1.

**v2 prévue** : intégration de `windpowerlib` (équivalent Python pour éolien) + données vent ECMWF ERA5 (Copernicus Climate Data Store) + courbes de puissance des turbines (Vestas, Siemens Gamesa, etc.).
"""
)

st.divider()

# ---- Disclaimers ----
st.markdown("## Disclaimer politique")

st.warning(
    """
Cet outil est une **démonstration personnelle**, sans affiliation à Allianz, à AIM, ou à aucune
entité du groupe. Les vues et interprétations exprimées sont celles de Mancef Ferrah uniquement
et ne sauraient engager la position officielle d'Allianz.

**Aucun document confidentiel, aucune donnée Allianz interne, aucun reporting GP n'est utilisé.**
Toutes les sources sont publiques au sens des Public Records Acts, des publications corporate, ou
des programmes open data européens (Copernicus, JRC).

Pour un déploiement institutionnel européen, une variante self-hosted serait recommandée pour
répondre aux contraintes de souveraineté DORA et RGPD.
"""
)

st.divider()

# ---- Code source ----
st.markdown("## Code source")

st.markdown(
    """
Le code source de ce Lab est public sur GitHub : **[github.com/mancef/allianz-renewables-atlas](https://github.com/)**

Stack : Streamlit + PyDeck + Folium + Plotly + Sentinel-2 + PVGIS. Toute la chaîne est reproductible
en local en 30 minutes. Sources et paramètres configurables via fichiers YAML.
"""
)

st.divider()

# ---- Contact ----
st.markdown("## Contact")

st.markdown(
    """
**Mancef Ferrah**

- Étudiant M1 Magistère Finance — Université Paris 1 Panthéon-Sorbonne
- Échange académique — Université de Bologne (2025-2026)
- 📧 le007du91@gmail.com

*Très intéressé d'avoir vos retours sur la pertinence de cet exercice.*
"""
)
