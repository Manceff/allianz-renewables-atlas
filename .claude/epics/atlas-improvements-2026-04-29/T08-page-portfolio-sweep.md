---
id: T08
epic: E1-portfolio-sweep
parallel: false
blockedBy: [T07]
estimate: 2h
status: pending
---

# T08 — Page Portfolio Sweep

## Context

The hero page for the 70% quantitative signal. Must be readable in 15s by the analyst.

## Acceptance criteria

- [ ] New page `src/pages/2_📊_Portfolio_Sweep.py` (renumber existing Spotlight if needed)
- [ ] Reads `data/portfolio_sweep.json` (validated via T03 schema)
- [ ] Plotly horizontal bar chart:
  - One bar per park
  - Bar = confidence interval range (low → high) in MWh/an
  - Marker = mid (PVGIS 14% loss)
  - Marker = reported production (different shape/color)
  - Color of bar = severity (green / yellow / red)
- [ ] Below chart: table with columns `park | capacity_mwp | reported | estimated_mid | delta_pct | severity | source_url`
- [ ] Click on park name → navigates to Spotlight
- [ ] Renders via `streamlit.testing.v1.AppTest` without exception

## Files

- `src/pages/2_📊_Portfolio_Sweep.py` (NEW)
- `tests/test_pages.py` (extend smoke test)

## Notes

Keep colors consistent with existing severity mapping in `compute_delta.py`. Reuse `TECHNOLOGY_COLORS` constants if relevant.
