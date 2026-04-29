---
id: T14
epic: E4-final
parallel: false
blockedBy: [T08, T10, T13, T04]
estimate: 2h
status: pending
---

# T14 — Tests integration + polish + deploy

## Context

Final integration: full test suite, screenshots, Streamlit Cloud deploy, README update.

## Acceptance criteria

- [ ] `pytest tests/ -v` ≥ 84/84 vert
- [ ] `streamlit run src/app.py` launches, all 6 pages render
- [ ] Smoke test via `streamlit.testing.v1.AppTest` for each new page passes
- [ ] README updated:
  - Section "Pages" listant les 6 pages avec 1 ligne descriptive
  - Section "Methodology" pointant vers la page in-app
  - Lien Streamlit Cloud si déployé
- [ ] CHANGELOG.md ou agent-log.md entry for 2026-04-29 PRD execution
- [ ] Streamlit Cloud redeploy (manuel — instructions dans IMPROVEMENT_REPORT)

## Files

- `README.md` (edit)
- `agent-log.md` (append)
- screenshots/ (add 2-3 PNG of new pages)

## Notes

If Streamlit Cloud deploy fails, document in IMPROVEMENT_REPORT and provide Chrome screenshots as fallback.
