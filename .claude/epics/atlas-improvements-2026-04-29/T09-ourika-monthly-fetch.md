---
id: T09
epic: E2-ourika-monograph
parallel: true
blockedBy: [T03]
estimate: 1h
status: pending
---

# T09 — Ourika monthly PVGIS fetch + persist

## Context

PVGIS PVcalc response contains `outputs.monthly` with 12 monthly values. Currently dropped — only annual is persisted. Recover for the monograph chart.

## Acceptance criteria

- [ ] Extend `fetch_pvgis_pvcalc` (or add a sibling function) to also return monthly breakdown
- [ ] Persist `data/parks/ourika/pvgis_monthly.json` validated against extended `PVGISOutput` schema (T03)
- [ ] Re-run `precompute_all.py` for Ourika regenerates the file
- [ ] Tests verify monthly array length = 12 and values are floats

## Files

- `src/lib/pvgis_fetch.py` (edit, additive)
- `scripts/precompute_all.py` (edit to write monthly)
- `data/parks/ourika/pvgis_monthly.json` (generated)
- `tests/test_pvgis_fetch.py` (extend)

## Notes

PVGIS already returns monthly. Don't make a second API call. Just don't drop the data.
