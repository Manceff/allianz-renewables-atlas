---
id: T01
epic: E0-foundation
parallel: true
blockedBy: []
estimate: 30min
status: pending
---

# T01 — Fix solara-4 coordinates (sea → land)

## Context

`data/parks_index.yaml` lists `solara-4` at `[37.95, -8.87]` which falls in the Atlantic Ocean. PVGIS returns HTTP 400 on this point. Need land-based coordinates near Sines, Portugal.

## Acceptance criteria

- [ ] Coordinates updated in `data/parks_index.yaml` to a verifiable land location near the actual Solara 4 plant in Sines region
- [ ] Source URL added in a comment next to the coords (press release or operator site)
- [ ] `pytest tests/test_parks_index.py` still passes
- [ ] PVGIS PVcalc returns HTTP 200 on the new coords (manual sanity-check)

## Files

- `data/parks_index.yaml` (edit)

## Notes

WElink + China Triumph International Engineering operate this plant. Search for press release naming the municipality or commune. Plausible candidates: Ourique, Castro Verde, Beja district. Avoid generic Portugal centroid.
