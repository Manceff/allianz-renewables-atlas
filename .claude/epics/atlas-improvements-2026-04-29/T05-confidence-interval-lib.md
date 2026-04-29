---
id: T05
epic: E1-portfolio-sweep
parallel: true
blockedBy: [T03]
estimate: 1h30
status: pending
---

# T05 — Confidence interval lib (sensitivity on PVGIS loss)

## Context

The differentiator vs a naive estimate: an explicit confidence range. PVGIS `loss` is the most opaque parameter — sensitivity over [10%, 14%, 18%] gives a defensible band.

## Acceptance criteria

- [ ] New file `src/lib/confidence_interval.py` with function:
  ```python
  def compute_pvgis_range(
      lat: float, lon: float, peakpower_kwp: float,
      loss_scenarios: tuple[float, ...] = (10.0, 14.0, 18.0),
  ) -> ConfidenceInterval
  ```
  Returns Pydantic `ConfidenceInterval` (from T03).
- [ ] Calls `fetch_pvgis_pvcalc` 3 times (one per scenario), caches results
- [ ] `low` = highest-loss scenario (most conservative), `high` = lowest-loss, `mid` = 14%
- [ ] Tests in `tests/test_confidence_interval.py` mocking PVGIS responses
- [ ] `pytest` passes

## Files

- `src/lib/confidence_interval.py` (NEW)
- `tests/test_confidence_interval.py` (NEW)

## Notes

Use existing `fetch_pvgis_pvcalc(loss=X)` signature. Don't re-implement PVGIS HTTP. If `fetch_pvgis_pvcalc` doesn't accept `loss` as kwarg yet, extend it with default 14.0 (backwards-compatible).
