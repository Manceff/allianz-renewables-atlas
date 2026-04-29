"""Tests des schémas Pydantic v2 contre les JSON existants sur disque.

Garantit la compat backwards : tout fichier déjà produit doit valider sans
modification. Si un parc manque un fichier, le test est skippé (les seeds
ne sont pas tous complets — solar/wind/BESS).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.lib.schemas import (
    ConfidenceInterval,
    DeltaOutput,
    LossScenario,
    ParkMetadata,
    PortfolioSweep,
    PortfolioSweepEntry,
    ProductionReported,
    PVGISOutput,
)

PARKS_DIR = Path(__file__).parent.parent / "data" / "parks"
PARK_DIRS = sorted(d for d in PARKS_DIR.iterdir() if d.is_dir())


@pytest.mark.parametrize("park_dir", PARK_DIRS, ids=lambda d: d.name)
def test_metadata_validates(park_dir: Path) -> None:
    f = park_dir / "metadata.json"
    if not f.exists():
        pytest.skip(f"no metadata.json in {park_dir.name}")
    data = json.loads(f.read_text())
    ParkMetadata.model_validate(data)


@pytest.mark.parametrize("park_dir", PARK_DIRS, ids=lambda d: d.name)
def test_pvgis_validates(park_dir: Path) -> None:
    # Le précompute écrit en `production_estimated.json` (cf. pvgis_fetch.py).
    f = park_dir / "production_estimated.json"
    if not f.exists():
        pytest.skip(f"no production_estimated.json in {park_dir.name}")
    data = json.loads(f.read_text())
    PVGISOutput.model_validate(data)


@pytest.mark.parametrize("park_dir", PARK_DIRS, ids=lambda d: d.name)
def test_delta_validates(park_dir: Path) -> None:
    f = park_dir / "delta.json"
    if not f.exists():
        pytest.skip(f"no delta.json in {park_dir.name}")
    data = json.loads(f.read_text())
    DeltaOutput.model_validate(data)


@pytest.mark.parametrize("park_dir", PARK_DIRS, ids=lambda d: d.name)
def test_production_reported_validates(park_dir: Path) -> None:
    f = park_dir / "production_reported.json"
    if not f.exists():
        pytest.skip(f"no production_reported.json in {park_dir.name}")
    data = json.loads(f.read_text())
    ProductionReported.model_validate(data)


def test_confidence_interval_construction() -> None:
    ci = ConfidenceInterval(
        low_mwh=70000,
        mid_mwh=75000,
        high_mwh=80000,
        scenarios=[
            LossScenario(loss_pct=18.0, annual_kwh=70000000),
            LossScenario(loss_pct=14.0, annual_kwh=75000000),
            LossScenario(loss_pct=10.0, annual_kwh=80000000),
        ],
    )
    assert ci.low_mwh < ci.mid_mwh < ci.high_mwh
    assert len(ci.scenarios) == 3
    assert ci.scenarios[1].loss_pct == 14.0


def test_portfolio_sweep_entry_severity_default() -> None:
    entry = PortfolioSweepEntry(
        park_id="ourika",
        capacity_mwp=46.0,
        confidence_interval=ConfidenceInterval(
            low_mwh=70000, mid_mwh=75000, high_mwh=80000, scenarios=[]
        ),
    )
    assert entry.severity == "unknown"
    assert entry.reported_mwh is None
    assert entry.source_url is None


def test_portfolio_sweep_round_trip() -> None:
    sweep = PortfolioSweep.model_validate(
        {
            "entries": [
                {
                    "park_id": "ourika",
                    "capacity_mwp": 46.0,
                    "confidence_interval": {
                        "low_mwh": 70000,
                        "mid_mwh": 75000,
                        "high_mwh": 80000,
                        "scenarios": [],
                    },
                    "reported_mwh": 80000.0,
                    "delta_pct": -8.13,
                    "severity": "yellow",
                    "source_url": "https://www.allianzcapitalpartners.com/",
                }
            ],
            "generated_at": "2026-04-29T12:00:00Z",
        }
    )
    assert len(sweep.entries) == 1
    assert sweep.entries[0].severity == "yellow"
