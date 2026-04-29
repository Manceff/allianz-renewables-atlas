---
id: T13
epic: E3-ic-snapshot
parallel: false
blockedBy: [T11, T12]
estimate: 2h
status: pending
---

# T13 — Page IC Snapshot

## Context

The 30s read for the IC reader. Must fit on viewport 1440x900 without scroll.

## Acceptance criteria

- [ ] New page `src/pages/4_📈_IC_Snapshot.py`
- [ ] Layout:
  - Top row: 4 metric cards (total MW, parks count, countries, % covered by delta)
  - Middle row: mini-globe (severity colored, smaller than main Globe page) + donut chart "capacity by technology"
  - Bottom row: donut chart "capacity by country" + table top 5 by capacity
- [ ] All widgets read pre-computed data — no API call on render
- [ ] Renders via `streamlit.testing.v1.AppTest`
- [ ] Print-friendly CSS (D5: bouton "Imprimer" → window.print() via st.markdown HTML)

## Files

- `src/pages/4_📈_IC_Snapshot.py` (NEW)
- `tests/test_pages.py` (extend)

## Notes

Reuse `compute_aggregates` from T12. Reuse globe config from `Globe.py`. Donut charts via Plotly.
