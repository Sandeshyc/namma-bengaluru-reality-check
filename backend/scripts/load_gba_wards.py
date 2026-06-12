"""
One-shot loader: copy GBA ward polygons from
data/processed/wards_master.geojson into the PostGIS `gba_wards` table via
the `insert_gba_ward` RPC (see database/migrations/004_dedup_and_loader.sql).

This is what closes cursorrules section 1: after running this once, ward
containment lookups stop happening in Python memory and start happening as
indexed PostGIS ST_Contains() queries inside Supabase.

Idempotent: truncates the table at the start, so re-running after an updated
GeoJSON is safe. (gba_wards has no foreign keys pointing into it.)

Usage:
    cd backend
    python -m scripts.load_gba_wards

    # or with a custom GeoJSON path:
    python -m scripts.load_gba_wards path/to/wards.geojson

Requires SUPABASE_URL and SUPABASE_SERVICE_KEY in the .env file at the repo root.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict

from dotenv import load_dotenv

# Resolve repo paths from this file's location so it works regardless of cwd.
SCRIPT_DIR = Path(__file__).resolve().parent      # backend/scripts
BACKEND_DIR = SCRIPT_DIR.parent                   # backend
REPO_ROOT = BACKEND_DIR.parent                    # repo root
DEFAULT_GEOJSON = REPO_ROOT / "data" / "processed" / "wards_master.geojson"

load_dotenv(REPO_ROOT / ".env", override=True)

# Add backend/ to sys.path so `from app.services...` resolves when this script
# is invoked directly (vs. as a module).
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.supabase_client import get_supabase  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("load_gba_wards")


def _extract_props(properties: Dict[str, Any], feature_index: int) -> Dict[str, Any]:
    """Pull the four columns we care about, with friendly fallbacks."""
    return {
        "ward_name": (
            properties.get("ward_name")
            or properties.get("WARD_NAME")
            or properties.get("name")
            or f"ward_{feature_index}"
        ),
        "gba_corporation": (
            properties.get("gba_corporation") or properties.get("corporation")
        ),
        "cauvery_stage": properties.get("cauvery_stage"),
        "groundwater_risk": (
            properties.get("groundwater_risk") or properties.get("water_risk")
        ),
    }


def main(geojson_path: Path) -> int:
    if not geojson_path.exists():
        log.error("GeoJSON not found at %s", geojson_path)
        return 1

    client = get_supabase()
    if client is None:
        log.error(
            "Supabase client not configured. "
            "Set SUPABASE_URL and SUPABASE_SERVICE_KEY in .env."
        )
        return 1

    log.info("Reading %s", geojson_path)
    with open(geojson_path, "r", encoding="utf-8") as f:
        feature_collection = json.load(f)

    features = feature_collection.get("features", [])
    if not features:
        log.error("GeoJSON has no features.")
        return 1
    log.info("Found %d ward features.", len(features))

    log.info("Truncating gba_wards (clean re-load)...")
    try:
        client.rpc("truncate_gba_wards", {}).execute()
    except Exception as e:
        log.error("truncate_gba_wards failed (is migration 004 applied?): %s", e)
        return 2

    inserted = 0
    skipped = 0
    for i, feat in enumerate(features, start=1):
        geom = feat.get("geometry")
        if not geom:
            skipped += 1
            continue

        props = _extract_props(feat.get("properties", {}) or {}, i)
        try:
            client.rpc(
                "insert_gba_ward",
                {
                    "p_ward_name": props["ward_name"],
                    "p_gba_corporation": props["gba_corporation"],
                    "p_cauvery_stage": props["cauvery_stage"],
                    "p_groundwater_risk": props["groundwater_risk"],
                    "p_geojson": json.dumps(geom),
                },
            ).execute()
            inserted += 1
        except Exception as e:
            log.warning("Skipping feature #%d (%s): %s", i, props["ward_name"], e)
            skipped += 1

        if i % 25 == 0:
            log.info("  ...processed %d/%d", i, len(features))

    log.info("Done. Inserted=%d  Skipped=%d", inserted, skipped)

    if inserted == 0:
        log.error("No rows inserted — table is empty and lookups will fall back to shapely.")
        return 3
    return 0


if __name__ == "__main__":
    path = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_GEOJSON
    sys.exit(main(path))
