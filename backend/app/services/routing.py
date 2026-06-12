import logging
import math
import os

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)

from app.services.supabase_client import get_supabase

logger = logging.getLogger(__name__)

_OLA_DIRECTIONS_URL = "https://api.olamaps.io/routing/v1/directions"
_REQUEST_TIMEOUT_SEC = 5.0

# Cache radius: any prior route from within this many meters of the same
# origin/destination counts as a hit. Tuned for the cursorrules mandate that
# spatial cache lookups happen *before* outbound API hits.
_CACHE_RADIUS_METERS = 100

_RETRYABLE_EXCEPTIONS = (
    httpx.ConnectError,
    httpx.ReadTimeout,
    httpx.WriteTimeout,
    httpx.ConnectTimeout,
    httpx.RemoteProtocolError,
)


def heuristic_commute(lat1: float, lng1: float, lat2: float, lng2: float) -> int:
    """Straight-line heuristic if Ola Maps fails or quota is exceeded."""
    R = 6371  # km, Haversine
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlng / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    dist_km = R * c

    # 22 km/h is a realistic Bengaluru city average (15 km/h is bumper-to-bumper,
    # 30 km/h would imply ring-road conditions all the way).
    time_hr = dist_km / 22.0
    return int(time_hr * 60)


async def _lookup_commute_cache(
    origin_lat: float, origin_lng: float, dest_lat: float, dest_lng: float
) -> int | None:
    """Check Supabase for a recently cached route within the spatial radius."""
    client = get_supabase()
    if not client:
        return None
    try:
        res = client.rpc(
            "lookup_commute_cache",
            {
                "p_origin_lat": origin_lat,
                "p_origin_lng": origin_lng,
                "p_dest_lat": dest_lat,
                "p_dest_lng": dest_lng,
                "p_radius_m": _CACHE_RADIUS_METERS,
            },
        ).execute()
        if res.data:
            row = res.data[0] if isinstance(res.data, list) else res.data
            mins = row.get("commute_time_mins") if isinstance(row, dict) else None
            if mins is not None:
                logger.info("commute_cache HIT mins=%s", mins)
                return int(mins)
    except Exception as e:
        # Cache miss/RPC-missing is non-fatal; we just fall through to the API.
        logger.debug("commute_cache lookup failed (non-fatal): %s", e)
    return None


async def _store_commute_cache(
    origin_lat: float, origin_lng: float, dest_lat: float, dest_lng: float, mins: int
) -> None:
    client = get_supabase()
    if not client:
        return
    try:
        client.rpc(
            "store_commute_cache",
            {
                "p_origin_lat": origin_lat,
                "p_origin_lng": origin_lng,
                "p_dest_lat": dest_lat,
                "p_dest_lng": dest_lng,
                "p_commute_time_mins": mins,
            },
        ).execute()
    except Exception as e:
        logger.debug("commute_cache write failed (non-fatal): %s", e)


async def _ola_call_with_retry(params: dict) -> httpx.Response | None:
    async for attempt in AsyncRetrying(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=4.0),
        retry=retry_if_exception_type(_RETRYABLE_EXCEPTIONS),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=False,
    ):
        with attempt:
            async with httpx.AsyncClient() as client:
                return await client.post(
                    _OLA_DIRECTIONS_URL, params=params, timeout=_REQUEST_TIMEOUT_SEC
                )
    return None


async def get_commute_time(
    origin_lat: float, origin_lng: float, dest_lat: float, dest_lng: float
) -> int:
    """
    Get commute time using Ola Maps API with spatial cache + circuit breaker.

    Lookup order (per cursorrules section 2: cache first):
      1. PostGIS commute_cache (radius lookup)
      2. Ola Maps API (with tenacity retries)
      3. Haversine heuristic fallback
    """
    cached = await _lookup_commute_cache(origin_lat, origin_lng, dest_lat, dest_lng)
    if cached is not None:
        return cached

    api_key = os.getenv("OLA_MAPS_API_KEY")
    if not api_key:
        return heuristic_commute(origin_lat, origin_lng, dest_lat, dest_lng)

    params = {
        "origin": f"{origin_lat},{origin_lng}",
        "destination": f"{dest_lat},{dest_lng}",
        "api_key": api_key,
    }

    try:
        resp = await _ola_call_with_retry(params)
    except _RETRYABLE_EXCEPTIONS as e:
        logger.error(f"Ola Maps exhausted retries: {e}")
        return heuristic_commute(origin_lat, origin_lng, dest_lat, dest_lng)
    except Exception as e:
        logger.error(f"Ola Maps routing failed: {e}")
        return heuristic_commute(origin_lat, origin_lng, dest_lat, dest_lng)

    if resp and resp.status_code == 200:
        data = resp.json()
        routes = data.get("routes", [])
        if routes:
            duration_sec = routes[0].get("legs", [{}])[0].get("duration", 0)
            mins = int(duration_sec / 60)
            await _store_commute_cache(origin_lat, origin_lng, dest_lat, dest_lng, mins)
            return mins

    return heuristic_commute(origin_lat, origin_lng, dest_lat, dest_lng)
