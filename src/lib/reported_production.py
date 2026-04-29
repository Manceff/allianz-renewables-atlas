"""Loader pour data/reported_production.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field, HttpUrl


class ReportedProduction(BaseModel):
    """Production annuelle reportee publiquement pour un parc."""

    park_id: str
    annual_mwh: float = Field(gt=0)
    year: int = Field(ge=2008, le=2030)
    source_url: HttpUrl
    note: Optional[str] = None


DEFAULT_PATH = (
    Path(__file__).resolve().parent.parent.parent / "data" / "reported_production.yaml"
)


def load_reported_production(
    path: Path = DEFAULT_PATH,
) -> dict[str, ReportedProduction]:
    """Charge le YAML et retourne un dict park_id -> ReportedProduction."""
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or []
    return {entry["park_id"]: ReportedProduction(**entry) for entry in raw}
