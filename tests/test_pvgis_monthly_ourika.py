"""Tests T09 — `data/parks/ourika/pvgis_monthly.json`.

Vérifie que le sidecar mensuel persisté pour Ourika respecte le contrat
attendu par la page Monograph (T10) : 12 floats > 0, somme ≈ annual.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
OURIKA_DIR = ROOT / "data" / "parks" / "ourika"
MONTHLY_FILE = OURIKA_DIR / "pvgis_monthly.json"
ESTIMATED_FILE = OURIKA_DIR / "production_estimated.json"


def _load_monthly() -> dict:
    assert MONTHLY_FILE.exists(), f"Fichier attendu absent : {MONTHLY_FILE}"
    return json.loads(MONTHLY_FILE.read_text(encoding="utf-8"))


def test_pvgis_monthly_file_exists() -> None:
    assert MONTHLY_FILE.exists()


def test_pvgis_monthly_has_12_entries() -> None:
    data = _load_monthly()
    monthly = data["monthly_production_kwh"]
    assert isinstance(monthly, list)
    assert len(monthly) == 12


def test_pvgis_monthly_values_are_positive_floats() -> None:
    data = _load_monthly()
    for i, value in enumerate(data["monthly_production_kwh"]):
        assert isinstance(value, float), f"month {i + 1} not a float : {type(value)}"
        assert value > 0, f"month {i + 1} non strictement positif : {value}"


def test_pvgis_monthly_sum_matches_annual_within_1pct() -> None:
    """Somme des 12 mois ≈ annual_total_kwh à 1 % près."""
    monthly = _load_monthly()["monthly_production_kwh"]
    estimated = json.loads(ESTIMATED_FILE.read_text(encoding="utf-8"))
    annual = float(estimated["annual_total_kwh"])

    total = sum(monthly)
    assert annual > 0
    assert total == pytest.approx(annual, rel=0.01)


def test_pvgis_monthly_validates_against_pvgisoutput_monthly_field() -> None:
    """Le bloc {monthly_production_kwh: [...]} satisfait la contrainte du schéma PVGISOutput."""
    from pydantic import TypeAdapter

    monthly = _load_monthly()["monthly_production_kwh"]
    # Replique le min_length=12 / max_length=12 du field PVGISOutput.monthly_production_kwh.
    adapter = TypeAdapter(list[float])
    validated = adapter.validate_python(monthly)
    assert len(validated) == 12
    assert all(v > 0 for v in validated)


def test_precompute_all_writes_pvgis_monthly_sidecar(tmp_path, monkeypatch) -> None:
    """`_process_park` produit `pvgis_monthly.json` à côté de `production_estimated.json`."""
    from scripts import precompute_all

    monthly = [float(1000 * (i + 1)) for i in range(12)]
    fake_production = {
        "inputs": {
            "lat": 37.65,
            "lon": -8.22,
            "peakpower_kw": 46000.0,
            "tilt_deg": 27.65,
            "azimuth_deg": 0.0,
            "loss_pct": 14.0,
            "pv_technology": "crystSi",
        },
        "monthly_production_kwh": monthly,
        "annual_total_kwh": sum(monthly),
        "annual_total_mwh": sum(monthly) / 1000.0,
        "metadata": {"source": "PVGIS v5.2 (JRC EU)"},
        "raw_totals_fixed": {},
    }

    monkeypatch.setattr(precompute_all, "PARKS_DIR", tmp_path)
    monkeypatch.setattr(precompute_all, "fetch_pvgis_pvcalc", lambda **kwargs: fake_production)

    park = {
        "id": "ourika",
        "name": "Ourika Solar Park",
        "technology": "solar",
        "coordinates": [37.65, -8.22],
        "capacity_mwp": 46,
        "has_pvgis_estimate": True,
        "has_reported_production": False,
    }
    precompute_all._process_park(park, failures=[], sentinel_enabled=False)

    sidecar = tmp_path / "ourika" / "pvgis_monthly.json"
    assert sidecar.exists()
    content = json.loads(sidecar.read_text(encoding="utf-8"))
    assert content["monthly_production_kwh"] == monthly
