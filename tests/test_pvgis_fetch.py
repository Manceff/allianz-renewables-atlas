"""Tests pour src.lib.pvgis_fetch — PVGIS PVcalc API du JRC EU.

Mocks `requests.get` ; aucun réseau réel.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.lib.pvgis_fetch import (
    PVGIS_PVCALC_URL,
    PvgisFetchError,
    fetch_pvgis_pvcalc,
)


def _fake_pvcalc_response() -> dict:
    """Réponse PVcalc factice — 12 mois + totals fixed."""
    return {
        "inputs": {
            "location": {"latitude": 37.65, "longitude": -8.22, "elevation": 100.0},
            "meteo_data": {"radiation_db": "PVGIS-SARAH2", "year_min": 2005, "year_max": 2020},
            "mounting_system": {"fixed": {"slope": {"value": 27.0}, "azimuth": {"value": 0.0}}},
            "pv_module": {"technology": "c-Si", "peak_power": 46000.0, "system_loss": 14.0},
        },
        "outputs": {
            "monthly": {
                "fixed": [
                    {"month": m, "E_d": 100.0 + m, "E_m": (100.0 + m) * 30, "H(i)_d": 5.0, "H(i)_m": 150.0, "SD_m": 10.0}
                    for m in range(1, 13)
                ]
            },
            "totals": {
                "fixed": {
                    "E_d": 110.0,
                    "E_m": 3300.0,
                    "E_y": 39600.0,
                    "H(i)_d": 5.0,
                    "H(i)_m": 150.0,
                    "H(i)_y": 1800.0,
                    "SD_m": 10.0,
                    "SD_y": 100.0,
                    "l_aoi": -2.0,
                    "l_spec": 0.5,
                    "l_tg": -3.0,
                    "l_total": -14.0,
                }
            },
        },
        "meta": {"inputs": {}, "outputs": {}},
    }


def _make_mock_response(payload: dict, status: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = payload
    if status >= 400:
        from requests import HTTPError

        resp.raise_for_status.side_effect = HTTPError(f"{status} error")
    else:
        resp.raise_for_status.return_value = None
    return resp


@patch("src.lib.pvgis_fetch.requests.get")
def test_fetch_pvgis_returns_expected_keys(mock_get: MagicMock) -> None:
    mock_get.return_value = _make_mock_response(_fake_pvcalc_response())

    out = fetch_pvgis_pvcalc(lat=37.65, lon=-8.22, peakpower_mw=46.0)

    assert set(out.keys()) >= {
        "inputs",
        "monthly_production_kwh",
        "annual_total_kwh",
        "annual_total_mwh",
        "metadata",
    }
    assert len(out["monthly_production_kwh"]) == 12
    assert out["annual_total_kwh"] == 39600.0
    assert out["annual_total_mwh"] == pytest.approx(39.6)


@patch("src.lib.pvgis_fetch.requests.get")
def test_fetch_pvgis_converts_mw_to_kw(mock_get: MagicMock) -> None:
    """peakpower est passé en kWp à PVGIS (× 1000)."""
    mock_get.return_value = _make_mock_response(_fake_pvcalc_response())

    fetch_pvgis_pvcalc(lat=37.65, lon=-8.22, peakpower_mw=46.0)

    assert mock_get.call_count == 1
    params = mock_get.call_args.kwargs.get("params") or mock_get.call_args.args[1]
    assert params["peakpower"] == 46000.0  # 46 MW → 46 000 kWp
    assert params["outputformat"] == "json"


@patch("src.lib.pvgis_fetch.requests.get")
def test_fetch_pvgis_default_tilt_lat_minus_10(mock_get: MagicMock) -> None:
    mock_get.return_value = _make_mock_response(_fake_pvcalc_response())

    fetch_pvgis_pvcalc(lat=40.0, lon=0.0, peakpower_mw=10.0)

    params = mock_get.call_args.kwargs.get("params") or mock_get.call_args.args[1]
    assert params["angle"] == pytest.approx(30.0)  # 40 - 10


@patch("src.lib.pvgis_fetch.requests.get")
def test_fetch_pvgis_default_azimuth_zero(mock_get: MagicMock) -> None:
    mock_get.return_value = _make_mock_response(_fake_pvcalc_response())

    fetch_pvgis_pvcalc(lat=40.0, lon=0.0, peakpower_mw=10.0)

    params = mock_get.call_args.kwargs.get("params") or mock_get.call_args.args[1]
    assert params["aspect"] == 0.0


@patch("src.lib.pvgis_fetch.requests.get")
def test_fetch_pvgis_explicit_tilt_and_azimuth(mock_get: MagicMock) -> None:
    mock_get.return_value = _make_mock_response(_fake_pvcalc_response())

    fetch_pvgis_pvcalc(lat=40.0, lon=0.0, peakpower_mw=10.0, tilt=25.0, azimuth=15.0)

    params = mock_get.call_args.kwargs.get("params") or mock_get.call_args.args[1]
    assert params["angle"] == 25.0
    assert params["aspect"] == 15.0


@patch("src.lib.pvgis_fetch.requests.get")
def test_fetch_pvgis_uses_correct_url(mock_get: MagicMock) -> None:
    mock_get.return_value = _make_mock_response(_fake_pvcalc_response())

    fetch_pvgis_pvcalc(lat=0.0, lon=0.0, peakpower_mw=1.0)

    url = mock_get.call_args.args[0] if mock_get.call_args.args else mock_get.call_args.kwargs["url"]
    assert url == PVGIS_PVCALC_URL


@patch("src.lib.pvgis_fetch.requests.get")
def test_fetch_pvgis_http_error_raises_pvgisfetcherror(mock_get: MagicMock) -> None:
    mock_get.return_value = _make_mock_response({}, status=500)

    with pytest.raises(PvgisFetchError):
        fetch_pvgis_pvcalc(lat=0.0, lon=0.0, peakpower_mw=1.0)


@patch("src.lib.pvgis_fetch.requests.get")
def test_fetch_pvgis_malformed_payload_raises(mock_get: MagicMock) -> None:
    """Payload sans `outputs.monthly.fixed` → erreur claire."""
    mock_get.return_value = _make_mock_response({"foo": "bar"})

    with pytest.raises(PvgisFetchError):
        fetch_pvgis_pvcalc(lat=0.0, lon=0.0, peakpower_mw=1.0)


@patch("src.lib.pvgis_fetch.requests.get")
def test_fetch_pvgis_metadata_exposed(mock_get: MagicMock) -> None:
    mock_get.return_value = _make_mock_response(_fake_pvcalc_response())

    out = fetch_pvgis_pvcalc(lat=37.65, lon=-8.22, peakpower_mw=46.0)

    assert out["metadata"]["raddatabase"] == "PVGIS-SARAH2"
    assert out["metadata"]["year_min"] == 2005
    assert out["metadata"]["year_max"] == 2020


def test_fetch_pvgis_invalid_peakpower_raises() -> None:
    """peakpower_mw <= 0 → ValueError immédiat (pas d'appel HTTP)."""
    with pytest.raises(ValueError):
        fetch_pvgis_pvcalc(lat=0.0, lon=0.0, peakpower_mw=0.0)
