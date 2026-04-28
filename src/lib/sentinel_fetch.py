"""Client Sentinel-2 RGB via Copernicus Data Space Ecosystem (Sentinel Hub Process API).

Auth : OAuth2 password grant (Keycloak CDSE).
Process API : POST PNG RGB true-color, plus récente passe avec cloud cover < seuil.

Variables d'environnement attendues :
- COPERNICUS_USERNAME
- COPERNICUS_PASSWORD
"""

from __future__ import annotations

import logging
import math
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

CDSE_TOKEN_URL = (
    "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
)
CDSE_PROCESS_URL = "https://sh.dataspace.copernicus.eu/api/v1/process"
CDSE_TOKEN_CLIENT_ID = "cdse-public"

DEFAULT_BBOX_KM = 5.0
DEFAULT_WIDTH_PX = 512
DEFAULT_HEIGHT_PX = 512
DEFAULT_CLOUD_PCT = 20.0
DEFAULT_TIME_WINDOW_DAYS = 90
DEFAULT_TIMEOUT_SEC = 60

# Évalscript Sentinel Hub : true color RGB (B04/B03/B02) avec gain 2.5.
EVALSCRIPT_TRUE_COLOR = """
//VERSION=3
function setup() {
  return {
    input: ["B02", "B03", "B04"],
    output: { bands: 3, sampleType: "AUTO" }
  };
}
function evaluatePixel(s) {
  return [2.5 * s.B04, 2.5 * s.B03, 2.5 * s.B02];
}
""".strip()


class SentinelAuthError(RuntimeError):
    """Échec d'authentification Copernicus."""


class SentinelFetchError(RuntimeError):
    """Échec d'appel Process API ou écriture PNG."""


def _build_bbox(lat: float, lon: float, size_km: float) -> tuple[float, float, float, float]:
    """Renvoie [min_lon, min_lat, max_lon, max_lat] centré sur (lat, lon).

    1° latitude ≈ 111 km. Longitude scale par cos(lat).
    """
    half_lat_deg = (size_km / 2.0) / 111.0
    cos_lat = max(math.cos(math.radians(lat)), 1e-6)
    half_lon_deg = (size_km / 2.0) / (111.0 * cos_lat)
    return (lon - half_lon_deg, lat - half_lat_deg, lon + half_lon_deg, lat + half_lat_deg)


def _get_access_token(
    username: str, password: str, timeout: int = DEFAULT_TIMEOUT_SEC
) -> str:
    """Récupère un access_token OAuth2 via le grant `password` Keycloak CDSE."""
    data = {
        "grant_type": "password",
        "username": username,
        "password": password,
        "client_id": CDSE_TOKEN_CLIENT_ID,
    }
    try:
        resp = requests.post(CDSE_TOKEN_URL, data=data, timeout=timeout)
        resp.raise_for_status()
    except requests.RequestException as e:
        raise SentinelAuthError(f"Copernicus auth HTTP error: {e}") from e

    try:
        token = resp.json()["access_token"]
    except (KeyError, ValueError) as e:
        raise SentinelAuthError(f"Copernicus auth payload invalide: {e}") from e

    return token


def _build_process_body(
    bbox: tuple[float, float, float, float],
    time_from: str,
    time_to: str,
    max_cloud_cover_pct: float,
    width_px: int,
    height_px: int,
) -> dict:
    return {
        "input": {
            "bounds": {
                "bbox": list(bbox),
                "properties": {"crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84"},
            },
            "data": [
                {
                    "type": "sentinel-2-l2a",
                    "dataFilter": {
                        "timeRange": {"from": time_from, "to": time_to},
                        "maxCloudCoverage": max_cloud_cover_pct,
                        "mosaickingOrder": "leastRecent",
                    },
                }
            ],
        },
        "output": {
            "width": width_px,
            "height": height_px,
            "responses": [{"identifier": "default", "format": {"type": "image/png"}}],
        },
        "evalscript": EVALSCRIPT_TRUE_COLOR,
    }


def fetch_sentinel_rgb(
    lat: float,
    lon: float,
    output_path: Path,
    bbox_size_km: float = DEFAULT_BBOX_KM,
    max_cloud_cover_pct: float = DEFAULT_CLOUD_PCT,
    width_px: int = DEFAULT_WIDTH_PX,
    height_px: int = DEFAULT_HEIGHT_PX,
    time_window_days: int = DEFAULT_TIME_WINDOW_DAYS,
    username: str | None = None,
    password: str | None = None,
    timeout: int = DEFAULT_TIMEOUT_SEC,
) -> Path:
    """Télécharge un PNG RGB Sentinel-2 récent autour de (lat, lon).

    Args:
        output_path: chemin de sortie ; les parents sont créés.
        bbox_size_km: taille de la bbox en km (carré centré).
        max_cloud_cover_pct: filtre cloud cover maximum (%).
        time_window_days: profondeur de recherche (j) avant aujourd'hui.
        username, password: creds Copernicus ; sinon `COPERNICUS_USERNAME` / `COPERNICUS_PASSWORD`.

    Returns:
        Le `Path` du PNG écrit.

    Raises:
        SentinelAuthError: creds manquants ou rejetés.
        SentinelFetchError: erreur Process API ou écriture.
    """
    user = username or os.getenv("COPERNICUS_USERNAME")
    pwd = password or os.getenv("COPERNICUS_PASSWORD")
    if not user or not pwd:
        raise SentinelAuthError(
            "Credentials Copernicus manquants : COPERNICUS_USERNAME / COPERNICUS_PASSWORD"
        )

    token = _get_access_token(user, pwd, timeout=timeout)

    now = datetime.now(timezone.utc)
    time_from = (now - timedelta(days=time_window_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    time_to = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    bbox = _build_bbox(lat, lon, bbox_size_km)
    body = _build_process_body(
        bbox=bbox,
        time_from=time_from,
        time_to=time_to,
        max_cloud_cover_pct=max_cloud_cover_pct,
        width_px=width_px,
        height_px=height_px,
    )

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "image/png",
        "Content-Type": "application/json",
    }

    logger.info(
        "Sentinel Process lat=%.4f lon=%.4f bbox=%.1fkm cloud<%.0f%% window=%dd",
        lat,
        lon,
        bbox_size_km,
        max_cloud_cover_pct,
        time_window_days,
    )

    try:
        resp = requests.post(CDSE_PROCESS_URL, json=body, headers=headers, timeout=timeout)
        resp.raise_for_status()
    except requests.RequestException as e:
        raise SentinelFetchError(f"Sentinel Process HTTP error: {e}") from e

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(resp.content)
    logger.info("Sentinel PNG écrit : %s (%d bytes)", output_path, len(resp.content))
    return output_path
