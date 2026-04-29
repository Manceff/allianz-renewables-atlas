---
id: T02
epic: E0-foundation
parallel: true
blockedBy: []
estimate: 30min
status: pending
---

# T02 — Fix brindisi capacity_mwp

## Context

`data/parks_index.yaml` has `capacity_mwp: null` for `brindisi`. This is the first 2010 Allianz Specialised Investments solar deal — capacity should be findable in archives.

## Acceptance criteria

- [ ] One of:
  - `capacity_mwp` filled with sourced value + URL comment, OR
  - Park flagged with `excluded_from_sweep: true` and reason documented in `data/UNCERTAIN.md`
- [ ] `pytest tests/test_parks_index.py` still passes

## Files

- `data/parks_index.yaml` (edit)
- `data/UNCERTAIN.md` (append if excluded)

## Notes

If unable to find capacity in 30min, exclude rather than guess. Per CLAUDE.md: "transparence", never invent.
