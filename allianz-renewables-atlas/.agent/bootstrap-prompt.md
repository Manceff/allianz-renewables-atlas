# Bootstrap prompt — Allianz Renewables Atlas

Tu es l'orchestrator autonome du projet allianz-renewables-atlas. Tu vas exécuter les 4 phases jusqu'au bout sans confirmation humaine. Tu commits à chaque étape significative pour permettre rollback.

## Contexte — lis ces fichiers en premier

1. `README.md` — vision produit
2. `CLAUDE.md` — conventions et stack imposée
3. `data/parks_index.yaml` — 10 parcs initiaux à enrichir
4. `tests/test_parks_index.py` — smoke test à faire passer après Phase 1
5. `scripts/precompute_all.py` — TODOs Phase 3
6. `src/app.py`, `src/pages/*.py` — UI déjà scaffoldée
7. `src/lib/__init__.py` — libs à implémenter en Phase 2
8. `.claude/skills/` — liste tous les `SKILL.md` disponibles

## Skills à invoquer

- **prompt-engineering** : structurer ta réflexion sur chaque phase
- **subagent-driven-development** : fan-out parallèle quand pertinent
- **using-git-worktrees** : pour les fan-outs longs en Phase 1 et Phase 2
- **test-driven-development** : Phase 2 (libs) — tests d'abord
- **skill-creator** : si tu identifies un pattern réutilisable à extraire

## Workflow — 4 phases

### Phase 1 — Cartographie ACP
Spawn 3 subagents en parallèle via git worktrees, chacun scrape une période des press releases sur `allianz-capital-partners.com/news` :
- Période A : 2010-2017
- Période B : 2018-2022
- Période C : 2023-2026

Chaque subagent enrichit `data/parks_index.yaml` dans son worktree avec : `lat`/`lon` raffinées, `capacity_mwp`, `commissioning_year`, `operator`, `allianz_stake_pct`, `acquisition_year`, `press_release_url` canonique. Cible : **passer de 10 à 23 parcs validés** par `tests/test_parks_index.py`. Si un parc est ambigu (lat manquante, capacité unclear), l'ajouter à `data/UNCERTAIN.md` et continuer.

À la fin : merge les worktrees, dédup par `id`, mets à jour le bloc `metadata` du YAML, fait passer `pytest tests/test_parks_index.py`. Commit final : `feat(phase1): cartographie 23 parcs ACP`.

### Phase 2 — Libs internes en TDD
Implémente dans cet ordre, **tests d'abord** :

a) `src/lib/parks_loader.py` — YAML → Pydantic v2 `ParkModel`, `lru_cache`. Tests : champs obligatoires, types, enum technology.

b) `src/lib/pvgis_fetch.py` — HTTP GET sur `https://re.jrc.ec.europa.eu/api/v5_2/PVcalc` (no auth). Inputs : lat, lon, peakpower_mw, tilt (default lat-10°), azimuth (0). Output : dict avec `monthly_production_estimated` (12 mois × N années) + `annual_total_mwh`. Tests : mock requests, vérifier parsing.

c) `src/lib/sentinel_fetch.py` — OAuth2 Copernicus Data Space Ecosystem (`COPERNICUS_USERNAME`/`PASSWORD` dans `.env`) + Process API pour fetch RGB Sentinel-2 (cloud cover < 20%, plus récent). Output : PNG dans `data/parks/<id>/sentinel.png`. Tests : mock auth, vérifier write.

d) `src/lib/compute_delta.py` — calcule (estimée − reportée) / reportée pour les solaires avec `has_reported_production: true`. Severity green <5%, yellow 5-10%, red >10%. Output : dict serialisable JSON.

Chaque lib : tests pytest qui passent avant de bouger à la suivante. Commit après chaque lib : `feat(phase2): <lib_name>`.

### Phase 3 — Precompute exhaustif
Termine `scripts/precompute_all.py` (les TODOs deviennent des appels aux libs Phase 2). Exécute sur les 23 parcs. Génère `data/parks/<id>/{metadata.json, sentinel.png, production_estimated.json, delta.json (si applicable)}`. Si un parc échoue (Sentinel down, PVGIS bad params, coords invalides), log dans `data/PRECOMPUTE_FAILURES.md` et continue.

Commit final Phase 3 : `feat(phase3): precompute 23 parcs`.

### Phase 4 — Polish UI + deploy
Le scaffold UI fonctionne déjà avec les stubs. À cette étape :
- Vérifie que `streamlit run src/app.py` tourne sans erreur sur les 3 pages.
- Le globe (Page 1) doit afficher les 23 parcs avec `_GlobeView` 3D.
- Spotlight (Page 2) doit afficher l'image satellite + les charts pour les solaires.
- Crée `.github/workflows/refresh-data.yml` (cron lundi 6h UTC) qui re-run `scripts/precompute_all.py`.
- **Ne deploy pas Streamlit Cloud** (besoin auth navigateur — laisse une note dans `DEPLOY.md` avec les étapes manuelles).

Commit final Phase 4 : `feat(phase4): ui polish + ci cron`.

## Règles d'exécution

- Tu **ne demandes JAMAIS** confirmation. Tu décides et tu commits.
- Si bloqué techniquement, tu documentes dans `BLOCKERS.md` et tu passes à la suite.
- Tu cites tes sources (doctrine R4) dans les `notes` YAML / commentaires JSON.
- Stack imposée respectée — pas de PVLIB ModelChain, pas de framework hors `requirements.txt` sans validation.
- Tu logues chaque phase dans `agent-log.md` à la racine : timestamp + phase + résumé + parcs traités.
- À chaque commit significatif, vérifie que `pytest tests/` passe encore.

## Output final

Un fichier `RUN_REPORT.md` à la racine résumant :
- Parcs cartographiés (23 cible vs réel)
- Libs implémentées + couverture tests
- Parcs précomputés / échoués
- Blockers rencontrés
- Commits clés (hashes courts)
- Étapes manuelles restantes pour Mancef (deploy, secrets Copernicus, mail analyste)

## Démarre maintenant

Commence par lire les fichiers du contexte ci-dessus, puis attaque Phase 1.
