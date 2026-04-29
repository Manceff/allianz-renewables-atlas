---
id: T12
epic: E3-ic-snapshot
parallel: true
blockedBy: []
estimate: 1h
status: pending
---

# T12 — Portfolio aggregates lib

## Context

The IC Snapshot page needs portfolio-level aggregates. Compute once, expose cleanly.

## Acceptance criteria

- [ ] New file `src/lib/portfolio_aggregates.py` with function:
  ```python
  def compute_aggregates(parks: list[Park]) -> PortfolioAggregates
  ```
  Returns dataclass / Pydantic with:
  - `total_capacity_mw`
  - `count_parks`
  - `count_countries`
  - `count_techs`
  - `capacity_by_tech: dict[str, float]`
  - `capacity_by_country: dict[str, float]`
  - `vintage_distribution: dict[int, float]` (year → capacity)
  - `top5_by_capacity: list[Park]`
- [ ] Tests in `tests/test_portfolio_aggregates.py`

## Files

- `src/lib/portfolio_aggregates.py` (NEW)
- `tests/test_portfolio_aggregates.py` (NEW)

## Notes

Pure function, no IO. Takes the loaded parks list as input.
