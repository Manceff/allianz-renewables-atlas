"""Tests pour src.lib.compute_delta — comparaison PVGIS estimée vs production publiée."""

from __future__ import annotations

import pytest

from src.lib.compute_delta import (
    Severity,
    compute_production_delta,
    severity_from_relative_delta,
)


# ---------- severity_from_relative_delta ----------


@pytest.mark.parametrize(
    "rel_pct, expected",
    [
        (0.0, Severity.GREEN),
        (4.99, Severity.GREEN),
        (-4.99, Severity.GREEN),
        (5.0, Severity.YELLOW),
        (-5.0, Severity.YELLOW),
        (9.99, Severity.YELLOW),
        (10.0, Severity.RED),
        (-10.0, Severity.RED),
        (50.0, Severity.RED),
    ],
)
def test_severity_thresholds(rel_pct: float, expected: Severity) -> None:
    assert severity_from_relative_delta(rel_pct) == expected


# ---------- compute_production_delta ----------


def test_compute_delta_basic() -> None:
    """Estimée 100, reportée 95 → +5.26% (yellow)."""
    out = compute_production_delta(estimated_annual_mwh=100.0, reported_annual_mwh=95.0)

    assert out["estimated_annual_mwh"] == 100.0
    assert out["reported_annual_mwh"] == 95.0
    assert out["absolute_delta_mwh"] == pytest.approx(5.0)
    assert out["relative_delta_pct"] == pytest.approx((100.0 - 95.0) / 95.0 * 100, rel=1e-6)
    assert out["severity"] == "yellow"


def test_compute_delta_perfect_match_green() -> None:
    out = compute_production_delta(estimated_annual_mwh=100.0, reported_annual_mwh=100.0)
    assert out["relative_delta_pct"] == 0.0
    assert out["severity"] == "green"


def test_compute_delta_negative_relative_delta() -> None:
    """Estimée < reportée donne un delta négatif (parc surperforme)."""
    out = compute_production_delta(estimated_annual_mwh=80.0, reported_annual_mwh=100.0)
    assert out["relative_delta_pct"] == pytest.approx(-20.0)
    assert out["severity"] == "red"


def test_compute_delta_red_severity_above_10pct() -> None:
    out = compute_production_delta(estimated_annual_mwh=120.0, reported_annual_mwh=100.0)
    assert out["relative_delta_pct"] == pytest.approx(20.0)
    assert out["severity"] == "red"


def test_compute_delta_zero_reported_raises() -> None:
    with pytest.raises(ValueError):
        compute_production_delta(estimated_annual_mwh=100.0, reported_annual_mwh=0.0)


def test_compute_delta_negative_inputs_raise() -> None:
    with pytest.raises(ValueError):
        compute_production_delta(estimated_annual_mwh=-10.0, reported_annual_mwh=100.0)
    with pytest.raises(ValueError):
        compute_production_delta(estimated_annual_mwh=100.0, reported_annual_mwh=-10.0)


def test_compute_delta_output_is_json_serialisable() -> None:
    """Le dict doit être directement passable à json.dumps."""
    import json

    out = compute_production_delta(estimated_annual_mwh=100.0, reported_annual_mwh=95.0)
    s = json.dumps(out)
    assert isinstance(s, str)
    assert "yellow" in s


def test_compute_delta_includes_interpretation_text() -> None:
    """Le delta JSON expose une `interpretation` lisible par l'analyste."""
    out = compute_production_delta(estimated_annual_mwh=100.0, reported_annual_mwh=95.0)
    assert "interpretation" in out
    assert isinstance(out["interpretation"], str)
    assert len(out["interpretation"]) > 0
