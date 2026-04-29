---
id: T11
epic: E3-ic-snapshot
parallel: true
blockedBy: [T07]
estimate: 1h
status: pending
---

# T11 — Globe severity coloration layer

## Context

Currently markers on the globe are colored by technology. For IC reading, we want a "delta computed → severity color" overlay.

## Acceptance criteria

- [ ] `src/pages/1_🌍_Globe.py` modified:
  - Default coloration unchanged (technology)
  - Toggle / radio in sidebar : "Color by: [technology | delta severity]"
  - When severity selected: green/yellow/red for parks with delta computed, grey for parks without
  - Uses `data/portfolio_sweep.json` to know which park has a delta
- [ ] Globe still renders without exception
- [ ] Smoke test in `tests/test_pages.py` covers both modes

## Files

- `src/pages/1_🌍_Globe.py` (edit)
- `tests/test_pages.py` (extend)

## Notes

Don't refactor the globe code — additive change only. Reuse existing PyDeck `_GlobeView` config.
