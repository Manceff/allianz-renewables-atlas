"""Methodology — sources, formules, hypothèses, limites lisibles par un analyste.

Tonalité factuelle, sourcée, sans marketing. Toute valeur affichée
ailleurs dans l'app doit être traçable à un élément listé ici.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Methodology — Allianz Renewables Atlas",
    page_icon="📐",
    layout="wide",
)

CSS_PATH = Path(__file__).resolve().parent.parent / "assets" / "style.css"
if CSS_PATH.exists():
    st.markdown(f"<style>{CSS_PATH.read_text()}</style>", unsafe_allow_html=True)

st.title("📐 Methodology")

st.markdown(
    "Cette page documente les sources, formules, hypothèses et limites "
    "qui sous-tendent les chiffres affichés dans l'atlas. Tout chiffre "
    "présenté ailleurs dans l'application doit être traçable à un élément "
    "listé ci-dessous."
)

st.divider()

# ---- 1. Sources ----
st.header("1. Sources")

st.markdown(
    """
- **PVGIS v5.2** — Photovoltaic Geographical Information System du JRC
  (Joint Research Centre, Commission européenne). Outil de référence pour
  l'estimation de production photovoltaïque. Gratuit, sans clé API.
  <https://re.jrc.ec.europa.eu/pvg_tools/en/>
- **`data/parks_index.yaml`** — liste curée à la main des 11 parcs
  solaires ACP publiquement identifiables (2010-2026). Sources :
  press releases ACP, Allianz Group, opérateurs partenaires
  (WElink, Grenergy, Avantus, Elgin, IBC Solar, BayWa). Cross-checked
  via Renewables Now, PV-Tech, GEM Wiki, et une recherche deep
  Gemini menée le 2026-04-30.
- **`data/reported_production.yaml`** — chiffres de production publiés,
  curés à la main. Une URL source par ligne pour vérification.
"""
)

st.divider()

# ---- 2. PVGIS — Le bon mental model ----
st.header("2. Comment fonctionne PVGIS")

st.markdown(
    """
PVGIS **n'est pas une simulation physique** d'un parc spécifique. C'est
un **estimateur statistique** qui combine trois choses :

1. **Une base de rayonnement solaire historique** (satellite ou réanalyse)
   sur 16 ans (2005-2020 pour SARAH-2/3 en Europe-Afrique).
2. **Un modèle physique simplifié** de panneau solaire qui convertit
   l'irradiance reçue en électricité produite.
3. **Des hypothèses standardisées de pertes** (par défaut 14%).

### L'analogie qui marche

> *« Quelle température fait-il à Paris le 30 avril ? »*

| Réponse A | Réponse B |
|---|---|
| **Climat moyen** | **Météo en vrai** |
| « Historiquement, un 30 avril c'est 14°C » | « Aujourd'hui à Paris, 19°C ciel clair » |
| Calculé sur 16 ans de relevés | Mesuré maintenant avec un thermomètre |

PVGIS = **réponse A appliquée au solaire**.

Il te dit : *« Un panneau de 1 MWp à cet endroit, sur un 30 avril
typique, devrait produire X MWh. »*

Il ne te dit **pas** : *« Aujourd'hui 30 avril, le parc Ourika a
produit Y MWh. »* — pour ça il faudrait un compteur sur place,
et cette donnée est privée à l'opérateur.
"""
)

st.divider()

# ---- 3. La formule de base ----
st.header("3. La formule simplifiée")

st.markdown(
    """
Chaque appel à PVGIS pour un parc donné calcule essentiellement :

```
production_kwh = peakpower_kwp
              × specific_yield(lat, lon, tilt, azimuth)
              × (1 − loss / 100)
```

