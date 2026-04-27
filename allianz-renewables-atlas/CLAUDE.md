# Allianz Renewables Atlas — briefing Claude Code

> Briefing pour les agents Claude Code qui vont implémenter le projet.
> Lis ce fichier en premier avant toute action.

## Vision en 3 phrases

Atlas interactif Streamlit avec globe terrestre 3D rotatif (PyDeck) montrant les ~23 parcs Renewables d'Allianz Capital Partners publiquement identifiables. Chaque parc cliquable ouvre une page Spotlight avec image satellite Sentinel-2 + (pour les solaires) production estimée PVGIS comparée à la production publiée. Outil construit comme follow-up post-entretien d'alternance pour signal candidat technique sur sources publiques uniquement.

## Conventions de code

- **Python 3.11+**
- **Pas de classes complexes** sauf si nécessaire — fonctions pures privilégiées
- **Pydantic v2** pour validation schémas
- **Type hints partout**
- **Docstrings courtes** en français
- **Logs structurés** via `logging` standard (pas de print)

## Sources de vérité

- `README.md` : vision produit complète
- `data/parks_index.yaml` : liste master des parcs (à compléter en Phase 1)
- `data/parks/<id>/metadata.json` : metadata par parc (généré en Phase 1-2)

## Ne PAS faire

- Pas de PVLIB ModelChain (PVGIS PVcalc fait tout en un appel HTTP)
- Pas de scraping live des press releases ACP en runtime (cartographie one-shot dans Phase 1)
- Pas de Daily Brief, pas de Fund Memo Analyzer, pas de RSS — ce projet est focused Renewables Atlas uniquement
- Pas de claim "150+ parcs cartographiés" — toujours 23 / 150+ (transparence)

## Stack imposée

- **Streamlit** pour le frontend (multi-page natif)
- **PyDeck** pour le globe 3D (`_GlobeView`)
- **Folium** pour les cartes zoom local en Spotlight
- **Plotly** pour les charts (production mensuelle, etc.)
- **requests** pour les APIs Sentinel + PVGIS
- **PIL/Pillow** pour manipulation images satellites
- **PyYAML** pour `parks_index.yaml`

Pas d'autres frameworks sans validation explicite.

## Phases d'exécution recommandées

Voir README.md section "Prochaine action" pour les 5 phases.

Chaque phase doit être committée séparément avec un message clair.

## Tests minimum

- Vérifier que `precompute_all.py` tourne sur 1 parc (Ourika) avant de boucler sur les 23
- Vérifier que le globe affiche au moins 5 markers visibles avant d'ajouter les filtres
- Vérifier que la Spotlight ouvre correctement pour 1 parc solaire ET 1 parc wind avant polish
