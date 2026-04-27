"""Allianz Renewables Atlas — Streamlit entry point.

Multi-page app. Streamlit détecte automatiquement les pages dans src/pages/.
Cette page est la page d'accueil qui présente le projet en 30 secondes.
"""

from __future__ import annotations

import streamlit as st

st.set_page_config(
    page_title="Allianz Renewables Atlas",
    page_icon="🌍",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("Allianz Renewables Atlas")
st.subheader("Atlas interactif des parcs Renewables d'Allianz Capital Partners")

st.markdown(
    """
Bienvenue sur l'**Allianz Renewables Atlas**, une démonstration construite par
**Mancef Ferrah** (M1 Magistère Finance — Université Paris 1 Panthéon-Sorbonne).

Ce Lab cartographie les **parcs Renewables d'Allianz Capital Partners publiquement identifiables**
à partir de leurs press releases corporate et de la presse spécialisée. Pour chaque parc :
image satellite Sentinel-2 récente, métadonnées (capacité, opérateur, mise en service),
et — pour les parcs solaires — estimation de production via PVGIS du Joint Research Centre EU.

### Trois sections

#### 🌍 Globe interactif
Une terre 3D rotative avec 23 parcs cartographiés. Couleur par technologie, hauteur proportionnelle
à la capacité installée. Click sur un marker pour explorer.

#### 📍 Spotlight Parc
Image satellite récente, métadonnées, et — pour les solaires — comparaison entre la production
estimée par PVGIS et la production publiée par l'opérateur partenaire.

#### ℹ️ About
Méthodologie complète, sources publiques utilisées, disclaimers.

---

### Périmètre assumé

**23 parcs cartographiés sur les 150+ revendiqués** par Allianz Capital Partners. Le reste
du portefeuille est détenu indirectement via des fonds infrastructure (Macquarie Infrastructure,
Brookfield Infrastructure, etc.) sans nom public des assets sous-jacents.

### Sources publiques uniquement

- **ESA Copernicus** : imagerie Sentinel-2
- **Joint Research Centre EU Commission** : PVGIS (estimation production solaire)
- **Allianz Capital Partners** : press releases publiques
- **OpenStreetMap, The Wind Power database** : géocodage et métadonnées

Aucune donnée Allianz interne, aucun document privé, aucune affiliation.

---

👈 Sélectionne **Globe** dans la barre latérale pour explorer.
"""
)

st.divider()

col_a, col_b, col_c = st.columns(3)
with col_a:
    st.metric("Parcs cartographiés", "23 / 150+", help="23 parcs publiquement identifiables sur ~150 revendiqués par ACP")
with col_b:
    st.metric("Capacité couverte", "~1.9 GW", help="Capacité installée des parcs cartographiés")
with col_c:
    st.metric("Coût d'hébergement", "0 €/mois", help="Streamlit Cloud + APIs publiques gratuites")

st.caption(
    "Démonstration construite à des fins d'exploration — ne reflète pas les vues officielles d'Allianz. "
    "Code source GitHub : [URL]. Contact : le007du91@gmail.com"
)
