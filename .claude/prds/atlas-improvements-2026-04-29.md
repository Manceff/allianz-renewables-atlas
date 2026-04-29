---
type: prd
slug: atlas-improvements-2026-04-29
status: active
created: 2026-04-29
horizon: 7d
target: Demo-ready repo for Allianz Investment Management analyst review (alternance follow-up)
---

# PRD — Atlas Improvements 2026-04-29

## 1. Contexte

L'Atlas Renewables est en post-Phase 4 (UI polish + CI cron livrés). 23 parcs cartographiés, 4 libs TDD avec 59/59 tests pass, mais le **différenciateur central** — le delta production estimée vs publiée — n'existe que sur **1 parc** (Ourika, -8.1% yellow). Le projet doit être présenté à un analyste Allianz Investment Management dans 7 jours, en mode follow-up post-entretien d'alternance.

## 2. Signal cible

**Mix 70/30 :**

- **70% rigueur quantitative.** L'analyste doit retenir : "ce candidat sait challenger une production publiée avec PVGIS, intervalle de confiance, et écart versionné". Le delta est le héros.
- **30% storytelling Investment Committee.** Le portefeuille de 23 parcs doit être lisible en 30 secondes par un IC reader (capacité, géographie, vintage, severity du delta).

Le craft (tests, schemas, CI, structure) reste un **sous-jacent invisible** : si l'analyste creuse le code, il voit la qualité ; on ne le vend pas frontalement.

## 3. Décisions par défaut

> Ces décisions ont été prises sans validation explicite utilisateur. Elles peuvent être challengées après livraison.

| ID | Décision | Justification |
|----|----------|---------------|
| D1 | Sentinel-2 = **SKIPPED** sur 7j | Creds CDSE absents, OAuth Copernicus = risque non-maîtrisable dans la fenêtre. Hors chemin critique pour le signal "rigueur quanti". |
| D2 | Approche hybride **portfolio sweep (3-5 deltas) + Ourika deep-dive** | Match 70/30 : sweep = portfolio storytelling, Ourika = profondeur méthodo. |
| D3 | Confidence interval = **sensitivity sur PVGIS `loss` ∈ {10%, 14%, 18%}** | Le `loss` parameter est l'hypothèse la plus opaque et la plus impactante (±~5% sur l'estimation). Bornes basées sur la doc JRC. |
| D4 | Production publiée = **YAML curated** dans `data/reported_production.yaml` | Pas de scraping live (interdit par CLAUDE.md). Sources tracées par URL pour chaque chiffre. |
| D5 | PDF export = **CSS print stylesheet** + bouton "Print to PDF" via le navigateur | Pas de dépendance lourde (`weasyprint`/`playwright`). YAGNI : un IC reader imprime depuis Chrome. |
| D6 | Schemas Pydantic v2 stricts sur **outputs JSON** (`pvgis.json`, `delta.json`, `metadata.json`) | Ferme le blast radius identifié par l'analyse GitNexus : les frontières réelles entre libs et UI sont les fichiers JSON, pas les call edges. |
| D7 | Méthodologie = **page Streamlit dédiée** `4_📐_Methodology.py` | Plus visible qu'un README pour un analyste qui survole l'app. Cite sources, formules, biais. |
| D8 | Globe coloration severity = **couche additionnelle PyDeck** sur le globe existant | Pas de refonte. Couleur du marker = severity du delta (green/yellow/red/grey si pas de delta). |
| D9 | Production publiée non-trouvable → parc **exclu du sweep** mais reste sur le globe | Honnêteté intellectuelle. Mieux 4 deltas vraies que 7 deltas bidon. |
| D10 | Tests TDD enforced sur toutes les nouvelles libs | Conformité CLAUDE.md "TDD privilégié". 59 tests existants + ~25 nouveaux attendus. |

## 4. Features (3 + 1 fondation)

### Feature 1 — Portfolio Sweep Delta (priorité P0, 70% du signal)

**Objectif :** passer de 1 à 4-5 deltas calculés sur les parcs solaires, chacun avec intervalle de confiance.

**Livrables :**

