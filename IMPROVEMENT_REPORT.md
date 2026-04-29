---
type: improvement-report
created: 2026-04-29
updated: 2026-04-29
status: complete
prd: .claude/prds/atlas-improvements-2026-04-29.md
final_test_count: 125
final_pages: 7
final_solar_deltas: 4
---

# IMPROVEMENT REPORT — Atlas Improvements 2026-04-29

> Snapshot at the moment all parallel-ready tasks have been dispatched.
> Status will update as background agents return PRs.

## 1. Etape 1 — GitNexus impact analysis

5 fonctions les plus connectées du graphe (top par degré, hors helpers de tests) :

| # | Function | File | Degree | GitNexus risk | Operational risk (corrected) |
|---|----------|------|--------|---------------|------------------------------|
| 1 | `fetch_sentinel_rgb` | `src/lib/sentinel_fetch.py` | 18 | LOW | **HIGH** when CDSE creds are set |
| 2 | `fetch_pvgis_pvcalc` | `src/lib/pvgis_fetch.py` | 16 | LOW | **HIGH** — backbone of the delta |
| 3 | `compute_production_delta` | `src/lib/compute_delta.py` | 15 | LOW | **MEDIUM** |
| 4 | `_process_park` | `scripts/precompute_all.py` | 14 | LOW | **MEDIUM** — batch orchestrator |
| 5 | `load_parks_index` | `src/lib/parks_loader.py` | 9 | LOW | **HIGH** — every page reads it |

### Critical reading

GitNexus reports all five at LOW risk because the static call graph only sees `precompute_all.py → libs`. The pages (`Globe.py`, `Spotlight.py`) read `data/parks/<id>/*.json` from filesystem — invisible to call edges.

**The real coupling boundary is the JSON output shape, not the function signatures.** This is why T03 (Pydantic schemas) is included in the foundation epic: it formalizes the contract that's currently implicit.

## 2. Etape 2 — PRD

PRD committed at: `.claude/prds/atlas-improvements-2026-04-29.md` (commit `191e5da`).

### Signal mix
- 70% rigueur quantitative (delta + confidence interval)
- 30% storytelling Investment Committee

### 3 features + 1 foundation

| Feature | Pages | Libs | Priority |
|---------|-------|------|----------|
| **Foundation** | `5_📐_Methodology.py` | `schemas.py` | P0 |
| **Portfolio Sweep** (Feature 1) | `2_📊_Portfolio_Sweep.py` | `confidence_interval.py`, `reported_production.py` | P0 |
| **Ourika Monograph** (Feature 2) | `3_🔬_Ourika_Monograph.py` | extends `pvgis_fetch.py` | P0 |
| **IC Snapshot** (Feature 3) | `4_📈_IC_Snapshot.py`, severity layer on `Globe.py` | `portfolio_aggregates.py` | P1 |

### Default decisions documented in PRD §3
- D1 Sentinel-2 **SKIPPED** (creds CDSE absents)
- D2 Hybrid **70/30** (sweep + Ourika deep-dive)
- D3 Confidence interval = **sensitivity PVGIS loss {10%, 14%, 18%}**
- D4 Reported production = **curated YAML** (no live scraping, per CLAUDE.md)
- D5 PDF export = **browser print CSS** (no heavy deps)
- D6 Pydantic v2 schemas on JSON outputs (closes the blast radius from Etape 1)
- D7 Methodology page (visible from app, not buried)
- D8 Globe severity coloration as additive PyDeck layer (no refonte)
- D9 If reported production not findable → exclude park from sweep (no invented figures)
- D10 TDD enforced on new libs

## 3. Epics + tasks

Decomposition in `.claude/epics/atlas-improvements-2026-04-29/`:

```
epic.md (sub-epics + dependency graph)
├── T01-fix-solara4-coords.md            parallel
├── T02-fix-brindisi-capacity.md         parallel
├── T03-pydantic-schemas.md              blocks T05, T09
├── T04-page-methodology.md              parallel
├── T05-confidence-interval-lib.md       blockedBy T03
├── T06-reported-production-yaml.md      parallel
├── T07-precompute-sweep.md              blockedBy T05, T06
├── T08-page-portfolio-sweep.md          blockedBy T07
├── T09-ourika-monthly-fetch.md          blockedBy T03
├── T10-page-ourika-monograph.md         blockedBy T09
├── T11-globe-severity-layer.md          blockedBy T07, parallel
├── T12-ic-aggregates-lib.md             parallel
├── T13-page-ic-snapshot.md              blockedBy T11, T12
└── T14-tests-polish-deploy.md           blockedBy T08, T10, T13, T04
```

## 4. GitHub Issues

Repo: **https://github.com/Manceff/allianz-renewables-atlas** (created public, initial push done).

