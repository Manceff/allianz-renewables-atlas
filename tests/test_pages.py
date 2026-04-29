"""Smoke tests pour les pages Streamlit — vérifie qu'elles render sans exception."""

from __future__ import annotations


def test_methodology_page_renders():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file("src/pages/5_📐_Methodology.py").run()
    assert not at.exception


def test_ourika_monograph_renders(monkeypatch):
    """Smoke test page Monograph. Stub PVGIS pour éviter le hit réseau."""
    from src.lib import confidence_interval as ci_mod
    from src.lib.schemas import ConfidenceInterval, LossScenario
    from streamlit.testing.v1 import AppTest

    def _fake_compute_pvgis_range(
        lat: float, lon: float, peakpower_mw: float, loss_scenarios=(10.0, 14.0, 18.0)
    ) -> ConfidenceInterval:
        # Valeurs proches de l'ordre de grandeur Ourika (≈73-77 GWh/an).
        scenarios = [
            LossScenario(loss_pct=10.0, annual_kwh=77_000_000.0),
            LossScenario(loss_pct=14.0, annual_kwh=73_500_000.0),
            LossScenario(loss_pct=18.0, annual_kwh=70_000_000.0),
        ]
        return ConfidenceInterval(
            low_mwh=70_000.0,
            mid_mwh=73_500.0,
            high_mwh=77_000.0,
            scenarios=scenarios,
        )

    monkeypatch.setattr(ci_mod, "compute_pvgis_range", _fake_compute_pvgis_range)

    at = AppTest.from_file("src/pages/3_🔬_Ourika_Monograph.py").run(timeout=30)
    assert not at.exception


def test_globe_renders_default():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file("src/pages/1_🌍_Globe.py").run()
    assert not at.exception


def test_globe_renders_severity_mode():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file("src/pages/1_🌍_Globe.py").run()
    radios = at.radio
    if radios:
        radios[0].set_value("Delta severity").run()
    assert not at.exception
