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


class SubSite(BaseModel):
    """Sous-site d'un portfolio multi-sites (ex. Elgin Ireland 16 sites).

    Coords are physical site location (commune-level if commune source, or precise from SEAI Solar Atlas).
    `capacity_mw` is AC export capacity (what's contracted on RESS / EirGrid). DC peak ≈ AC × dc_ac_ratio.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    county: str = Field(min_length=1)
    capacity_mw: float = Field(ge=0, description="AC export capacity in MWac")
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    eirgrid_code: str | None = Field(default=None, description="EirGrid project code (DG1xxx / TGxxx)")
    eirgrid_name: str | None = Field(default=None, description="Canonical EirGrid project name")
    station: str | None = Field(default=None, description="Grid connection station")
    seai_status: str | None = Field(default=None, description="Connected | Contracted (per SEAI Solar Atlas, may lag reality)")
    firm_access: str | None = Field(default=None, description="EirGrid Firm Access date (admin, ≠ energization)")
    esb_status: str | None = Field(default=None, description="Energised | Contracted (per ESB Networks DSO report — authoritative)")
    esb_connect_date: str | None = Field(default=None, description="ISO date YYYY-MM-DD of grid energization, per ESB DSO report")
    offer_type: str | None = Field(default=None, description="Non GPA | ECP-2.1 | etc. — non-firm = curtailment risk")
    note: str | None = None


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
    excluded_from_sweep: bool = False
    sub_sites: tuple[SubSite, ...] | None = None
    sub_sites_caption: str | None = None
    portfolio_status: str | None = Field(
        default=None,
        description="'forward_sale' (Allianz bought permits / RESS contracts pre-build, no production yet), "
                    "'operating' (panels generating), or None (single-site or not specified).",
    )
    fit_strike_price_eur_mwh: float | None = Field(
        default=None,
        description="If under a feed-in tariff (Italian Conto Energia, French CRE/EDF OA, etc.), "
                    "the contracted €/MWh. Asset earns this regardless of wholesale price — "
                    "spot calculations should be replaced by FiT × production.",
    )
    fit_scheme: str | None = Field(
        default=None,
        description="Free-text description of the FiT scheme (e.g. 'Conto Energia II + Spalma-Incentivi 2015 -8%').",
    )
    fit_expiry_year: int | None = Field(
        default=None, ge=1980, le=2050,
        description="Year the FiT contract expires (typically COD + 20 years, or +24 with Spalma Option A).",
    )
    divested: bool = Field(
        default=False,
        description="True if Allianz no longer owns this asset. Kept in the index for historical traceability.",
    )
    divestment_note: str | None = Field(
        default=None,
        description="Free-text describing the divestment: date if known, buyer, or 'date unknown'.",
    )
    dc_ac_ratio: float = Field(default=1.30, ge=1.0, le=2.0)
    ress_strike_price_eur_mwh: float | None = Field(
        default=None,
        description="If RESS-secured (Irish auction floor), the contracted strike €/MWh. "
                    "Pricing is a 2-way CfD so cannibalisation = 0 from project perspective.",
    )

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
