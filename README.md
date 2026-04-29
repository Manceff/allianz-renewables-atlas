---
type: project
status: active
updated: 2026-04-27
scope: alternance-allianz-alternative-assets
target: follow-up post-entretien — atlas visuel des parcs Renewables ACP
tags: [alternance, allianz, renewables, atlas, streamlit, pydeck, globe, sentinel-2, pvgis, copernicus, jrc, open-data, vibe-coding]
related: [[domains/alternance/README]], [[mancef-context]], [[wiki/synthesis/2026-04-25-allianz-alternance-ai-use-cases]]
deadline: ~4 jours d'effort vibe-codé
---

# Allianz Renewables Atlas

> Atlas interactif des parcs Renewables d'Allianz Capital Partners publiquement identifiables. Globe terrestre 3D rotatif avec ~20-30 parcs cartographiés, spotlight par parc avec image satellite Sentinel-2 et production estimée PVGIS pour les solaires. Data 100% publique, aucune affiliation Allianz.

## Vision produit

L'analyste alternance Allianz Alternative Assets ouvre un lien. Il voit un **globe terrestre 3D qui tourne**, avec des markers colorés sur l'Europe et les US — chaque marker = un parc Renewables d'ACP cartographié depuis leurs press releases publiques. Hauteur du marker proportionnelle à la capacité installée. Couleur par technologie (jaune = solar, vert = onshore wind, bleu = offshore wind).

Il fait tourner le globe à la souris. Il survole un marker — tooltip *"Galloper Offshore Wind, 353 MW, RWE/Allianz/Macquarie, 2018"*. Il clique. La page Spotlight s'ouvre : image Sentinel-2 récente du parc en mer du Nord, métadonnées, lien vers le press release ACP source. Pour les parcs solaires, en plus : production estimée mensuelle PVGIS comparée à la production publiée par l'opérateur.

C'est mémorable, c'est viscéralement parlant, c'est démonstration technique tangible.

## Périmètre assumé

**~20-30 parcs publiquement identifiables** (sur les 150+ revendiqués par ACP). Le compteur en haut du globe affiche transparemment *"23 parcs cartographiés / 150+ revendiqués par ACP"*. Le reste du portefeuille est détenu indirectement via fonds infra (Macquarie Infrastructure Fund V, Brookfield Infrastructure Partners, etc.) sans que ACP ne nomme publiquement les assets sous-jacents.

L'honnêteté du périmètre est elle-même un atout — l'analyste apprécie la rigueur intellectuelle qui assume la limite de la donnée publique.

## Pourquoi cette approche est différenciante

**Le globe 3D n'est pas un gadget**. C'est le format de visualisation que les hedge funds géospatiaux (Orbital Insight, RS Metrics) utilisent pour leurs présentations institutionnelles. Reproduire ce format en open source sur un portefeuille LP institutionnel = signal de sophistication immédiat.

**Pas un outil utilitaire — un récit visuel**. Tu ne livres pas une démo technique froide. Tu livres une carte vivante du portefeuille Renewables d'ACP que l'analyste peut explorer, partager en interne, commenter avec ses collègues.

**Couverture analytique variable selon le type d'infrastructure**. Pour les parcs solaires (~5-7 sur 23) : pipeline analytique complet (Sentinel-2 + PVGIS PVcalc + comparaison à production publiée). Pour les parcs éoliens (~13-18 sur 23) : monitoring visuel (image satellite + métadonnées). La méthodologie distingue clairement les deux niveaux.

## Live demo

Streamlit Cloud : https://allianz-renewables-atlas.streamlit.app/

## Pages

L'app Streamlit comporte 7 pages multi-onglets :