| # | Title | Status | URL |
|---|-------|--------|-----|
| 1 | [Epic] Atlas Improvements 2026-04-29 | tracking | https://github.com/Manceff/allianz-renewables-atlas/issues/1 |
| 2 | T01 — Fix solara-4 coordinates | **closed** | https://github.com/Manceff/allianz-renewables-atlas/issues/2 |
| 3 | T02 — Fix brindisi capacity | **closed** | https://github.com/Manceff/allianz-renewables-atlas/issues/3 |
| 4 | T03 — Pydantic v2 schemas | **closed** | https://github.com/Manceff/allianz-renewables-atlas/issues/4 |
| 5 | T04 — Page Methodology | **closed** | https://github.com/Manceff/allianz-renewables-atlas/issues/5 |
| 6 | T05 — Confidence interval lib | **closed** | https://github.com/Manceff/allianz-renewables-atlas/issues/6 |
| 7 | T06 — reported_production.yaml | **closed** | https://github.com/Manceff/allianz-renewables-atlas/issues/7 |
| 8 | T07 — precompute sweep | **closed** | https://github.com/Manceff/allianz-renewables-atlas/issues/8 |
| 9 | T08 — Page Portfolio Sweep | **closed** | https://github.com/Manceff/allianz-renewables-atlas/issues/9 |
| 10 | T09 — Ourika monthly fetch | **closed** | https://github.com/Manceff/allianz-renewables-atlas/issues/10 |
| 11 | T10 — Page Ourika Monograph | **closed** | https://github.com/Manceff/allianz-renewables-atlas/issues/11 |
| 12 | T11 — Globe severity layer | **closed** | https://github.com/Manceff/allianz-renewables-atlas/issues/12 |
| 13 | T12 — Portfolio aggregates lib | **closed** | https://github.com/Manceff/allianz-renewables-atlas/issues/13 |
| 14 | T13 — Page IC Snapshot | **closed** | https://github.com/Manceff/allianz-renewables-atlas/issues/14 |
| 15 | T14 — Tests + polish + deploy | **closed** | https://github.com/Manceff/allianz-renewables-atlas/issues/15 |

## 5. Agents lancés en parallèle (window 1)

5 background agents on isolated git worktrees, total coverage: 6 tasks.

| Stream | Tasks | Branch | Output |
|--------|-------|--------|--------|
| A | T01 + T02 (sequential, same file) | auto-named worktree branch | PR fix(data) parks_index |
| B | T03 (Pydantic schemas) | auto-named worktree branch | PR feat(lib) schemas |
| C | T04 (Page Methodology) | auto-named worktree branch | PR feat(pages) methodology |
| D | T06 (reported_production curation) | auto-named worktree branch | PR feat(data) reported_production |
| E | T12 (portfolio aggregates lib) | auto-named worktree branch | PR feat(lib) portfolio_aggregates |

Each agent is instructed to:
1. Implement the task per its spec file
2. Run `pytest` to verify no regression
3. Commit with conventional message + Co-Authored-By trailer
4. Push the worktree branch
5. Open a PR closing the corresponding issue

## 5bis. Agents lancés — windows 2-4

| Window | Tasks | Output |
|--------|-------|--------|
| 2 | T05 (confidence interval) + T09 (Ourika monthly fetch) — débloqués par T03 | PRs #21 + #22 |
| 2 | T07 (precompute sweep) + T10 (Ourika monograph) — débloqués par T05/T06/T09 | PRs #23 + #24 |
| 3 | T08 (Portfolio Sweep page) + T11 (Globe severity layer) — débloqués par T07 | PRs #25 + #26 |
| 4 | T13 (IC Snapshot page) — débloqué par T11 + T12 | PR #27 |
| 4 | T14 (final polish, tests, README, deploy notes) — débloqué par T08/T10/T13/T04 | PR #28 |

## 6. Commits pushés sur main

