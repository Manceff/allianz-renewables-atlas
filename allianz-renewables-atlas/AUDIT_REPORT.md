---
type: audit
status: complete
updated: 2026-04-27
verdict: GO pour `claude -p` après corrections
---

# Audit pré-bootstrap — Allianz Renewables Atlas

> Audit complet du scaffold avant lancement de `claude -p --dangerously-skip-permissions`.
> Objectif : garantir que le contexte chargé par l'agent est cohérent et exempt de pièges qui
> coûteraient des tokens en débuggage.

## Verdict global

**GO** — le scaffold est prêt à être copié vers `~/Code/allianz-renewables-atlas/` et lancé en mode autonome via `claude -p`. Quatre corrections critiques ont été appliquées + cinq additions structurelles.

## Corrections critiques appliquées

| # | Fichier | Bug | Fix |
|---|---|---|---|
| 1 | `src/pages/1_🌍_Globe.py` | `.map(...).fillna([liste])` — pandas refuse les listes en fillna, crash au premier run | Remplacé par `.apply(lambda t: TECHNOLOGY_COLORS.get(t, ...))` |
| 2 | `src/pages/1_🌍_Globe.py` | `_GlobeView` PyDeck non utilisé malgré promesse README → globe Mercator plat | Ajout `views=[pdk.View(type="_GlobeView", controller=True)]`, `map_provider=None`, `pitch=0`, `zoom=1.2` |
| 3 | `README.md` | Section "Prochaine action" listait 5 phases vs bootstrap-prompt 4 phases — ambiguïté pour l'agent | Aligné sur 4 phases : Cartographie / Libs TDD / Precompute / Polish+deploy |
| 4 | `requirements.txt` | Pas de libs scraping pour Phase 1 | Ajouté `beautifulsoup4`, `lxml`, `crawl4ai` (commenté) |

## Additions structurelles

| # | Fichier | Raison |
|---|---|---|
| 1 | `tests/__init__.py` + `tests/test_parks_index.py` | Smoke test YAML ready-to-run pour ancrer le TDD Phase 2 et détecter rapidement une corruption du YAML |
| 2 | `data/parks/.gitkeep` | Dossier pré-créé pour les outputs Phase 3 (évite à l'agent de devoir le créer en cours de run) |
| 3 | `.agent/bootstrap-prompt.md` | Prompt versionné et lisible par l'agent au runtime, pas seulement passé en argument `-p` |
| 4 | `.gitignore` patch | Ignore les logs runtime de l'agent (`.agent/run-*.log`) |
| 5 | `AUDIT_REPORT.md` (ce fichier) | Traçabilité pour le post-mortem |

## Inventaire final du scaffold

```
allianz-renewables-atlas/
├── README.md                       ← vision (aligné 4 phases)
├── CLAUDE.md                       ← briefing agent
├── AUDIT_REPORT.md                 ← ce rapport
├── requirements.txt                ← + bs4 + lxml + crawl4ai commenté
├── .env.example                    ← Copernicus + USER_AGENT
├── .gitignore                      ← + .agent/run-*.log
├── .streamlit/config.toml          ← thème Allianz
├── .agent/
│   └── bootstrap-prompt.md         ← prompt versionné pour claude -p
├── data/
│   ├── parks_index.yaml            ← 10 parcs initiaux, 13 à ajouter en Phase 1
│   └── parks/.gitkeep              ← rempli en Phase 3
├── src/
│   ├── app.py                      ← entry point Streamlit
│   ├── pages/
│   │   ├── 1_🌍_Globe.py           ← FIX bugs #1 + #2 appliqués
│   │   ├── 2_📍_Spotlight.py       ← OK
│   │   └── 3_ℹ️_About.py            ← OK
│   └── lib/
│       └── __init__.py             ← libs implémentées en Phase 2
├── scripts/
│   └── precompute_all.py           ← TODOs dépendent de Phase 2
└── tests/
    ├── __init__.py
    └── test_parks_index.py         ← smoke test YAML ready-to-run
```

## Points d'attention non bloquants pour l'agent

1. **Coordonnées approximatives** dans `parks_index.yaml` — Phase 1 doit les raffiner via OSM Nominatim ou The Wind Power database.

2. **PyDeck `_GlobeView` est expérimental** — l'underscore préfixe signale une API instable. Si elle casse en prod Streamlit Cloud, fallback sur `MapView` standard (perte du globe 3D, gain de stabilité).

3. **Click handler PyDeck → Streamlit page navigation n'existe pas nativement.** Le scaffold contourne via selectbox dans la sidebar de Spotlight. Le README promet "click sur marker" — diff résiduel à assumer ou à régler en v2 avec `streamlit-pydeck-events`.

4. **Pas d'authentification Copernicus testée** — Phase 2 va devoir créer un compte sur dataspace.copernicus.eu. L'agent doit flagger dans `BLOCKERS.md` si OAuth fail.

5. **PVGIS PVcalc params exacts non figés** — l'endpoint v5.2 demande `lat`, `lon`, `peakpower` (kWp pas MWp), `loss` (default 14), `tilt`, `azimuth`. L'agent doit lire la doc JRC en démarrant Phase 2b.

## Doctrine vault — application

| Règle | Statut |
|---|---|
| R1 frontmatter YAML | Ce fichier OK. README OK. CLAUDE.md = briefing technique, pas de frontmatter requis. |
| R2 vault avant web | L'agent a accès au vault via `~/Documents/SecondBrain` mais le projet est dans `~/Code/` — pour Phase 1, l'agent va surtout web-search. OK. |
| R4 citations | YAML cite `press_release_url` pour chaque parc. OK. |
| R6 pas d'écrasement | Bootstrap-prompt impose commits à chaque étape. OK. |
| R7 filing back | `RUN_REPORT.md` final + idéalement filer dans `wiki/synthesis/` après le run. À faire post-bootstrap. |
| R8 log.md vault | À update après le run, dans le vault `~/Documents/SecondBrain/log.md`. |
| R10 doute affiché | `BLOCKERS.md` + `UNCERTAIN.md` prévus dans le bootstrap-prompt. OK. |

## Commande de lancement validée

```bash
cd ~/Code
cp -r ~/Documents/SecondBrain/projects/alternance/allianz-renewables-atlas .
cd allianz-renewables-atlas
git init && git add -A && git commit -m "Initial scaffold (audited 2026-04-27)"

# Sanity check : tests passent sur le YAML initial
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest tests/ -v   # devrait passer sur les 6 tests, validant la structure du YAML 10 parcs

# Sanity check : streamlit tourne sur le scaffold
streamlit run src/app.py
# (Ctrl-C après vérification visuelle des 3 pages)

# Lancement Phase 1 only en autonome
claude -p "$(cat .agent/bootstrap-prompt.md)\n\nMAIS exécute UNIQUEMENT Phase 1. Stoppe après le commit final de Phase 1." \
  --dangerously-skip-permissions \
  --max-turns 80 \
  2>&1 | tee .agent/phase1-$(date +%Y%m%d-%H%M%S).log
```

## Critères de succès Phase 1

- [ ] `data/parks_index.yaml` contient ≥ 23 parcs avec tous les champs obligatoires
- [ ] `pytest tests/test_parks_index.py` passe en vert
- [ ] `data/UNCERTAIN.md` créé (peut être vide)
- [ ] Au moins 1 commit de feat(phase1) dans git log
- [ ] `agent-log.md` contient une entrée Phase 1 avec timestamp + résumé
