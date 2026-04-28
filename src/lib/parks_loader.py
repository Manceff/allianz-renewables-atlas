"""Chargeur Pydantic v2 du master index `data/parks_index.yaml`.

Expose :
- `Technology` : enum des technologies autorisées
- `ParkModel` : schéma validé d'un parc
- `ParksIndex` : conteneur (parks + metadata)
- `load_parks_index()` : lit le YAML, valide, met en cache
- `get_park_by_id()` : helper de recherche
"""

from __future__ import annotations

import logging
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Annotated

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

logger = logging.getLogger(__name__)

DEFAULT_PARKS_INDEX = (
    Path(__file__).resolve().parent.parent.parent / "data" / "parks_index.yaml"
)


class Technology(str, Enum):
    """Les 4 technologies couvertes par l'atlas."""

    SOLAR = "solar"
    ONSHORE_WIND = "onshore_wind"
    OFFSHORE_WIND = "offshore_wind"
    BATTERY_STORAGE = "battery_storage"


class ParkModel(BaseModel):
    """Schéma validé d'un parc Renewables Allianz."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    country: str = Field(min_length=2)
    technology: Technology
    coordinates: tuple[float, float]
    capacity_mwp: float | None = Field(default=None, ge=0)
    commissioning_year: int = Field(ge=1980, le=2050)
    operator: str | None = None
    allianz_stake_pct: float | None = Field(default=None, ge=0, le=100)
    acquisition_year: int | None = Field(default=None, ge=1980, le=2050)
    press_release_url: str = Field(min_length=1)
    notes: str | None = None
    has_pvgis_estimate: bool = False
    has_reported_production: bool = False

    @field_validator("coordinates", mode="before")
    @classmethod
    def _coords_pair(cls, v: object) -> tuple[float, float]:
        if not isinstance(v, (list, tuple)) or len(v) != 2:
            raise ValueError("coordinates must be a [lat, lon] pair")
        lat, lon = float(v[0]), float(v[1])
        if not -90 <= lat <= 90:
            raise ValueError(f"latitude {lat} hors bornes [-90, 90]")
        if not -180 <= lon <= 180:
            raise ValueError(f"longitude {lon} hors bornes [-180, 180]")
        return (lat, lon)

    @property
    def lat(self) -> float:
        return self.coordinates[0]

    @property
    def lon(self) -> float:
        return self.coordinates[1]


class ParksMetadata(BaseModel):
    """Bloc metadata du YAML (compteurs de transparence)."""

    model_config = ConfigDict(extra="allow")

    total_parks_mapped: int = Field(ge=0)
    total_parks_claimed_by_acp: int = Field(ge=0)
    capacity_total_mw: float | None = None
    countries_covered: list[str] | None = None
    source_disclaimer: str | None = None
    phase1_completed_on: str | None = None


class ParksIndex(BaseModel):
    """Container racine du fichier parks_index.yaml."""

    model_config = ConfigDict(extra="allow")

    parks: Annotated[list[ParkModel], Field(min_length=1)]
    metadata: ParksMetadata


def _load_uncached(path: Path) -> ParksIndex:
    if not path.exists():
        raise FileNotFoundError(f"parks_index.yaml introuvable : {path}")
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return ParksIndex.model_validate(raw)


@lru_cache(maxsize=8)
def _load_cached(path_str: str) -> ParksIndex:
    return _load_uncached(Path(path_str))


def load_parks_index(path: Path | None = None) -> ParksIndex:
    """Charge et valide `parks_index.yaml`. Cache LRU par chemin résolu.

    Args:
        path: chemin vers le YAML ; défaut = data/parks_index.yaml.
    """
    target = (path or DEFAULT_PARKS_INDEX).resolve()
    return _load_cached(str(target))


def get_park_by_id(park_id: str, path: Path | None = None) -> ParkModel | None:
    """Renvoie le parc dont l'id matche, ou None."""
    idx = load_parks_index(path=path)
    for park in idx.parks:
        if park.id == park_id:
            return park
    return None
