"""
Ward spatial lookup.

Primary path: PostGIS ST_Contains via Supabase RPC `lookup_gba_ward(lat, lng)`
(see database/migrations/002_gba_wards.sql). This is the cursorrules section 1
mandate: spatial joins live in Postgres, not in Python memory.

Fallback path: in-memory shapely scan over the bundled GeoJSON. Kept ONLY for
local development where Supabase isn't configured. Logged with a WARNING so
prod misconfiguration is obvious.
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from app.services.supabase_client import get_supabase

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
GEOJSON_PATH = BASE_DIR / "data" / "processed" / "wards_master.geojson"


# ----- Fallback: in-memory shapely index (local dev only) -------------------

class _ShapelyFallback:
    """Lazy in-memory index. Only built if we have to fall back."""

    def __init__(self) -> None:
        self._wards: list[Dict[str, Any]] = []
        self._loaded = False

    def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True

        if not GEOJSON_PATH.exists():
            logger.warning("GeoJSON not found at %s; ward lookup will return None.", GEOJSON_PATH)
            return

        # Import shapely lazily so prod environments that rely purely on
        # PostGIS don't have to pay the import cost.
        from shapely.geometry import shape

        with open(GEOJSON_PATH, "r") as f:
            data = json.load(f)

        for feature in data.get("features", []):
            try:
                geom = shape(feature["geometry"])
                self._wards.append({"geometry": geom, "properties": feature["properties"]})
            except Exception as e:
                logger.error("Failed to parse ward geometry: %s", e)

        logger.warning(
            "Spatial fallback loaded %d wards in memory. Configure Supabase to "
            "use the PostGIS RPC instead.", len(self._wards),
        )

    def lookup(self, lat: float, lng: float) -> Optional[Dict[str, Any]]:
        self._load()
        if not self._wards:
            return None
        from shapely.geometry import Point
        point = Point(lng, lat)  # GeoJSON/Shapely is (lng, lat)
        for ward in self._wards:
            if ward["geometry"].contains(point):
                return ward["properties"]
        return None


_fallback = _ShapelyFallback()


# ----- Primary: PostGIS via Supabase RPC ------------------------------------

async def _rpc_lookup(lat: float, lng: float) -> Optional[Dict[str, Any]]:
    client = get_supabase()
    if not client:
        return None
    try:
        res = await asyncio.to_thread(
            lambda: client.rpc(
                "lookup_gba_ward",
                {"p_lat": lat, "p_lng": lng},
            ).execute()
        )
        if res and res.data:
            row = res.data[0] if isinstance(res.data, list) else res.data
            if isinstance(row, dict):
                return row
    except Exception as e:
        logger.warning("PostGIS ward lookup failed (will fall back): %s", e)
    return None


async def get_ward_data_async(lat: float, lng: float) -> Optional[Dict[str, Any]]:
    """Async PostGIS-first ward lookup with shapely fallback."""
    result = await _rpc_lookup(lat, lng)
    if result is not None:
        return result
    # Fallback runs sync shapely; offload so we don't block the loop while it
    # walks polygons (typically <1ms but we're being polite).
    return await asyncio.to_thread(_fallback.lookup, lat, lng)


def get_ward_data(lat: float, lng: float) -> Optional[Dict[str, Any]]:
    """
    Synchronous adapter for legacy call sites. New code should prefer
    get_ward_data_async() inside async nodes.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is None:
        return asyncio.run(get_ward_data_async(lat, lng))

    # Running inside an event loop already — fall back to sync shapely so we
    # don't deadlock. This branch should only be hit from non-async contexts
    # or unit tests; the async nodes use get_ward_data_async directly.
    return _fallback.lookup(lat, lng)
