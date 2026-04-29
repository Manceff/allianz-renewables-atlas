"""Phase 3 — pré-calcul exhaustif des assets par parc.

Pour chaque parc dans `data/parks_index.yaml` :
- Écrit `metadata.json` (snapshot du dict YAML)
- Tente de récupérer une image RGB Sentinel-2 (`sentinel.png`) via Copernicus Data Space
- Pour les solaires `has_pvgis_estimate` : appelle PVGIS PVcalc (`production_estimated.json`)
- Pour les solaires `has_reported_production` : si `production_reported.json` existe localement,
  calcule `delta.json` (estimée − reportée)

Échecs loggés dans `data/PRECOMPUTE_FAILURES.md` (et le script continue).

Lance avec :
    python scripts/precompute_all.py

Voir CLAUDE.md / README.md pour la stack et la doctrine R4 (sources publiques uniquement).
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

# Charge .env si python-dotenv est dispo (sinon on lit os.environ tel quel)
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.lib.compute_delta import (  # noqa: E402
    compute_production_delta,
    severity_from_relative_delta,
)
from src.lib.confidence_interval import compute_pvgis_range  # noqa: E402
from src.lib.pvgis_fetch import PvgisFetchError, fetch_pvgis_pvcalc  # noqa: E402
from src.lib.reported_production import (  # noqa: E402
    ReportedProduction,
    load_reported_production,
)
from src.lib.schemas import PortfolioSweep, PortfolioSweepEntry  # noqa: E402
from src.lib.sentinel_fetch import (  # noqa: E402
    SentinelAuthError,
    SentinelFetchError,
    fetch_sentinel_rgb,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PARKS_INDEX = ROOT / "data" / "parks_index.yaml"
PARKS_DIR = ROOT / "data" / "parks"
FAILURES_LOG = ROOT / "data" / "PRECOMPUTE_FAILURES.md"
PORTFOLIO_SWEEP_PATH = ROOT / "data" / "portfolio_sweep.json"


def _has_copernicus_creds() -> bool:
    return bool(os.getenv("COPERNICUS_USERNAME") and os.getenv("COPERNICUS_PASSWORD"))


def _load_reported_mwh(park_dir: Path) -> tuple[float | None, str | None]:
    """Lit `production_reported.json` si présent. Renvoie (mwh, source)."""
    fp = park_dir / "production_reported.json"
    if not fp.exists():
        return None, None
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
        return float(data["annual_total_mwh"]), data.get("source")
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
        logger.warning("  ⚠ production_reported.json illisible : %s", e)
        return None, None


def _process_park(
    park: dict[str, Any],
    failures: list[dict[str, str]],
    sentinel_enabled: bool,
) -> None:
    park_id = park["id"]
    park_dir = PARKS_DIR / park_id
    park_dir.mkdir(parents=True, exist_ok=True)
    lat, lon = float(park["coordinates"][0]), float(park["coordinates"][1])

    logger.info("=== %s (%s) ===", park["name"], park["technology"])

    # 1. metadata.json
    (park_dir / "metadata.json").write_text(
        json.dumps(park, indent=2, default=str, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info("  ✓ metadata.json")

    # 2. Sentinel-2 RGB
    if sentinel_enabled:
        try:
            fetch_sentinel_rgb(lat=lat, lon=lon, output_path=park_dir / "sentinel.png")
            logger.info("  ✓ sentinel.png")
        except (SentinelAuthError, SentinelFetchError) as e:
            logger.warning("  ⚠ Sentinel: %s", e)
            failures.append({"id": park_id, "step": "sentinel", "error": str(e)})
    else:
        logger.info("  ↪ sentinel skip (creds COPERNICUS_* absents)")

    # 3. PVGIS pour solaires
    estimated_mwh: float | None = None
    if park["technology"] == "solar" and park.get("has_pvgis_estimate"):
        capacity = park.get("capacity_mwp")
        if capacity in (None, 0):
            msg = "capacity_mwp manquant"
            logger.warning("  ⚠ PVGIS: %s", msg)
            failures.append({"id": park_id, "step": "pvgis", "error": msg})
        else:
            try:
                production = fetch_pvgis_pvcalc(
                    lat=lat, lon=lon, peakpower_mw=float(capacity)
                )
                (park_dir / "production_estimated.json").write_text(
                    json.dumps(production, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                # Sidecar dédié au breakdown mensuel — consommé par la page Monograph (T10).
                (park_dir / "pvgis_monthly.json").write_text(
                    json.dumps(
                        {"monthly_production_kwh": production["monthly_production_kwh"]},
                        indent=2,
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
                estimated_mwh = float(production["annual_total_mwh"])
                logger.info(
                    "  ✓ production_estimated.json + pvgis_monthly.json (%.0f MWh/an)",
                    estimated_mwh,
                )
            except (PvgisFetchError, ValueError) as e:
                logger.warning("  ⚠ PVGIS: %s", e)
                failures.append({"id": park_id, "step": "pvgis", "error": str(e)})

    # 4. Delta pour solaires avec production reportée
    if park["technology"] == "solar" and park.get("has_reported_production"):
        reported_mwh, reported_source = _load_reported_mwh(park_dir)
        if reported_mwh is None:
            logger.info("  ↪ delta skip : pas de production_reported.json")
        elif estimated_mwh is None:
            logger.info("  ↪ delta skip : pas d'estimée PVGIS")
        else:
            try:
                delta = compute_production_delta(estimated_mwh, reported_mwh)
                if reported_source:
                    delta["reported_source"] = reported_source
                (park_dir / "delta.json").write_text(
                    json.dumps(delta, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                logger.info(
                    "  ✓ delta.json severity=%s rel=%+.1f%%",
                    delta["severity"],
                    delta["relative_delta_pct"],
                )
            except ValueError as e:
                logger.warning("  ⚠ delta: %s", e)
                failures.append({"id": park_id, "step": "delta", "error": str(e)})


def _build_portfolio_sweep(
    parks: list[dict[str, Any]],
    failures: list[dict[str, str]],
    output_path: Path = PORTFOLIO_SWEEP_PATH,
) -> PortfolioSweep:
    """Construit le sweep portfolio (CI PVGIS + delta vs reported) et l'écrit en JSON.

    Inclut un parc si :
    - `technology == "solar"`,
    - `has_pvgis_estimate is True`,
    - `excluded_from_sweep` n'est pas True (défaut False),
    - `capacity_mwp` renseigné,
    - une entrée existe dans `data/reported_production.yaml`.

    Échecs PVGIS loggés dans `failures` (step="sweep") et le parc est skippé.
    """
    reported: dict[str, ReportedProduction] = load_reported_production()
    entries: list[PortfolioSweepEntry] = []

    for park in parks:
        park_id = park["id"]
        if park.get("technology") != "solar":
            continue
        if not park.get("has_pvgis_estimate"):
            continue
        if park.get("excluded_from_sweep", False):
            continue
        capacity = park.get("capacity_mwp")
        if capacity in (None, 0):
            continue
        if park_id not in reported:
            continue

        lat, lon = float(park["coordinates"][0]), float(park["coordinates"][1])
        try:
            ci = compute_pvgis_range(
                lat=lat, lon=lon, peakpower_mw=float(capacity)
            )
        except (PvgisFetchError, ValueError) as e:
            logger.warning("  ⚠ sweep PVGIS échec %s : %s", park_id, e)
            failures.append({"id": park_id, "step": "sweep", "error": str(e)})
            continue

        rep = reported[park_id]
        delta_pct = (ci.mid_mwh - rep.annual_mwh) / rep.annual_mwh * 100.0
        severity = severity_from_relative_delta(delta_pct)

        entries.append(
            PortfolioSweepEntry(
                park_id=park_id,
                capacity_mwp=float(capacity),
                confidence_interval=ci,
                reported_mwh=rep.annual_mwh,
                delta_pct=delta_pct,
                severity=severity.value,
                source_url=str(rep.source_url),
            )
        )
        logger.info(
            "  ✓ sweep %s mid=%.0f MWh reported=%.0f MWh delta=%+.1f%% severity=%s",
            park_id,
            ci.mid_mwh,
            rep.annual_mwh,
            delta_pct,
            severity.value,
        )

    sweep = PortfolioSweep(
        entries=entries,
        generated_at=datetime.now(timezone.utc),
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(sweep.model_dump_json(indent=2), encoding="utf-8")
    logger.info(
        "=== portfolio_sweep.json écrit (%d entrée(s)) ===", len(entries)
    )
    return sweep


def _write_failures_log(
    failures: list[dict[str, str]],
    total_parks: int,
    sentinel_enabled: bool,
) -> None:
    """Écrit `data/PRECOMPUTE_FAILURES.md` ou le supprime si rien à logger."""
    if not failures and sentinel_enabled:
        if FAILURES_LOG.exists():
            FAILURES_LOG.unlink()
        return

    by_step: dict[str, list[dict[str, str]]] = {}
    for f in failures:
        by_step.setdefault(f["step"], []).append(f)

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [
        "# Précompute — échecs",
        "",
        f"_Généré le {ts} sur {total_parks} parcs traités._",
        "",
    ]

    if not sentinel_enabled:
        lines += [
            "## sentinel — désactivé pour ce run",
            "",
            "Variables `COPERNICUS_USERNAME` / `COPERNICUS_PASSWORD` absentes de l'environnement ; "
            "tous les `sentinel.png` ont été skippés. Voir `.env.example` et `DEPLOY.md` "
            "(Phase 4) pour la procédure d'inscription Copernicus Data Space.",
            "",
        ]

    for step, items in sorted(by_step.items()):
        suffix = "s" if len(items) > 1 else ""
        lines.append(f"## {step} ({len(items)} échec{suffix})")
        lines.append("")
        for it in items:
            lines.append(f"- **{it['id']}** — {it['error']}")
        lines.append("")

    FAILURES_LOG.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    logger.info("Chargement %s", PARKS_INDEX)
    if not PARKS_INDEX.exists():
        logger.error("Fichier non trouvé : %s", PARKS_INDEX)
        return

    with open(PARKS_INDEX, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    parks: list[dict[str, Any]] = data.get("parks", [])
    sentinel_enabled = _has_copernicus_creds()
    logger.info(
        "%d parcs à traiter — Sentinel %s",
        len(parks),
        "ACTIF" if sentinel_enabled else "désactivé (creds absents)",
    )

    failures: list[dict[str, str]] = []
    for park in parks:
        try:
            _process_park(park, failures, sentinel_enabled)
        except Exception as e:  # safety net : on continue malgré tout
            logger.exception("  ✗ Erreur fatale sur %s", park.get("id"))
            failures.append(
                {"id": str(park.get("id", "?")), "step": "fatal", "error": repr(e)}
            )

    try:
        _build_portfolio_sweep(parks, failures)
    except Exception as e:  # safety net : on continue malgré tout
        logger.exception("  ✗ Erreur fatale sur portfolio_sweep")
        failures.append({"id": "-", "step": "sweep", "error": repr(e)})

    _write_failures_log(failures, total_parks=len(parks), sentinel_enabled=sentinel_enabled)
    logger.info(
        "=== Précompute terminé : %d échec(s) sur %d parcs ===",
        len(failures),
        len(parks),
    )


if __name__ == "__main__":
    main()
