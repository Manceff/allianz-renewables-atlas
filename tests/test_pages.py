"""Smoke tests pour les pages Streamlit — vérifie qu'elles render sans exception."""

from __future__ import annotations


def test_app_entry_renders():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file("src/app.py").run()
    assert not at.exception


def test_atlas_renders_default(monkeypatch):
    """Atlas page — stub PVGIS pour éviter les hits réseau."""
    from src.lib import confidence_interval as ci_mod
    from src.lib.schemas import ConfidenceInterval, LossScenario
    from streamlit.testing.v1 import AppTest

    def _fake_range(lat, lon, peakpower_mw, loss_scenarios=(10.0, 14.0, 18.0)):
        scenarios = [
            LossScenario(loss_pct=lp, annual_kwh=peakpower_mw * 1500 * (1 - lp / 100) * 1000)
            for lp in loss_scenarios
        ]
        return ConfidenceInterval(
            low_mwh=peakpower_mw * 1500 * 0.82,
            mid_mwh=peakpower_mw * 1500 * 0.86,
            high_mwh=peakpower_mw * 1500 * 0.90,
            scenarios=scenarios,
        )

    monkeypatch.setattr(ci_mod, "compute_pvgis_range", _fake_range)

    at = AppTest.from_file("src/pages/1_🌍_Atlas.py").run(timeout=30)
    assert not at.exception


def test_methodology_page_renders():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file("src/pages/2_📐_Methodology.py").run()
    assert not at.exception
