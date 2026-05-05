"""Tests de validation structurelle de data/parks_index.yaml.

Smoke test minimum à faire passer avant Phase 1 et Phase 2 :
- le YAML parse
- chaque parc a les champs obligatoires
- les coordonnées sont des floats valides
- les technologies sont dans le set autorisé

L'agent Phase 2 enrichira ces tests avec validation Pydantic complète.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

PARKS_INDEX = Path(__file__).resolve().parent.parent / "data" / "parks_index.yaml"

REQUIRED_FIELDS = {
    "id",
    "name",
    "country",
    "technology",
    "coordinates",
    "commissioning_year",
    "press_release_url",
}

ALLOWED_TECHNOLOGIES = {"solar", "onshore_wind", "offshore_wind", "battery_storage"}


@pytest.fixture(scope="module")
def parks_data() -> dict:
    assert PARKS_INDEX.exists(), f"Fichier manquant : {PARKS_INDEX}"
    with open(PARKS_INDEX) as f:
        return yaml.safe_load(f)


def test_yaml_parses(parks_data: dict) -> None:
    assert "parks" in parks_data
    assert isinstance(parks_data["parks"], list)
    assert len(parks_data["parks"]) >= 1


def test_metadata_block(parks_data: dict) -> None:
    assert "metadata" in parks_data
    assert "total_parks_mapped" in parks_data["metadata"]
    assert "total_parks_claimed_by_acp" in parks_data["metadata"]


def test_each_park_has_required_fields(parks_data: dict) -> None:
    for park in parks_data["parks"]:
        missing = REQUIRED_FIELDS - park.keys()
        assert not missing, f"Parc {park.get('id', '?')} : champs manquants {missing}"


def test_technologies_are_valid(parks_data: dict) -> None:
    for park in parks_data["parks"]:
        assert (
            park["technology"] in ALLOWED_TECHNOLOGIES
        ), f"Parc {park['id']} : technology '{park['technology']}' non valide"


def test_coordinates_are_lat_lon_pair(parks_data: dict) -> None:
    for park in parks_data["parks"]:
        coords = park["coordinates"]
        assert isinstance(coords, list) and len(coords) == 2, (
            f"Parc {park['id']} : coordonnées doivent être [lat, lon]"
        )
        lat, lon = coords
        assert -90 <= lat <= 90, f"Parc {park['id']} : latitude hors bornes"
        assert -180 <= lon <= 180, f"Parc {park['id']} : longitude hors bornes"


def test_ids_are_unique(parks_data: dict) -> None:
    ids = [p["id"] for p in parks_data["parks"]]
    assert len(ids) == len(set(ids)), f"Doublons d'ID détectés : {ids}"
