---
id: T03
epic: E0-foundation
parallel: false
blockedBy: []
blocks: [T05, T09]
estimate: 2h
status: pending
---

# T03 — Pydantic v2 schemas for JSON outputs

## Context

GitNexus impact analysis flagged that the real coupling between libs and pages passes through `data/parks/<id>/*.json` — invisible to call graphs. Schemas formalize this contract.

## Acceptance criteria

- [ ] New file `src/lib/schemas.py` with Pydantic v2 models:
  - `PVGISOutput` — fields matching current `pvgis.json` shape (annual_kwh, monthly_kwh[12], inputs)
  - `DeltaOutput` — fields matching `delta.json` (estimated_mwh, reported_mwh, delta_pct, severity)
  - `ParkMetadata` — fields matching `metadata.json`
  - `ConfidenceInterval` — `{low_mwh, mid_mwh, high_mwh, scenarios: [{loss_pct, kwh}]}`
  - `PortfolioSweep` — list of per-park entries with delta + interval
- [ ] All 23 existing JSON outputs in `data/parks/*/` validate against the schemas (no break)
- [ ] New tests in `tests/test_schemas.py` parametrized on existing fixtures
- [ ] `pytest` passes (≥ 64 tests)

## Files

- `src/lib/schemas.py` (NEW)
- `tests/test_schemas.py` (NEW)
- `tests/conftest.py` (extend if needed)

## TDD checklist

1. Write tests first, parametrized on existing JSON files in `data/parks/`
2. Implement schemas to make them pass
3. No backwards-compat hack — if a field is optional in current data, mark `Optional` cleanly

## Notes

Use `model_validate` for validation. Use `Field(..., description=...)` for self-documenting models. Export via `__all__` for clean imports.
