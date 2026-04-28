"""Tests pour src.lib.sentinel_fetch — Copernicus Data Space Ecosystem.

Mocks l'OAuth2 + Process API ; aucun appel réseau réel.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.lib.sentinel_fetch import (
    SentinelAuthError,
    SentinelFetchError,
    _build_bbox,
    _get_access_token,
    fetch_sentinel_rgb,
)

# 8-byte PNG signature suffit pour qu'un test "byte content écrit" passe.
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def _mock_token_response() -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"access_token": "FAKE_TOKEN_XYZ", "expires_in": 3600}
    resp.raise_for_status.return_value = None
    return resp


def _mock_process_response(content: bytes = PNG_BYTES, status: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.content = content
    if status >= 400:
        from requests import HTTPError

        resp.raise_for_status.side_effect = HTTPError(f"{status} error")
    else:
        resp.raise_for_status.return_value = None
    return resp


# ---------- _build_bbox ----------


def test_build_bbox_returns_minlon_minlat_maxlon_maxlat() -> None:
    bbox = _build_bbox(lat=40.0, lon=10.0, size_km=5.0)
    assert len(bbox) == 4
    min_lon, min_lat, max_lon, max_lat = bbox
    assert min_lon < 10.0 < max_lon
    assert min_lat < 40.0 < max_lat


def test_build_bbox_respects_size() -> None:
    """À ~40° de latitude, 5 km ≈ 0.045° lat, donc ~0.09° de span total."""
    bbox = _build_bbox(lat=40.0, lon=10.0, size_km=5.0)
    lat_span = bbox[3] - bbox[1]
    assert 0.04 < lat_span < 0.12


# ---------- _get_access_token ----------


@patch("src.lib.sentinel_fetch.requests.post")
def test_get_access_token_returns_token(mock_post: MagicMock) -> None:
    mock_post.return_value = _mock_token_response()

    token = _get_access_token(username="user", password="pwd")

    assert token == "FAKE_TOKEN_XYZ"
    assert mock_post.call_count == 1


@patch("src.lib.sentinel_fetch.requests.post")
def test_get_access_token_sends_password_grant(mock_post: MagicMock) -> None:
    mock_post.return_value = _mock_token_response()

    _get_access_token(username="u", password="p")

    data = mock_post.call_args.kwargs.get("data") or {}
    assert data["grant_type"] == "password"
    assert data["username"] == "u"
    assert data["password"] == "p"
    assert "client_id" in data


@patch("src.lib.sentinel_fetch.requests.post")
def test_get_access_token_http_error_raises(mock_post: MagicMock) -> None:
    err_resp = MagicMock()
    err_resp.status_code = 401
    from requests import HTTPError

    err_resp.raise_for_status.side_effect = HTTPError("401")
    mock_post.return_value = err_resp

    with pytest.raises(SentinelAuthError):
        _get_access_token(username="u", password="p")


# ---------- fetch_sentinel_rgb ----------


@patch("src.lib.sentinel_fetch.requests.post")
def test_fetch_sentinel_rgb_writes_png(mock_post: MagicMock, tmp_path: Path) -> None:
    """1er post = token, 2e post = process API."""
    mock_post.side_effect = [_mock_token_response(), _mock_process_response()]

    out = tmp_path / "park" / "sentinel.png"
    result = fetch_sentinel_rgb(
        lat=40.0,
        lon=10.0,
        output_path=out,
        username="u",
        password="p",
    )

    assert result == out
    assert out.exists()
    assert out.read_bytes().startswith(b"\x89PNG")


@patch("src.lib.sentinel_fetch.requests.post")
def test_fetch_sentinel_rgb_uses_bearer_token(mock_post: MagicMock, tmp_path: Path) -> None:
    mock_post.side_effect = [_mock_token_response(), _mock_process_response()]

    fetch_sentinel_rgb(
        lat=40.0,
        lon=10.0,
        output_path=tmp_path / "x.png",
        username="u",
        password="p",
    )

    process_call = mock_post.call_args_list[1]
    headers = process_call.kwargs.get("headers") or {}
    assert headers.get("Authorization") == "Bearer FAKE_TOKEN_XYZ"


@patch("src.lib.sentinel_fetch.requests.post")
def test_fetch_sentinel_rgb_passes_cloud_cover(mock_post: MagicMock, tmp_path: Path) -> None:
    mock_post.side_effect = [_mock_token_response(), _mock_process_response()]

    fetch_sentinel_rgb(
        lat=40.0,
        lon=10.0,
        output_path=tmp_path / "x.png",
        username="u",
        password="p",
        max_cloud_cover_pct=15.0,
    )

    body = mock_post.call_args_list[1].kwargs.get("json") or {}
    data_sources = body.get("input", {}).get("data", [])
    assert data_sources, "Process body must contain input.data"
    cloud = data_sources[0].get("dataFilter", {}).get("maxCloudCoverage")
    assert cloud == 15.0


@patch("src.lib.sentinel_fetch.requests.post")
def test_fetch_sentinel_rgb_creates_parent_dir(mock_post: MagicMock, tmp_path: Path) -> None:
    mock_post.side_effect = [_mock_token_response(), _mock_process_response()]

    nested = tmp_path / "deeply" / "nested" / "out.png"
    fetch_sentinel_rgb(
        lat=0.0,
        lon=0.0,
        output_path=nested,
        username="u",
        password="p",
    )
    assert nested.exists()


@patch("src.lib.sentinel_fetch.requests.post")
def test_fetch_sentinel_rgb_process_http_error_raises(mock_post: MagicMock, tmp_path: Path) -> None:
    mock_post.side_effect = [
        _mock_token_response(),
        _mock_process_response(content=b"", status=502),
    ]

    with pytest.raises(SentinelFetchError):
        fetch_sentinel_rgb(
            lat=0.0,
            lon=0.0,
            output_path=tmp_path / "x.png",
            username="u",
            password="p",
        )


def test_fetch_sentinel_rgb_missing_credentials_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pas de creds dans args ni env → SentinelAuthError clair."""
    monkeypatch.delenv("COPERNICUS_USERNAME", raising=False)
    monkeypatch.delenv("COPERNICUS_PASSWORD", raising=False)

    with pytest.raises(SentinelAuthError):
        fetch_sentinel_rgb(lat=0.0, lon=0.0, output_path=tmp_path / "x.png")


@patch("src.lib.sentinel_fetch.requests.post")
def test_fetch_sentinel_rgb_credentials_from_env(
    mock_post: MagicMock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("COPERNICUS_USERNAME", "env_user")
    monkeypatch.setenv("COPERNICUS_PASSWORD", "env_pwd")
    mock_post.side_effect = [_mock_token_response(), _mock_process_response()]

    fetch_sentinel_rgb(lat=0.0, lon=0.0, output_path=tmp_path / "x.png")

    token_call = mock_post.call_args_list[0]
    data = token_call.kwargs.get("data") or {}
    assert data["username"] == "env_user"
    assert data["password"] == "env_pwd"
