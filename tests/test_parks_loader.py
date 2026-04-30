"""Tests Pydantic v2 + loader pour data/parks_index.yaml.

TDD : ces tests décrivent l'API attendue de src.lib.parks_loader.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from src.lib.parks_loader import (
    ParkModel,
    ParksIndex,
    Technology,
    get_park_by_id,
    load_parks_index,
)


def test_technology_enum_values() -> None:
    """Les seules technos acceptées sont solar, onshore_wind, offshore_wind, battery_storage."""
    assert {t.value for t in Technology} == {
        "solar",
        "onshore_wind",
        "offshore_wind",
        "battery_storage",
    }


def test_park_model_minimal_valid() -> None:
    """Un ParkModel se construit avec les champs obligatoires uniquement."""
    park = ParkModel(
        id="test-park",
        name="Test Park",
        country="FR",
        technology="solar",
        coordinates=[48.85, 2.35],
        commissioning_year=2020,
        press_release_url="https://example.com/pr",
    )
    assert park.id == "test-park"
    assert park.technology == Technology.SOLAR
    assert park.coordinates == (48.85, 2.35)
    assert park.capacity_mwp is None  # optionnel
    assert park.has_pvgis_estimate is False  # default


def test_park_model_full_valid() -> None:
    """Tous les champs renseignés."""
    park = ParkModel(
        id="ourika",
        name="Ourika Solar Park",
        country="PT",
        technology="solar",
        coordinates=[37.65, -8.22],
        capacity_mwp=46.0,
        commissioning_year=2018,
        operator="WElink Energy",
        allianz_stake_pct=100.0,
        acquisition_year=2018,
        press_release_url="https://www.allianzcapitalpartners.com/foo",
        notes="Premier parc subsidy-free",
        has_pvgis_estimate=True,
        has_reported_production=True,
    )
    assert park.allianz_stake_pct == 100.0
    assert park.has_reported_production is True


def test_park_model_invalid_technology_rejected() -> None:
    with pytest.raises(ValidationError):
        ParkModel(
            id="x",
            name="X",
            country="FR",
            technology="nuclear",  # type: ignore[arg-type]
            coordinates=[0.0, 0.0],
            commissioning_year=2020,
            press_release_url="https://x.test",
        )


def test_park_model_invalid_coordinates_rejected() -> None:
    """Latitude hors bornes."""
    with pytest.raises(ValidationError):
        ParkModel(
            id="x",
            name="X",
            country="FR",
            technology="solar",
            coordinates=[91.0, 0.0],
            commissioning_year=2020,
            press_release_url="https://x.test",
        )


def test_park_model_coordinates_must_be_pair() -> None:
    with pytest.raises(ValidationError):
        ParkModel(
            id="x",
            name="X",
            country="FR",
            technology="solar",
            coordinates=[1.0],  # type: ignore[arg-type]
            commissioning_year=2020,
            press_release_url="https://x.test",
        )


def test_park_model_negative_capacity_rejected() -> None:
    with pytest.raises(ValidationError):
        ParkModel(
            id="x",
            name="X",
            country="FR",
            technology="solar",
            coordinates=[0.0, 0.0],
            capacity_mwp=-10.0,
            commissioning_year=2020,
            press_release_url="https://x.test",
        )


def test_park_model_stake_pct_bounds() -> None:
    with pytest.raises(ValidationError):
        ParkModel(
            id="x",
            name="X",
            country="FR",
            technology="solar",
            coordinates=[0.0, 0.0],
            commissioning_year=2020,
            press_release_url="https://x.test",
            allianz_stake_pct=150.0,
        )


def test_load_parks_index_returns_index() -> None:
    """load_parks_index() lit data/parks_index.yaml et renvoie un ParksIndex."""
    idx = load_parks_index()
    assert isinstance(idx, ParksIndex)
    # V1 solar-only : 11 parcs solaires post-cleanup Gemini 2026-04-30
    assert len(idx.parks) == 11
    assert idx.metadata.total_parks_mapped == 11
    # Tous les parcs sont solaires en V1
    assert all(p.technology.value == "solar" for p in idx.parks)


def test_load_parks_index_uses_cache() -> None:
    """Deux appels successifs renvoient la MÊME instance (lru_cache)."""
    a = load_parks_index()
    b = load_parks_index()
    assert a is b


def test_get_park_by_id_known() -> None:
    park = get_park_by_id("ourika")
    assert park is not None
    assert "Ourika" in park.name
    assert park.technology == Technology.SOLAR


def test_get_park_by_id_unknown_returns_none() -> None:
    assert get_park_by_id("non-existent-park-zzz") is None


def test_load_parks_index_custom_path(tmp_path: Path) -> None:
    """On peut charger depuis un chemin custom (utile pour les tests)."""
    custom = tmp_path / "mini.yaml"
    custom.write_text(
        """
parks:
  - id: foo
    name: Foo
    country: FR
    technology: solar
    coordinates: [10.0, 20.0]
    commissioning_year: 2020
    press_release_url: https://example.com
metadata:
  total_parks_mapped: 1
  total_parks_claimed_by_acp: 1
""",
        encoding="utf-8",
    )
    idx = load_parks_index(path=custom)
    assert len(idx.parks) == 1
    assert idx.parks[0].id == "foo"


def test_all_yaml_parks_validate() -> None:
    """Sanity : chaque parc du YAML réel passe la validation Pydantic."""
    idx = load_parks_index()
    ids = [p.id for p in idx.parks]
    assert len(ids) == len(set(ids)), "IDs dupliqués"