où `specific_yield` est l'irradiation moyenne sur le plan du panneau
× le facteur de performance, calculé heure par heure sur l'année type
puis agrégé en mensuel/annuel.
"""
)

st.divider()

# ---- 4. Hypothèses par défaut ----
st.header("4. Hypothèses par défaut")

hypotheses_df = pd.DataFrame(
    [
        {"Paramètre": "Loss (pertes système)", "Valeur": "14 %", "Justification": "Default PVGIS — onduleur + câblage + mismatch + soiling baseline."},
        {"Paramètre": "TMY (année type)", "Valeur": "2005-2020", "Justification": "Typical Meteorological Year — moyenne climatique 16 ans."},
        {"Paramètre": "Année représentative (page Atlas)", "Valeur": "2019", "Justification": "Année climatiquement neutre dans la fenêtre SARAH ; choisie pour les calculs horaires."},
        {"Paramètre": "Tilt (inclinaison)", "Valeur": "lat - 10°", "Justification": "Approximation pour latitudes nord ; à raffiner si la géométrie réelle est publiée."},
        {"Paramètre": "Azimuth", "Valeur": "0° (sud)", "Justification": "Hypothèse standard pour optimisation solaire en hémisphère nord."},
        {"Paramètre": "Mounting", "Valeur": "fixed (free-standing)", "Justification": "Pas de tracker (single-axis ou dual-axis)."},
        {"Paramètre": "Technologie modules", "Valeur": "crystSi", "Justification": "Silicium cristallin, technologie dominante des parcs ACP."},
        {"Paramètre": "Shading & soiling spécifiques", "Valeur": "—", "Justification": "Aucun modèle local appliqué au-delà du loss baseline."},
        {"Paramètre": "Dégradation modules", "Valeur": "—", "Justification": "Estimations équivalent year-1, pas de courbe pluri-annuelle."},
    ]
)

st.dataframe(hypotheses_df, hide_index=True, width="stretch")

st.divider()

# ---- 5. Sensitivity analysis (loss) ----
st.header("5. Intervalle de confiance — sensitivity sur les pertes")

st.markdown(
    "Le paramètre `loss` est le principal levier d'incertitude du modèle. "
    "Pour chaque parc, on calcule trois scénarios :"
)

sensitivity_df = pd.DataFrame(
    [
        {"Loss": "10 %", "Description": "Optimiste — panneaux propres, onduleurs récents.", "Rôle": "Borne haute (high)"},
        {"Loss": "14 %", "Description": "Default PVGIS — conditions opérationnelles typiques.", "Rôle": "Estimation centrale (mid)"},
        {"Loss": "18 %", "Description": "Conservateur — onduleurs vieillissants, ombrage partiel, soiling élevé.", "Rôle": "Borne basse (low)"},
    ]
)
st.table(sensitivity_df)

st.divider()

# ---- 6. Lecture honnête du delta ----
st.header("6. Lire le delta (estimé vs publié)")

st.markdown(
    """
Quand on affiche par exemple « Ourika : delta -8.1 % », on compare :

| Estimé PVGIS | Publié Allianz |
|---|---|
| Année climatique **moyenne** | Année **réelle** de commissioning (2018) |
| Pertes **par défaut** 14 % | Pertes **réelles** spécifiques |
| Panneaux **génériques** crystSi | Panneaux **spécifiques** déployés |
| Géométrie **simplifiée** (tilt = lat) | Géométrie **réelle** |

**Donc -8.1 % ne signifie PAS « le parc sous-performe ».** Ça peut vouloir dire :

- L'année 2018 a été climatiquement supérieure à la moyenne
- Les pertes réelles 2018 étaient < 14 %
- Le chiffre press release a été arrondi vers le haut (marketing)
- Les panneaux sont mieux orientés que notre simplification
- ... ou une combinaison

Le delta est un **point de départ d'analyse**, pas un verdict de performance.

### Code de couleur

| Severity | Critère | Lecture |
|---|---|---|
| 🟢 Green | \\| delta \\| < 5 % | aligné avec l'estimation |
| 🟡 Yellow | 5 % ≤ \\| delta \\| < 10 % | dans l'incertitude du modèle, à monitorer |
| 🔴 Red | \\| delta \\| ≥ 10 % | écart significatif, mérite investigation |

Ces seuils sont **commentary-grade**, pas regulatory. Ils visent à
piloter la lecture analyste.
"""
)

st.divider()

# ---- 7. Limites assumées ----
st.header("7. Ce que PVGIS ne sait pas")

st.markdown(
    """
| ✅ PVGIS sait | ❌ PVGIS ne sait pas |
|---|---|
| Moyennes climatiques 16 ans | Météo d'une année spécifique (2024, 2025…) |
| Hypothèses standard de site | Ombrage spécifique (collines, arbres, bâtiments) |
| Mounting fixe ou tracker mono-axe | Géométrie réelle d'un parc précis |
| Technologies génériques (crystSi, CIS, CdTe) | Marque / modèle exact des modules |
| Pertes nominales 14 % | Pertes opérationnelles réelles |
| Production « année type » | Dégradation des panneaux dans le temps |
| 8760 valeurs horaires | Curtailment réseau (coupures forcées) |

PVGIS reste **la référence** utilisée par la Commission européenne,
les régulateurs énergétiques, et les développeurs en pré-bancabilité.
Sa rigueur est dans la transparence des hypothèses, pas dans la
précision météo en temps réel.
"""
)

st.divider()

# ---- 8. Hors périmètre V1 ----
st.header("8. Hors périmètre V1")

st.markdown(
    """
- **Éolien (onshore + offshore)** — PVGIS = solaire only. Les parcs éoliens
  ACP existent (Maevaara, Galloper, Hollandse Kust Zuid…) mais leur
  estimation rigoureuse demanderait `windpowerlib` + ERA5 (creds Copernicus
  bloqués) avec une précision ±15 % inférieure au standard PVGIS.
- **Battery storage (BESS)** — pas de notion publique de « production »
  pour du stockage. Les chiffres sont des cycles × capacité × efficiency,
  données opérationnelles privées.
- **Données live / temps réel** — toute production affichée est une
  estimation climatique TMY, jamais une mesure du jour.
- **Sentinel-2 imagery** — désactivée en V1 (creds Copernicus Data Space
  non disponibles).
"""
)

st.divider()

st.markdown(
    """
*Méthodologie versionnée à 2026-04-30. Toute évolution future
sera tracée dans `agent-log.md` et `IMPROVEMENT_REPORT.md`.*
"""
)
