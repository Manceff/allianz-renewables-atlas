---
id: T04
epic: E0-foundation
parallel: true
blockedBy: []
estimate: 1h
status: pending
---

# T04 — Page Methodology

## Context

The "rigueur quantitative" signal (70% of the PRD goal) requires explicit, sourced methodology visible from the app — not buried in code or README.

## Acceptance criteria

- [ ] New page `src/pages/5_📐_Methodology.py`
- [ ] Sections:
  - **Sources** : PVGIS v5.2 (JRC), parks_index.yaml hand-curated from press releases, reported_production.yaml hand-curated
  - **Formula PVGIS** : explain `peakpower × specific_yield × (1 - loss)` semantics
  - **Hypothèses** : default loss 14% (PVGIS default), TMY 2005-2020, fixed mounting, no shading model, no soiling, no degradation
  - **Sensitivity (loss)** : table 10/14/18% with explanation of why these bounds
  - **Limites** : no monthly reported production for most parks, geocoding precision, estimate inherently TMY-based (no weather realtime)
  - **Severity thresholds** : explain green/yellow/red logic (cite `compute_delta.py`)
- [ ] Page renders without exception via `streamlit.testing.v1.AppTest`
- [ ] All claims have a source URL or a code reference

## Files

- `src/pages/5_📐_Methodology.py` (NEW)
- `tests/test_pages.py` (extend with smoke test for this page)

## Notes

This page is read by the analyst. Tone : factual, sourced, no marketing. French OK.
