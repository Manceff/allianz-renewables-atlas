"""Tests du loader reported_production."""

from __future__ import annotations

from pathlib import Path

import yaml

from src.lib.reported_production import ReportedProduction, load_reported_production


def test_load_yaml_returns_dict():
    data = load_reported_production()
    assert isinstance(data, dict)
    assert len(data) >= 4


def test_each_entry_has_source_url():
    data = load_reported_production()
    for park_id, prod in data.items():
        assert prod.source_url is not None
        assert prod.annual_mwh > 0


def test_park_ids_match_known_parks():
    """Les park_id references doivent exister dans parks_index.yaml."""
    parks_yaml = Path(__file__).parent.parent / "data" / "parks_index.yaml"
    with open(parks_yaml, encoding="utf-8") as f:
        index = yaml.safe_load(f)
    known_ids = {p["id"] for p in index["parks"]}
    data = load_reported_production()
    for park_id in data:
        assert park_id in known_ids, f"{park_id} not in parks_index.yaml"
