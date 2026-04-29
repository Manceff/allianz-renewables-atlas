---
type: epic
slug: atlas-improvements-2026-04-29
prd: .claude/prds/atlas-improvements-2026-04-29.md
status: in_progress
created: 2026-04-29
---

# Epic — Atlas Improvements 2026-04-29

## Sub-epics

| ID | Sub-epic | Priority | Tasks |
|----|----------|----------|-------|
| E0 | Foundation (schemas + fixes + methodology) | P0 (prerequisite) | T01, T02, T03, T04 |
| E1 | Portfolio Sweep Delta | P0 | T05, T06, T07, T08 |
| E2 | Ourika Monograph | P0 | T09, T10 |
| E3 | Investment Committee Snapshot | P1 | T11, T12, T13 |
| E4 | Tests + Polish + Deploy | P1 | T14 |

## Dependency graph

```
T01 (parks fix coords)        ──┐
T02 (parks fix capacity)       ─┤
T04 (page methodology)         ─┤    parallel start
T06 (reported_production.yaml) ─┘

T03 (schemas Pydantic) ──> T05 (confidence_interval lib)
                          └─> T09 (ourika monthly fetch)

T05 + T06 ──> T07 (precompute sweep) ──> T08 (page Portfolio Sweep) ──┐
                                                                       │
T09 ──> T10 (page Ourika Monograph)                                    │
                                                                       ├─> T14 (tests + polish + deploy)
T07 + T08 ──> T11 (globe severity layer)                              │
              T12 (IC compute aggregates)                              │
              T13 (page IC Snapshot)                                   │
                                                                       │
                                                                       ┘
```

## Parallel windows

- **Window 1 (J0):** T01, T02, T04, T06 — tous parallel: true (no shared files)
- **Window 2 (J1):** T03 (schemas) — blocks T05/T09, sequential
- **Window 3 (J1-J2):** T05 + T09 — parallel after T03
- **Window 4 (J2-J3):** T07 — depends on T05 + T06
- **Window 5 (J3-J4):** T08 + T10 + T11 + T12 — pages parallel
- **Window 6 (J4):** T13 — depends on T11 + T12
- **Window 7 (J5-J6):** T14 — final integration