- `src/lib/confidence_interval.py` — fonction `compute_pvgis_range(park, loss_scenarios=[10, 14, 18])` qui retourne `(low, mid, high)` en MWh/an.
- `data/reported_production.yaml` — production publiée par parc (sources URL traçables, "null" assumé si non public).
- `src/pages/2_📊_Portfolio_Sweep.py` — bar chart Plotly horizontal : un bar par parc, range estimé (low-high) en barre, point production publiée, color severity (green/yellow/red/grey).
- Re-run `precompute_all.py` génère un `portfolio_sweep.json` agrégeant les deltas + intervalles.

**Critère de succès :** ≥ 4 parcs solaires avec delta + interval + production publiée affichés sur la page sweep.

### Feature 2 — Ourika Monograph (priorité P0, deep-dive quanti)

**Objectif :** une page de référence sur Ourika qui démontre la profondeur d'analyse possible avec PVGIS.

**Livrables :**

- `data/parks/ourika/pvgis_monthly.json` — production mensuelle estimée (PVGIS retourne déjà `outputs.monthly` dans la réponse PVcalc).
- `src/pages/3_🔬_Ourika_Monograph.py` — chart Plotly mensuel (12 barres estimé + ligne publiée si dispo), encadré sensitivity (3 scénarios loss), bloc méthodo + sources, lien press release ACP.
- Si la production mensuelle publiée n'est pas dispo (cas le plus probable) : graphe annuel + breakdown mensuel estimé seul, avec note explicite.

**Critère de succès :** la page Ourika rend en < 2s, avec chart mensuel + tableau sensitivity + bloc sources cliquables.

### Feature 3 — Investment Committee Snapshot (priorité P1, 30% du signal)

**Objectif :** une vue qui se lit en 30s et donne le pulse du portefeuille pour un IC reader.

**Livrables :**

- `src/pages/4_📈_IC_Snapshot.py` — one-pager Streamlit :
  - Métriques top : total capacity (MW), nombre de parcs, nombre de pays, % capacité avec delta calculé.
  - Mini-globe coloré par severity (réutilise `Globe.py` config, ajoute la couche couleur).
  - Donut chart capacity by technology (solar / onshore_wind / offshore_wind / battery_storage).
  - Donut chart capacity by country.
  - Table top 5 parcs par capacité avec lien Spotlight.
- Globe principal (`1_🌍_Globe.py`) : ajouter coloration severity à la couche markers existante.

**Critère de succès :** la page rend tous les 5 widgets sans scroll sur viewport 1440x900, et le globe principal montre 4-5 markers colorés (green/yellow/red).

### Foundation — Schema contracts + fixes (priorité P0, prérequis)

**Objectif :** poser des contrats Pydantic sur les outputs JSON et fixer les 2 échecs PVGIS connus.

**Livrables :**

- `src/lib/schemas.py` — Pydantic v2 models pour `PVGISOutput`, `DeltaOutput`, `ParkMetadata`, `ConfidenceInterval`, `PortfolioSweep`.
- Fix `solara-4` coords : passer de [37.95, -8.87] (mer) à coords land-based Sines (research → press release ou OSM).
- Fix `brindisi` capacity_mwp : research dans archives Allianz 2010 ou exclure du sweep si non trouvable.
- Page Methodology (`5_📐_Methodology.py`) : sources, formules PVGIS, biais TMY, hypothèses loss, limites.

**Critère de succès :** `pytest` reste vert (≥ 84 tests = 59 existants + ~25 nouveaux), 0 régression sur les outputs JSON existants.

## 5. Out of scope (explicitement)

- ❌ Sentinel-2 imagery (D1)
- ❌ Live scraping ACP press releases (CLAUDE.md)
- ❌ Refonte UI / nouveau theme
- ❌ Auth / login / multi-user
- ❌ Real-time data refresh (le CI cron lundi suffit)
- ❌ Wind production estimation (PVGIS = solar only ; pour wind, il faudrait `windpowerlib` ou ERA5 — hors scope 7j)
- ❌ NAV / financial valuation modeling (sources publiques insuffisantes)

## 6. Architecture cible