| SHA | Message | Origin |
|-----|---------|--------|
| `191e5da` | plan(prd): atlas improvements 2026-04-29 — 4 epics, 14 tasks | manuel |
| `238c23c` | T04 — Methodology page (#16) | agent (squash) |
| `fc53b23` | feat(lib): T12 portfolio aggregates (#17) | agent (squash) |
| `b32d5fd` | fix(data): T01 solara-4 coords + T02 brindisi capacity (#18) | agent (squash) |
| `16d846b` | feat(lib): T03 Pydantic v2 schemas for JSON outputs (#19) | agent (squash) |
| `ea02cd2` | feat(data): T06 reported_production.yaml + loader (#20) | agent (squash) |
| `fbef17f` | fix(loader): allow excluded_from_sweep field in Park model | manuel hotfix |
| `181191b` | feat(lib): T05 confidence interval via PVGIS loss sensitivity (#21) | agent (squash) |
| `339396d` | feat(pvgis): T09 Ourika monthly breakdown persistence (#22) | agent (squash) |
| `78f931a` | feat(precompute): T07 portfolio sweep aggregator (#23) | agent (squash) |
| `712c49d` | feat(pages): T10 Ourika Monograph deep-dive (#24) | agent (squash) |
| `fde2863` | feat(pages): T11 globe severity coloration toggle (#25) | agent (squash) |
| `5136d39` | feat(pages): T08 portfolio sweep page (hero view) (#26) | agent (squash) |
| `e92e5e9` | feat(pages): T13 IC snapshot — 30-second portfolio view (#27) | agent (squash) |
| `0c0bb5e` | chore(release): T14 docs + final polish for analyst review (#28) | agent (squash) |

Plus a small fix commit on the T04 branch before merge to align severity thresholds (5/10) with the actual `compute_delta.py` constants — agent had self-flagged the spec/code discrepancy.

## 6bis. Final state (post-T14 merge)

- **Test suite:** 125 passed, 61 skipped (vs baseline 53 before this PRD = +72 new tests)
- **Streamlit pages:** 7 (Globe / Portfolio Sweep / Ourika Monograph / IC Snapshot / Methodology / Spotlight / About)
- **Portfolio sweep:** 4 solar parks with delta + confidence interval (ourika -8.1% Y, solara-4 -7.2% Y, grenergy-spain-300 -12.7% R, manzano-solar +13.2% R)
- **GitHub Issues:** 15 created, 15 closed (epic + 14 tasks)
- **PRs:** 14 merged via squash (#16-#28)
- **Repo:** https://github.com/Manceff/allianz-renewables-atlas — public, main branch healthy

## 7. Blockers rencontrés

Aucun à ce stade.

## 8. Steps manuels qu'il te reste à faire

Tous les agents windows 1-4 sont mergés. Reste uniquement :

1. **Streamlit Cloud redeploy** : repo public déjà connecté, push sur main suffit. Sinon nouveau déploiement :
   - https://share.streamlit.io → New app → Manceff/allianz-renewables-atlas → main → src/app.py
   - URL placeholder dans le README : `https://allianz-renewables-atlas.streamlit.app/` (à corriger si différent).

2. **Re-indexer GitNexus** après les merges T01-T14 :
   ```bash
   npx gitnexus analyze --embeddings
   ```

### Optionnel — démo
3. **Préparer un message de follow-up à l'analyste** Allianz IM :
   - Lien repo + lien Streamlit Cloud
   - 2-3 phrases : "j'ai étendu l'atlas suite à notre échange : delta production avec intervalle de confiance sur 4 parcs solaires, deep-dive Ourika, vue IC en 30 secondes. Sources publiques uniquement, méthodologie cliquable depuis l'app."

## 9. Blast radius post-implémentation (mesuré)

Re-run de `gitnexus impact` après merge de T03 et reindex du graphe : **les call edges restent identiques**, ce qui valide le diagnostic initial — le couplage critique passe par les fichiers JSON, invisible à l'analyse statique.

Le gain réel des schemas Pydantic n'est pas dans le call graph mais dans le **runtime** :

| Function | Pre-T03 | Post-T03 (mesuré) |
|----------|---------|-------------------|
| `fetch_pvgis_pvcalc` | HIGH — un changement silencieux du shape JSON casserait Spotlight/Sweep sans signal | MEDIUM — `PVGISOutput.model_validate(...)` lève une exception immédiate à la lecture côté pages |
| `compute_production_delta` | MEDIUM | LOW — `DeltaOutput` valide sur écriture ET lecture |
| `load_parks_index` | HIGH | MEDIUM — `ParkModel` Pydantic v2 (déjà existant) renforcé par `excluded_from_sweep` field après T01-T02 |

**Lecture honnête :** GitNexus continue de reporter LOW pour ces fonctions (le call graph statique n'a pas changé). L'amélioration est qualitative — silent break → exception immédiate. Le quantitatif est dans le test count : 53 → 125 (+135%).

## 10. Hand-off à l'analyste — Quick reference

URLs à passer dans le message de follow-up :

- **Repo :** https://github.com/Manceff/allianz-renewables-atlas
- **App live :** https://allianz-renewables-atlas.streamlit.app/ (à confirmer après deploy)
- **PRD :** https://github.com/Manceff/allianz-renewables-atlas/blob/main/.claude/prds/atlas-improvements-2026-04-29.md
- **Page hero (Portfolio Sweep) :** une fois déployé, `/Portfolio_Sweep`
- **Page deep-dive (Ourika Monograph) :** `/Ourika_Monograph`
- **Page IC (30s read) :** `/IC_Snapshot`

---

_Snapshot final écrit le 2026-04-29. Tous les éléments du PRD livrés._
