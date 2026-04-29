---
id: T10
epic: E2-ourika-monograph
parallel: false
blockedBy: [T09]
estimate: 2h
status: pending
---

# T10 — Page Ourika Monograph

## Context

Deep-dive page for the rigueur quanti signal. Demonstrates depth of analysis on a single case study.

## Acceptance criteria

- [ ] New page `src/pages/3_🔬_Ourika_Monograph.py`
- [ ] Header: park name, capacity, country, commissioning year, operator, press release link
- [ ] Plotly chart: 12 bars (monthly estimated kWh) + horizontal line (1/12 of reported annual if available, with note)
- [ ] Sensitivity table: 3 rows (loss 10/14/18%), columns annual_mwh + delta_pct vs reported
- [ ] Methodology box (collapsible): formulas, assumptions, biases (cross-link page Methodology)
- [ ] Sources section: bullet list with URLs (PVGIS doc, ACP press release, parks_index entry)
- [ ] Renders via `streamlit.testing.v1.AppTest`

## Files

- `src/pages/3_🔬_Ourika_Monograph.py` (NEW)
- `tests/test_pages.py` (extend)

## Notes

This page is the most carefully read by the analyst. Polish typography, alignment, no Lorem Ipsum, no TODO.
