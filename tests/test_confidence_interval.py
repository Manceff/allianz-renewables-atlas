"""Tests pour `compute_pvgis_range` — sensibilité loss → CI low/mid/high."""

from __future__ import annotations

from unittest.mock import patch

from src.lib.confidence_interval import compute_pvgis_range
from src.lib.schemas import ConfidenceInterval


def _mock_fetch(loss_pct: float, **_kwargs) -> dict:
    """Fake PVGIS — production linéairement décroissante avec les pertes."""
    base_kwh = 80_000_000.0
    factor = 1.0 - (loss_pct - 14.0) / 100.0
    return {"annual_total_kwh": base_kwh * factor}


@patch(
    "src.lib.confidence_interval.fetch_pvgis_pvcalc",
    side_effect=lambda **kw: _mock_fetch(**kw),
)
def test_compute_range_orders_low_mid_high(mock_fetch):
    ci = compute_pvgis_range(lat=37.65, lon=-8.22, peakpower_mw=46.0)
    assert isinstance(ci, ConfidenceInterval)
    assert ci.low_mwh < ci.mid_mwh < ci.high_mwh
    assert len(ci.scenarios) == 3


@patch(
    "src.lib.confidence_interval.fetch_pvgis_pvcalc",
    side_effect=lambda **kw: _mock_fetch(**kw),
)
def test_compute_range_calls_pvgis_once_per_scenario(mock_fetch):
    compute_pvgis_range(
        lat=0.0,
        lon=0.0,
        peakpower_mw=1.0,
        loss_scenarios=(8.0, 14.0, 20.0),
    )
    assert mock_fetch.call_count == 3


@patch(
    "src.lib.confidence_interval.fetch_pvgis_pvcalc",
    side_effect=lambda **kw: _mock_fetch(**kw),
)
def test_compute_range_low_matches_highest_loss(mock_fetch):
    ci = compute_pvgis_range(
        lat=10.0,
        lon=20.0,
        peakpower_mw=5.0,
        loss_scenarios=(5.0, 14.0, 25.0),
    )
    # low = scénario 25% pertes (production min)
    expected_low_kwh = 80_000_000.0 * (1.0 - (25.0 - 14.0) / 100.0)
    assert ci.low_mwh == expected_low_kwh / 1000.0
    # high = scénario 5% pertes
    expected_high_kwh = 80_000_000.0 * (1.0 - (5.0 - 14.0) / 100.0)
    assert ci.high_mwh == expected_high_kwh / 1000.0


@patch(
    "src.lib.confidence_interval.fetch_pvgis_pvcalc",
    side_effect=lambda **kw: _mock_fetch(**kw),
)
def test_compute_range_passes_coordinates_and_capacity(mock_fetch):
    compute_pvgis_range(lat=37.65, lon=-8.22, peakpower_mw=46.0)
    for call in mock_fetch.call_args_list:
        kwargs = call.kwargs
        assert kwargs["lat"] == 37.65
        assert kwargs["lon"] == -8.22
        assert kwargs["peakpower_mw"] == 46.0
        assert "loss_pct" in kwargs
