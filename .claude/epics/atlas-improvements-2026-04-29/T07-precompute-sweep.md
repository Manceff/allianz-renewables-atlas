---
id: T07
epic: E1-portfolio-sweep
parallel: false
blockedBy: [T05, T06]
estimate: 1h
status: pending
---

# T07 — Extend precompute_all to generate portfolio_sweep.json

## Context

Need a single artifact aggregating per-park delta + confidence interval, consumable by the Portfolio Sweep page.

## Acceptance criteria

- [ ] `scripts/precompute_all.py` extended to:
  - For each solar park with `has_pvgis_estimate: true` AND a `reported_production.yaml` entry:
    - Compute `ConfidenceInterval` via T05 lib
    - Load reported production via T06 lib
    - Compute delta with severity
  - Write `data/portfolio_sweep.json` validated against `PortfolioSweep` schema (T03)
- [ ] Re-run on local: produces a JSON with ≥ 4 entries
- [ ] `pytest` still passes

## Files

- `scripts/precompute_all.py` (edit)
- `data/portfolio_sweep.json` (generated artifact, committed)

## Notes

Don't break existing per-park `delta.json` writes — keep them. The sweep is additive.
