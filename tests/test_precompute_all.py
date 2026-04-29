"""Tests pour `scripts.precompute_all._build_portfolio_sweep`.

On mocke `compute_pvgis_range` et `load_reported_production` pour rester offline
(et indépendant du YAML real `parks_index.yaml`).
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from pydantic import HttpUrl

from scripts.precompute_all import _build_portfolio_sweep
from src.lib.reported_production import ReportedProduction
from src.lib.schemas import ConfidenceInterval, PortfolioSweep


def _ci(mid_mwh: float) -> ConfidenceInterval:
    return ConfidenceInterval(
        low_mwh=mid_mwh * 0.9,
        mid_mwh=mid_mwh,
        high_mwh=mid_mwh * 1.1,
        scenarios=[],
    )


def _reported(
    park_id: str, annual_mwh: float, year: int = 2020
) -> ReportedProduction:
    return ReportedProduction(
        park_id=park_id,
        annual_mwh=annual_mwh,
        year=year,
        source_url=HttpUrl("https://example.com/source"),
        note=None,
    )


def _solar_park(
    park_id: str = "ourika",
    capacity: float | None = 46.0,
    has_pvgis: bool = True,
    excluded: bool = False,
    technology: str = "solar",
    coords: tuple[float, float] = (37.65, -8.22),
) -> dict:
    park: dict = {
        "id": park_id,
        "name": park_id,
        "country": "PT",
        "technology": technology,
        "coordinates": list(coords),
        "capacity_mwp": capacity,
        "commissioning_year": 2018,
        "press_release_url": "https://example.com/pr",
        "has_pvgis_estimate": has_pvgis,
        "has_reported_production": True,
    }
    if excluded:
        park["excluded_from_sweep"] = True
    return park


def test_build_sweep_writes_file_with_eligible_park(tmp_path: Path) -> None:
    parks = [_solar_park("ourika", 46.0)]
    output = tmp_path / "portfolio_sweep.json"

    with patch(
        "scripts.precompute_all.compute_pvgis_range",
        return_value=_ci(82_000.0),
    ), patch(
        "scripts.precompute_all.load_reported_production",
        return_value={"ourika": _reported("ourika", 80_000.0)},
    ):
        sweep = _build_portfolio_sweep(parks, failures=[], output_path=output)

    assert isinstance(sweep, PortfolioSweep)
    assert output.exists()
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert len(payload["entries"]) == 1
    entry = payload["entries"][0]
    assert entry["park_id"] == "ourika"
    assert entry["reported_mwh"] == 80_000.0
    # delta = (82000 - 80000) / 80000 * 100 = 2.5%
    assert abs(entry["delta_pct"] - 2.5) < 1e-6
    assert entry["severity"] == "green"
    assert entry["confidence_interval"]["mid_mwh"] == 82_000.0


def test_build_sweep_skips_excluded_park(tmp_path: Path) -> None:
    parks = [_solar_park("ourika", 46.0, excluded=True)]
    output = tmp_path / "portfolio_sweep.json"

    with patch(
        "scripts.precompute_all.compute_pvgis_range",
        return_value=_ci(82_000.0),
    ) as mock_pvgis, patch(
        "scripts.precompute_all.load_reported_production",
        return_value={"ourika": _reported("ourika", 80_000.0)},
    ):
        sweep = _build_portfolio_sweep(parks, failures=[], output_path=output)

    assert sweep.entries == []
    assert mock_pvgis.call_count == 0


def test_build_sweep_skips_park_without_reported(tmp_path: Path) -> None:
    parks = [_solar_park("solara-4", 219.0)]
    output = tmp_path / "portfolio_sweep.json"

    with patch(
        "scripts.precompute_all.compute_pvgis_range",
        return_value=_ci(400_000.0),
    ) as mock_pvgis, patch(
        "scripts.precompute_all.load_reported_production",
        return_value={},  # no reported entry
    ):
        sweep = _build_portfolio_sweep(parks, failures=[], output_path=output)

    assert sweep.entries == []
    assert mock_pvgis.call_count == 0


def test_build_sweep_skips_non_solar_and_no_pvgis(tmp_path: Path) -> None:
    parks = [
        _solar_park("dahme", 76.0, technology="onshore_wind"),
        _solar_park("brindisi", None, has_pvgis=True),  # capacity manquante
        _solar_park("foo", 10.0, has_pvgis=False),
    ]
    output = tmp_path / "portfolio_sweep.json"

    with patch(
        "scripts.precompute_all.compute_pvgis_range",
        return_value=_ci(82_000.0),
    ) as mock_pvgis, patch(
        "scripts.precompute_all.load_reported_production",
        return_value={
            "dahme": _reported("dahme", 80_000.0),
            "brindisi": _reported("brindisi", 12_000.0),
            "foo": _reported("foo", 8_000.0),
        },
    ):
        sweep = _build_portfolio_sweep(parks, failures=[], output_path=output)

    assert sweep.entries == []
    assert mock_pvgis.call_count == 0


def test_build_sweep_multiple_eligible_parks(tmp_path: Path) -> None:
    parks = [
        _solar_park("ourika", 46.0),
        _solar_park("solara-4", 219.0, coords=(37.3468, -7.6956)),
        _solar_park("grenergy-spain-300", 300.0, coords=(40.0, -3.7)),
    ]
    output = tmp_path / "portfolio_sweep.json"

    ci_by_id = {
        "ourika": _ci(82_000.0),
        "solara-4": _ci(385_000.0),
        "grenergy-spain-300": _ci(560_000.0),
    }

    def fake_compute_pvgis_range(*, lat, lon, peakpower_mw, **_):
        # Map by capacity since (lat, lon) is unique per call
        if peakpower_mw == 46.0:
            return ci_by_id["ourika"]
        if peakpower_mw == 219.0:
            return ci_by_id["solara-4"]
        return ci_by_id["grenergy-spain-300"]

    reported = {
        "ourika": _reported("ourika", 80_000.0),
        "solara-4": _reported("solara-4", 380_000.0),
        "grenergy-spain-300": _reported("grenergy-spain-300", 557_100.0),
    }

    with patch(
        "scripts.precompute_all.compute_pvgis_range",
        side_effect=fake_compute_pvgis_range,
    ), patch(
        "scripts.precompute_all.load_reported_production",
        return_value=reported,
    ):
        sweep = _build_portfolio_sweep(parks, failures=[], output_path=output)

    assert len(sweep.entries) == 3
    ids = {e.park_id for e in sweep.entries}
    assert ids == {"ourika", "solara-4", "grenergy-spain-300"}


def test_build_sweep_logs_failure_on_pvgis_error(tmp_path: Path) -> None:
    from src.lib.pvgis_fetch import PvgisFetchError

    parks = [_solar_park("ourika", 46.0)]
    output = tmp_path / "portfolio_sweep.json"
    failures: list[dict[str, str]] = []

    with patch(
        "scripts.precompute_all.compute_pvgis_range",
        side_effect=PvgisFetchError("boom"),
    ), patch(
        "scripts.precompute_all.load_reported_production",
        return_value={"ourika": _reported("ourika", 80_000.0)},
    ):
        sweep = _build_portfolio_sweep(parks, failures=failures, output_path=output)

    assert sweep.entries == []
    assert len(failures) == 1
    assert failures[0]["step"] == "sweep"
    assert failures[0]["id"] == "ourika"
