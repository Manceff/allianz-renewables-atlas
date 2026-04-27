"""Script one-shot pour pré-calculer toutes les données par parc.

À exécuter en local en dev. Pour chaque parc dans data/parks_index.yaml :
- Fetch Sentinel-2 RGB image via Copernicus Data Space (sauve PNG)
- Pour les solaires : fetch PVGIS PVcalc (sauve JSON production estimée)
- Pour les solaires avec production publiée : sauve production_reported.json (manuel ou semi-auto)
- Calcule delta.json pour les solaires

Lance avec :
    python scripts/precompute_all.py

Voir CLAUDE.md pour les conventions et README pour la vision.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import yaml

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# TODO: implémenter dans Phase 2 (Claude Code agents)
#
# from src.lib.sentinel_fetch import fetch_sentinel_rgb
# from src.lib.pvgis_fetch import fetch_pvgis_pvcalc
# from src.lib.compute_delta import compute_production_delta

PARKS_INDEX = Path(__file__).resolve().parent.parent / "data" / "parks_index.yaml"
PARKS_DIR = Path(__file__).resolve().parent.parent / "data" / "parks"


def main() -> None:
    """Boucle sur tous les parcs et lance les pré-calculs."""
    logger.info("Chargement de %s", PARKS_INDEX)
    if not PARKS_INDEX.exists():
        logger.error("Fichier non trouvé : %s", PARKS_INDEX)
        return

    with open(PARKS_INDEX) as f:
        data = yaml.safe_load(f)

    parks = data.get("parks", [])
    logger.info("%d parcs à traiter", len(parks))

    for park in parks:
        park_id = park["id"]
        park_dir = PARKS_DIR / park_id
        park_dir.mkdir(parents=True, exist_ok=True)

        logger.info("=== Traitement de %s (%s) ===", park["name"], park["technology"])

        # 1. Sauver les metadata
        with open(park_dir / "metadata.json", "w") as f:
            json.dump(park, f, indent=2, default=str)
        logger.info("  ✓ metadata.json sauvegardé")

        # 2. TODO: Fetch Sentinel-2 RGB
        # try:
        #     fetch_sentinel_rgb(
        #         lat=park["coordinates"][0],
        #         lon=park["coordinates"][1],
        #         output_path=park_dir / "sentinel.png",
        #     )
        #     logger.info("  ✓ sentinel.png fetched")
        # except Exception as e:
        #     logger.warning("  ⚠ Sentinel fetch failed: %s", e)
        logger.info("  [TODO] sentinel.png — implémenter src/lib/sentinel_fetch.py")

        # 3. TODO: Pour solaires, fetch PVGIS
        if park["technology"] == "solar" and park.get("has_pvgis_estimate"):
            # try:
            #     production = fetch_pvgis_pvcalc(
            #         lat=park["coordinates"][0],
            #         lon=park["coordinates"][1],
            #         peakpower_mw=park["capacity_mwp"],
            #     )
            #     with open(park_dir / "production_estimated.json", "w") as f:
            #         json.dump(production, f, indent=2)
            #     logger.info("  ✓ production_estimated.json (PVGIS)")
            # except Exception as e:
            #     logger.warning("  ⚠ PVGIS fetch failed: %s", e)
            logger.info("  [TODO] production_estimated.json — implémenter src/lib/pvgis_fetch.py")

        # 4. TODO: Pour solaires avec production publiée, calculer delta
        # if park["technology"] == "solar" and park.get("has_reported_production"):
        #     compute_production_delta(park_dir)
        #     logger.info("  ✓ delta.json calculé")

    logger.info("=== Précompute terminé ===")


if __name__ == "__main__":
    main()
