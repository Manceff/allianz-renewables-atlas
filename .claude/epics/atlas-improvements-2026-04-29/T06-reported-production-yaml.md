---
id: T06
epic: E1-portfolio-sweep
parallel: true
blockedBy: []
estimate: 2h
status: pending
---

# T06 — Curate reported_production.yaml

## Context

Per D4: production publiée comes from a hand-curated YAML, not live scraping. Each entry needs a source URL.

## Acceptance criteria

- [ ] New file `data/reported_production.yaml`
- [ ] Schema per entry:
  ```yaml
  - park_id: ourika
    annual_mwh: 80000
    year: 2019
    source_url: "https://www.allianzcapitalpartners.com/..."
    note: "Press release at commissioning, 23000 households figure × ~3.5 MWh/household"
  ```
- [ ] Cover at least 4 of: ourika, solara-4, grenergy-spain-300, brindisi (if T02 found capacity), maevaara, lac-alfred, eurus, north-pickenham
- [ ] If a park has no public production figure, do NOT add a row (rather than guess)
- [ ] New lib `src/lib/reported_production.py` with `load_reported_production() -> dict[park_id, ReportedProduction]`
- [ ] Tests in `tests/test_reported_production.py`

## Files

- `data/reported_production.yaml` (NEW)
- `src/lib/reported_production.py` (NEW)
- `tests/test_reported_production.py` (NEW)

## Notes

Search press releases for figures like "GWh/an", "MWh/year", "produces enough electricity for X households" (multiply by ~3.5 MWh/household for EU average).
Cite the URL even if the figure is approximate ("≈80 GWh/an commissioning estimate" is fine if sourced).