```
src/
├── app.py                              [unchanged]
├── pages/
│   ├── 1_🌍_Globe.py                   [+severity coloration layer]
│   ├── 2_📊_Portfolio_Sweep.py         [NEW — Feature 1]
│   ├── 3_🔬_Ourika_Monograph.py        [NEW — Feature 2]
│   ├── 4_📈_IC_Snapshot.py             [NEW — Feature 3]
│   ├── 5_📐_Methodology.py             [NEW — Foundation]
│   └── existing Spotlight + About      [+ Pydantic-validated read]
├── lib/
│   ├── schemas.py                      [NEW — Pydantic v2 contracts]
│   ├── confidence_interval.py          [NEW — Feature 1]
│   ├── reported_production.py          [NEW — load YAML]
│   ├── parks_loader.py                 [unchanged]
│   ├── pvgis_fetch.py                  [unchanged]
│   ├── compute_delta.py                [+ optional confidence interval param]
│   └── sentinel_fetch.py               [unchanged, dormant]
data/
├── parks_index.yaml                    [+coords solara-4 fix, +capacity brindisi]
├── reported_production.yaml            [NEW — sources publiques par parc]
└── parks/<id>/
    ├── metadata.json                   [unchanged]
    ├── pvgis.json                      [unchanged, validated]
    ├── pvgis_monthly.json              [NEW — Feature 2 monthly breakdown]
    ├── delta.json                      [+ confidence_interval field]
    └── portfolio_sweep.json            [NEW — Feature 1, project root level]
scripts/
└── precompute_all.py                   [+sweep + monthly + sensitivity]
tests/
├── test_schemas.py                     [NEW]
├── test_confidence_interval.py         [NEW]
├── test_reported_production.py         [NEW]
└── existing tests                      [+ refactor for Pydantic schemas]
```

## 7. Critères de succès globaux (definition of done)

- [ ] PRD committé dans `.claude/prds/`
- [ ] 4 epics + ~14 tasks créés dans `.claude/epics/`
- [ ] Repo GitHub `Manceff/allianz-renewables-atlas` créé et push initial
- [ ] Issues GitHub créées (4 epics + ~14 sub-issues)
- [ ] Tasks `parallel: true` lancées en parallèle via worktrees git
- [ ] Tests : `pytest` ≥ 84/84 vert
- [ ] App Streamlit : 6 pages totales, toutes rendent sans exception via `streamlit.testing.v1.AppTest`
- [ ] ≥ 4 parcs solaires avec delta + confidence interval visible sur la page Portfolio Sweep
- [ ] Page Ourika Monograph : chart mensuel + sensitivity + sources
- [ ] Page IC Snapshot : 5 widgets, lecture 30s
- [ ] Page Methodology : sources + formules PVGIS + biais explicites
- [ ] `IMPROVEMENT_REPORT.md` à la racine

## 8. Planning 7 jours (indicatif)

- **J0 (2026-04-29) :** PRD + epics + GitHub + foundation tasks lancées (T-Found-1 fixes + T-Found-2 schemas)
- **J1 :** schemas Pydantic mergés + portfolio sweep lib + reported_production.yaml curated
- **J2 :** confidence interval lib + Ourika monthly fetch
- **J3 :** Page Portfolio Sweep + Page Ourika Monograph
- **J4 :** Page IC Snapshot + Globe severity layer
- **J5 :** Page Methodology + tests integration full-suite
- **J6 :** Polish + Streamlit Cloud redeploy + IMPROVEMENT_REPORT.md
- **J7 (buffer) :** Bugs résiduels, screenshots README

## 9. Risques

| Risque | Impact | Mitigation |
|--------|--------|------------|
| Production publiée non-trouvable pour > 3 parcs | Sweep réduit à 1-2 cas, signal affaibli | Inclure tous les parcs solaires en mode "estimate-only" (sans severity flag) — moins fort mais visible |
| PVGIS API rate-limit ou downtime | Re-run precompute échoue | Cache local des réponses ; retry avec backoff (déjà partiellement géré) |
| Streamlit Cloud deploy fail | Pas d'URL publique | Fallback : screenshots README + lien repo |
| Pydantic strict break les anciens JSON | Régression | Migration script + tests parametrisés sur fixtures existantes |
| GitHub repo creation fails | Pas de sync issues | Documente dans IMPROVEMENT_REPORT, fournit commandes manuelles |
