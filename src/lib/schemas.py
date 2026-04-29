"""Schémas Pydantic v2 — contrat des fichiers JSON `data/parks/<id>/*.json`.

GitNexus a flagué que le couplage réel entre `src/lib/*` et les pages Streamlit
passe par les fichiers JSON sur disque, invisibles au call-graph. Ce module
formalise ce contrat sans imposer leur usage à tous les producteurs (additif).

Schémas existants (validés contre les fichiers en place) :
- `ParkMetadata` ← `metadata.json`
- `PVGISOutput` ← `production_estimated.json`
- `ProductionReported` ← `production_reported.json`
- `DeltaOutput` ← `delta.json`

Schémas forward-looking (T-suivants) :
- `LossScenario`, `ConfidenceInterval`
- `PortfolioSweepEntry`, `PortfolioSweep`
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

__all__ = [
    "ParkMetadata",
    "PVGISInputs",
    "PVGISMetadata",
    "PVGISOutput",
    "ProductionReported",
    "DeltaOutput",
    "LossScenario",
    "ConfidenceInterval",
    "PortfolioSweepEntry",
    "PortfolioSweep",
    "Severity",
]


Severity = Literal["green", "yellow", "red", "unknown"]


# ---------------------------------------------------------------------------
# metadata.json
# ---------------------------------------------------------------------------


class ParkMetadata(BaseModel):
    """Metadata d'un parc — `data/parks/<id>/metadata.json`.

    Miroir du `ParkModel` de `parks_loader.py` mais en `extra="allow"` pour
    rester additif si des champs sont ajoutés sans bumper le schéma.
    """

    model_config = ConfigDict(extra="allow")

    id: str = Field(..., min_length=1, description="Slug stable du parc")
    name: str = Field(..., min_length=1)
    country: str = Field(..., min_length=2, description="Code ISO-3166 alpha-2")
    technology: Literal["solar", "onshore_wind", "offshore_wind", "battery_storage"]
    coordinates: tuple[float, float] = Field(..., description="[lat, lon] en degrés")
    capacity_mwp: Optional[float] = Field(default=None, ge=0)
    commissioning_year: int = Field(..., ge=1980, le=2050)
    operator: Optional[str] = None
    allianz_stake_pct: Optional[float] = Field(default=None, ge=0, le=100)
    acquisition_year: Optional[int] = Field(default=None, ge=1980, le=2050)
    press_release_url: str = Field(..., min_length=1)
    notes: Optional[str] = None
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


# ---------------------------------------------------------------------------
# production_estimated.json (PVGIS PVcalc)
# ---------------------------------------------------------------------------


class PVGISInputs(BaseModel):
    """Paramètres effectifs envoyés à PVGIS PVcalc."""

    model_config = ConfigDict(extra="allow")

    lat: float
    lon: float
    peakpower_kw: float = Field(..., ge=0)
    tilt_deg: float
    azimuth_deg: float
    loss_pct: float
    pv_technology: str


class PVGISMetadata(BaseModel):
    """Bloc metadata PVGIS (source + fenêtre années radiation)."""

    model_config = ConfigDict(extra="allow")

    source: str
    raddatabase: Optional[str] = None
    year_min: Optional[int] = None
    year_max: Optional[int] = None


class PVGISOutput(BaseModel):
    """Sortie PVGIS sérialisée — `data/parks/<id>/production_estimated.json`.

    Note: `raw_totals_fixed` reste en `dict` libre car PVGIS renvoie parfois des
    valeurs typées variables (ex. `l_spec` est tantôt un float tantôt une string
    `"?(0)"` quand la donnée n'est pas disponible).
    """

    model_config = ConfigDict(extra="allow")

    inputs: PVGISInputs
    monthly_production_kwh: list[float] = Field(..., min_length=12, max_length=12)
    annual_total_kwh: float = Field(..., ge=0)
    annual_total_mwh: float = Field(..., ge=0)
    metadata: PVGISMetadata
    raw_totals_fixed: Optional[dict] = None


# ---------------------------------------------------------------------------
# production_reported.json (seed manuel doctrine R4)
# ---------------------------------------------------------------------------


class ProductionReported(BaseModel):
    """Production publiée par l'opérateur — seed manuel.

    Schéma déduit de `data/parks/ourika/production_reported.json` (seul existant
    aujourd'hui). Tous les champs documentaires sont optionnels pour rester
    accommodant si un futur producteur omet la note ou la méthode.
    """

    model_config = ConfigDict(extra="allow")

    park_id: str = Field(..., min_length=1)
    annual_total_mwh: float = Field(..., ge=0)
    year: Optional[int] = Field(default=None, ge=1980, le=2050)
    source: Optional[str] = None
    url: Optional[str] = None
    method: Optional[str] = None
    note: Optional[str] = None


# ---------------------------------------------------------------------------
# delta.json
# ---------------------------------------------------------------------------


class DeltaOutput(BaseModel):
    """Comparaison estimée vs publiée — `data/parks/<id>/delta.json`."""

    model_config = ConfigDict(extra="allow")

    estimated_annual_mwh: float = Field(..., ge=0)
    reported_annual_mwh: float = Field(..., ge=0)
    absolute_delta_mwh: float
    relative_delta_pct: float
    severity: Literal["green", "yellow", "red"]
    interpretation: str
    reported_source: Optional[str] = None


# ---------------------------------------------------------------------------
# Forward-looking — Confidence intervals (multi-loss sweep PVGIS)
# ---------------------------------------------------------------------------


class LossScenario(BaseModel):
    """Un scénario PVGIS à un `loss_pct` donné."""

    model_config = ConfigDict(extra="forbid")

    loss_pct: float = Field(..., description="Pertes système % envoyées à PVGIS")
    annual_kwh: float = Field(..., ge=0, description="Production annuelle correspondante (kWh)")


class ConfidenceInterval(BaseModel):
    """Encadrement low / mid / high de la production annuelle (MWh)."""

    model_config = ConfigDict(extra="forbid")

    low_mwh: float = Field(..., ge=0)
    mid_mwh: float = Field(..., ge=0)
    high_mwh: float = Field(..., ge=0)
    scenarios: list[LossScenario] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Forward-looking — Portfolio sweep
# ---------------------------------------------------------------------------


class PortfolioSweepEntry(BaseModel):
    """Une ligne du sweep portfolio par parc."""

    model_config = ConfigDict(extra="forbid")

    park_id: str = Field(..., min_length=1)
    capacity_mwp: Optional[float] = Field(default=None, ge=0)
    confidence_interval: ConfidenceInterval
    reported_mwh: Optional[float] = Field(default=None, ge=0)
    delta_pct: Optional[float] = None
    severity: Severity = "unknown"
    source_url: Optional[HttpUrl] = None


class PortfolioSweep(BaseModel):
    """Snapshot complet du sweep portfolio (tous parcs)."""

    model_config = ConfigDict(extra="forbid")

    entries: list[PortfolioSweepEntry] = Field(default_factory=list)
    generated_at: datetime
