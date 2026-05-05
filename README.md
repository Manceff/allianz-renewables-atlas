# Allianz Renewables Atlas

> Plateforme d'estimation de la production solaire des parcs photovoltaïques associés à
> Allianz Capital Partners et identifiés via sources publiques uniquement (2010-2026).
> Reconstruction hour-by-hour via `pvlib` + Open-Meteo Archive aux coordonnées exactes
> de chaque parc, revenue ancré sur les prix day-ahead ENTSO-E, LMP CAISO ou tarif
> Conto Energia selon la juridiction.

**8 parcs détenus · 586 MWp · 5 pays** (IT, PT, FR, US, ES). +1 parc inclus pour contexte
stratégique (Solara 4 — deal Allianz × WElink échoué). Sources : 100 % publiques, citées
par parc dans le YAML d'index.

**Live :** [allianz-renewables-atlas.streamlit.app](https://allianz-renewables-atlas-mancef-ferrah.streamlit.app/)

## Démarche

Projet personnel initié par Mancef Ferrah dans le cadre d'une candidature en alternance
Investment Management. L'atlas démontre une chaîne complète de raisonnement quantitatif sur
des actifs renewables réels :

1. **Identification** — cartographier les parcs solaires associés à ACP via press releases,
   filings IR de contreparties (Grenergy, Avantus, BayWa), CPUC, GSE Atlaimpianti
2. **Reconstruction physique** — pvlib aux coordonnées GPS exactes : POA Hay-Davies,
   Sandia cell temp, PVWatts DC, inverter clipping DC/AC=1.30, 14 % losses
3. **Météo** — Open-Meteo Archive (ECMWF reanalysis), publishing lag 5 jours
4. **Pricing** — ENTSO-E day-ahead pour l'EU (energy-charts.info mirror), CAISO OASIS
   pour la Californie, Conto Energia pour les actifs italiens
5. **Revenue** — chaque MWh produit × prix horaire, post-cannibalisation visible. Pour
   l'Italie : FiT contractuel + vente marché horaire (modèle dual Conto Energia)

## Périmètre

| # | Parc | Pays | Capacité | Régime de revenu |
|---|---|---|---|---|
| 1 | Manzano | IT (Friuli) | 11.2 MWp | Conto Energia II + market sale |
| 2 | SiSen Foggia | IT (Pouilles) | 8 MWp | Conto Energia III + market sale |
| 3 | Ourika | PT (Alentejo) | 46 MWp | Subsidy-free PPA Audax |
| 4 | Solara 4 | PT (Algarve) | 219 MWp | Deal Allianz × WElink échoué — opéré par WElink, inclus pour contexte |
| 5 | Lacs Médocains AREF II | FR (Gironde) | 9.4 MWp | Marché libre |
| 6 | Lotus Solar Farm | US-CA | 67 MWp | PPA Southern California Edison |
| 7 | Galloway 2 | US-TX | 147 MWp | PPA EDF Energy Services |
| 8 | Tabernas | ES (Andalousie) | 250 MWp | Marché libre |
| 9 | José Cabrera | ES (Castilla-La Mancha) | 47 MWp | Marché libre |

**Out of scope** : Elgin Ireland Portfolio (191 MWp / 16 sites) — forward sale signée
décembre 2023, panneaux pas encore tous construits ni raccordés au réseau.

## Captures

### Live · right now (Manzano, IT)

Production live estimée + prix spot day-ahead temps réel + revenue/h. Pour les parcs
italiens sous Conto Energia, la métrique « Realised €/MWh (FiT + spot) » combine
le tarif contractuel (€318/MWh State-paid, locked jusqu'en 2030) et la vente marché
horaire IT-North. Toutes les heures sont affichées en heure locale du parc (CEST ici)
et le badge « PARK LOCAL · CEST · 23:30 · OFF » confirme l'état jour/nuit des panneaux.

![Manzano live](docs/screenshots/02-manzano-live.png)

### Revenue · last 12 months (Manzano sous Conto Energia)

T12M aligné sur les mois calendaires complets. Production reconstruite × prix horaire
sur 8 760 heures. Pour Manzano : FiT €318/MWh + spot IT-North horaire moyen
€123.4/MWh = prix réalisé €362.7/MWh, revenue total €5.51 M sur l'année roulante.
Cannibalisation solaire visible (-6.2 %) car la production solaire fait baisser les prix
de marché aux mêmes heures où elle injecte.

![Manzano revenue](docs/screenshots/03-manzano-revenue.png)

### Live US (Galloway 2, Texas)

Pour les parcs US, l'heure locale du parc est calculée correctement (CDT ici, alors
qu'on consulte depuis l'Europe en CEST). Production réelle reconstituée
(97.2 MW = 66 % de la capacité, 780 W/m² sous 34.3 °C Texas heat). ERCOT MIS étant
auth-walled depuis 2025, le spot price est affiché en « — » avec un tooltip
explicatif plutôt qu'un fallback fudgé. Lotus (US-CA) en revanche dispose
du LMP CAISO en direct via OASIS.

![Galloway live](docs/screenshots/04-galloway-us.png)

## Stack technique

- **Frontend** : Streamlit avec custom component `globe_picker` (globe.gl + Three.js,
  NASA Blue Marble), `coord_picker` (Leaflet + Esri World Imagery)
- **Production** : `pvlib` (POA Hay-Davies, Sandia cell temp, PVWatts DC,
  inverter clipping DC/AC=1.30, 14 % losses), météo via Open-Meteo Archive
- **Prix EU** : `energy-charts.info` (mirror ENTSO-E day-ahead, hourly + 15-min depuis oct 2025)
- **Prix US** : appel direct OASIS HTTPS (urllib stdlib, pas de gridstatus) pour CAISO LMP
- **Italian Conto Energia** : tarifs CE II/III + Spalma-Incentivi 2014 (-8 % pour P > 900 kW)
  appliqués manuellement (GSE Atlaimpianti requiert credentials)
- **Cartes Spotlight** : Esri World Imagery (satellite)

## Lancer en local

```bash
git clone https://github.com/Manceff/allianz-renewables-atlas.git
cd allianz-renewables-atlas
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run src/app.py
```

L'app se lance sur `http://localhost:8501`. Aucun secret nécessaire — toutes les APIs
sont publiques (Open-Meteo, energy-charts.info, CAISO OASIS, Esri tile server).

**Deep links** : `?park=<id>` ouvre directement la page parc, par exemple
`http://localhost:8501/?park=manzano-solar`.

## Architecture des données

```
data/
├── parks_index.yaml          # Master config 9 parcs + sub-sites + FiT rates
├── coord_overrides.yaml      # GPS corrections user-curated par parc
├── reported_production.yaml  # MWh annuels publiés par opérateurs (cross-check)
├── electricity_prices/       # Cache local prix horaires par zone × année
└── production_pvlib/         # Cache local pvlib reconstruction
```

```
src/
├── app.py                    # Page Streamlit unique (header → globe → detail panel)
├── lib/
│   ├── parks_loader.py       # Pydantic v2 schema + YAML loader (cached)
│   ├── solar_model.py        # pvlib pipeline (compute_period_production, ...)
│   ├── electricity_prices.py # energy-charts EU + hour-bucket resampling
│   ├── electricity_prices_us.py # CAISO OASIS HTTPS direct (stdlib only)
│   ├── live_weather.py       # Open-Meteo current + today-hourly
│   └── portfolio_model.py    # Multi-site aggregate (forward-sale code path)
├── components/
│   ├── globe_picker/         # 3D globe with click → park selection
│   └── coord_picker/         # Esri map with dblclick → save coords
└── assets/
    └── style.css             # Bone editorial palette, mono numerics
```

## Méthodologie

Voir le panneau « How to read the sections » en bas de chaque page parc (expander
Streamlit) pour le détail de chaque section et de ses sources.

## Disclaimer

Ce projet est une démarche personnelle en post-entretien pour montrer la qualité de
raisonnement quantitatif sur le périmètre Renewables d'Allianz. Aucune donnée
propriétaire d'Allianz Capital Partners n'est utilisée. Toutes les sources sont
citées dans le YAML d'index ou les press releases linkées dans le panneau détail
de chaque parc. Le statut d'ownership de certains assets (en particulier les actifs
italiens acquis 2010-2013) peut avoir évolué depuis ; l'atlas reflète l'état issu
des sources publiques disponibles, pas une garantie de détention au jour le jour.