| Page | Description |
|------|-------------|
| 🌍 **Globe** | Globe 3D interactif des 23 parcs Renewables ACP cartographiés, avec toggle de coloration par sévérité du delta. |
| 📊 **Portfolio Sweep** | Production estimée vs publiée pour les 4 parcs solaires couverts, avec intervalle de confiance PVGIS. |
| 🔬 **Ourika Monograph** | Deep-dive sur le parc solaire portugais Ourika (46 MWp) : breakdown mensuel, sensibilité aux pertes, contexte projet. |
| 📈 **IC Snapshot** | Vue 30-secondes pour Investment Committee : 4 KPI portefeuille + top deltas. |
| 📐 **Methodology** | Sources, formules PVGIS, hypothèses, limites — méthodologie cliquable depuis l'app. |
| 📍 **Spotlight** | Vue détaillée d'un parc (image satellite, métadonnées, charts production pour les solaires). |
| ℹ️ **About** | Contexte projet, disclaimers, contact. |

## Architecture du projet

### Pages Streamlit

**Page 1 — Globe (page d'accueil)**
- Globe 3D PyDeck (`_GlobeView`) avec markers cliquables
- Filtres sidebar : pays, technologie (solar / onshore wind / offshore wind), capacité minimale, vintage d'acquisition
- Stats agrégées en haut : *"23 parcs cartographiés, 1.8 GW capacité couverte, 4.2 TWh production annuelle estimée"*
- Compteur transparence : *"23 / 150+ revendiqués ACP"*
- Hover tooltip avec nom, capacité, opérateur
- Click sur marker → navigation vers Spotlight

**Page 2 — Spotlight Parc**
- Image satellite Sentinel-2 récente (pré-fetched dans `data/parks/<id>/sentinel.png`)
- Carte zoom local Folium (vue régionale)
- Métadonnées : capacité installée, opérateur, mise en service, stake Allianz, lien press release ACP
- **Si solaire** : chart Plotly production estimée mensuelle (PVGIS) + comparaison production publiée + delta avec interprétation
- **Si éolien** : section "monitoring visuel uniquement" avec disclaimer méthodologique sur l'extension v2 windpowerlib
- Sélecteur de parc en sidebar pour explorer les autres parcs sans repasser par le globe

**Page 3 — About / Méthodologie**
- Disclaimers (sources publiques, absence d'affiliation Allianz)
- Tableau des sources : ESA Copernicus, JRC EU Commission, press releases ACP, opérateurs
- Limitation explicite : 23/150+ couverts, analyse production solaires only en v1
- Code GitHub linké
- Contact Mancef

## Stack technique

| Couche | Tech |
|---|---|
| Frontend | Streamlit multi-page |
| Globe 3D | PyDeck (`pydeck.Deck` avec `_GlobeView` et `ScatterplotLayer` + `ColumnLayer`) |
| Carte zoom local | Folium |
| Charts | Plotly |
| Imagerie satellite | Sentinel-2 RGB via Copernicus Data Space Ecosystem (free tier) |
| Production estimée solaire | PVGIS PVcalc API (Joint Research Centre EU, gratuit, sans clé) |
| Hébergement | Streamlit Community Cloud (gratuit) |
| Storage | Fichiers JSON/PNG/YAML versionnés dans le repo |

**Coût mensuel** : 0€ en running. ~3-5€ one-shot en dev pour les fetch initiaux Sentinel.

## Effort estimé

| Phase | Effort vibe-codé |
|---|---|
| Cartographie initiale 20-30 parcs (research + coordonnées + métadonnées) | 1-1,5 jour |
| Pré-calcul automatisé : Sentinel-2 + PVGIS pour chaque parc (script `precompute_all.py`) | 0,5 jour |
| Globe PyDeck interactif (Page 1) | 1 jour |
| Spotlight Parc dynamique (Page 2) | 0,75 jour |
| Page About + polish + déploiement | 0,5 jour |
| **Total** | **~4 jours vibe-codé** |

## Structure du repo

```
allianz-renewables-atlas/
├── README.md                      ← ce fichier
├── CLAUDE.md                      ← briefing Claude Code agents
├── requirements.txt
├── .env.example
├── .gitignore
├── .streamlit/config.toml         ← thème custom (couleurs Allianz)
├── data/
│   ├── parks_index.yaml           ← liste master des 20-30 parcs
│   └── parks/
│       ├── ourika/                ← solaire = pipeline complet
│       │   ├── metadata.json
│       │   ├── sentinel.png
│       │   ├── production_estimated.json
│       │   ├── production_reported.json
│       │   └── delta.json
│       ├── solara-4/              ← solaire
│       ├── grenergy-spain/        ← solaire
│       ├── galloper/              ← offshore wind = visuel only
│       │   ├── metadata.json
│       │   └── sentinel.png
│       ├── empire-wind-1/         ← offshore wind
│       ├── dahme/                 ← onshore wind
│       └── ...
├── src/
│   ├── app.py                     ← entry point Streamlit
│   ├── pages/
│   │   ├── 1_🌍_Globe.py
│   │   ├── 2_📍_Spotlight.py
│   │   └── 3_ℹ️_About.py
│   └── lib/
│       ├── __init__.py
│       ├── parks_loader.py
│       ├── globe_renderer.py
│       ├── sentinel_fetch.py
│       └── pvgis_fetch.py
└── scripts/
    └── precompute_all.py          ← exécuté en dev pour générer data/
```

## Sources de données

- **ESA Copernicus Data Space Ecosystem** : Sentinel-2 RGB imagery (gratuit, free tier 30k req/mois)
- **JRC EU Commission PVGIS** : production solaire estimée (gratuit, sans clé API)
- **Allianz Capital Partners Press Releases** : cartographie initiale des parcs (https://www.allianzcapitalpartners.com/en/media/news/)
- **OpenStreetMap** : géocodage précis
- **The Wind Power database** : cross-référencement coordonnées
- **Press releases opérateurs partenaires** : production rapportée (WElink, EDP, RWE, Equinor, etc.)

## Mail à l'analyste (template)

```
Bonjour [Prénom],

Pour donner suite à notre échange, j'ai construit un atlas interactif
des parcs Renewables d'Allianz Capital Partners — 23 parcs cartographiés
depuis vos press releases publiques, visualisés sur un globe terrestre 3D.

Pour chaque parc : image satellite Sentinel-2 récente + métadonnées.
Sur la fraction solaire (Ourika, Solara, Grenergy, Brindisi), j'ai
implémenté en plus l'estimation de production via PVGIS du Joint Research
Centre EU, comparée à la production publiée par l'opérateur.

Périmètre assumé : 23 parcs publiquement identifiables sur les 150+
revendiqués par ACP. Le reste du portefeuille (détenu indirectement
via fonds infra) n'est pas accessible publiquement.

Démo : [URL Streamlit]
Code : [URL GitHub]

Curieux de votre retour — y aurait-il des angles à ajouter pour le
rendre vraiment utile à votre équipe ?

Cordialement,
Mancef Ferrah
M1 Magistère Finance — Paris 1 Panthéon-Sorbonne
```

## Anti-patterns à éviter

- **Ne pas surclaim** "150+ parcs cartographiés". Toujours dire 23 / 150+.
- **Pas d'analyse production sur les wind** en v1. Disclaimer méthodologique clair.
- **Ne pas appeler l'outil "Atlas Allianz"** comme s'il était officiel — c'est *"Allianz Renewables Atlas (démo)"* avec disclaimer About absence d'affiliation.
- **Ne pas surcharger** le globe — max 30 markers, pas 100. Lisibilité avant densité.

## Prochaine action

Tes agents Claude Code peuvent attaquer phase par phase :

1. **Phase 1 (Jour 1)** — Cartographie initiale : remplir `data/parks_index.yaml` avec les 20-30 parcs, coordonnées, métadonnées. Research depuis press releases ACP + The Wind Power database + OpenStreetMap.

2. **Phase 2 (Jour 1-2)** — Précompute : `scripts/precompute_all.py` qui boucle sur les parcs, fetch Sentinel-2 + PVGIS PVcalc (pour solaires), commit les outputs dans `data/parks/<id>/`.

3. **Phase 3 (Jour 2-3)** — Globe : `src/pages/1_🌍_Globe.py` avec PyDeck `_GlobeView`, layers ScatterplotLayer + ColumnLayer, filtres sidebar.

4. **Phase 4 (Jour 3-4)** — Spotlight + About : pages dynamiques avec sélecteur de parc, charts production pour les solaires.

5. **Phase 5 (Jour 4)** — Polish + déploiement Streamlit Cloud + envoi mail analyste.
