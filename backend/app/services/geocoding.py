import logging
import os

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)

logger = logging.getLogger(__name__)

_GOOGLE_GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
_REQUEST_TIMEOUT_SEC = 5.0

# Only retry on transient network failures. Do NOT retry on 4xx — those are
# permanent (bad key, malformed query, over-quota) and we want to surface them
# immediately rather than burning quota on attempts that can't succeed.
_RETRYABLE_EXCEPTIONS = (
    httpx.ConnectError,
    httpx.ReadTimeout,
    httpx.WriteTimeout,
    httpx.ConnectTimeout,
    httpx.RemoteProtocolError,
)


async def _http_get_with_retry(url: str, params: dict) -> httpx.Response | None:
    """One-shot httpx.GET with bounded retries on transient network errors."""
    async for attempt in AsyncRetrying(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=4.0),
        retry=retry_if_exception_type(_RETRYABLE_EXCEPTIONS),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=False,
    ):
        with attempt:
            async with httpx.AsyncClient() as client:
                return await client.get(url, params=params, timeout=_REQUEST_TIMEOUT_SEC)
    return None


async def geocode_google(address: str) -> dict | None:
    """Geocode using Google Maps API with Bengaluru-bounded results."""
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        logger.warning("GOOGLE_MAPS_API_KEY missing. Please add it to your .env file.")
        return None

    params = {
        "address": f"{address}, Bengaluru, Karnataka, India",
        "key": api_key,
        # Constrain results to Bengaluru bounding box (Southwest|Northeast)
        "bounds": "12.75,77.4|13.15,77.85",
        "components": "country:IN",
    }

    try:
        resp = await _http_get_with_retry(_GOOGLE_GEOCODE_URL, params)
    except _RETRYABLE_EXCEPTIONS as e:
        logger.error(f"Google Maps API exhausted retries: {e}")
        return None
    except Exception as e:
        logger.error(f"Google Maps API failed: {e}")
        return None

    if not resp or resp.status_code != 200:
        logger.warning("Google Maps non-200: %s", resp.status_code if resp else "no-response")
        return None

    data = resp.json()
    if data.get("status") != "OK" or not data.get("results"):
        logger.warning(f"Google Maps failed to find '{address}': {data.get('status')}")
        return None

    best = data["results"][0]
    lat = float(best["geometry"]["location"]["lat"])
    lng = float(best["geometry"]["location"]["lng"])
    display_name = best.get("formatted_address", "")

    # Sanity check: verify coordinates are within Bengaluru bounds
    if not (12.7 <= lat <= 13.2 and 77.3 <= lng <= 77.9):
        logger.warning(
            f"Geocoded result outside Bengaluru: ({lat}, {lng}) for '{address}'. Discarding."
        )
        return None

    logger.info(f"Google Geocoded '{address}' -> ({lat}, {lng}) | {display_name}")
    return {
        "lat": lat,
        "lng": lng,
        "confidence": 0.9,
        "provider": "google_maps",
        "display_name": display_name,
    }


async def geocode(address: str) -> dict:
    """Main geocoding function with progressive-stripping fallback."""
    res = await geocode_google(address)
    if res:
        return res

    # Retry 1: If the address has commas, try just the first part (often the core locality)
    first_chunk = address.split(",")[0].strip()
    if first_chunk and first_chunk != address:
        logger.info(f"Geocoding full string failed. Retrying with first chunk: '{first_chunk}'")
        res = await geocode_google(first_chunk)
        if res:
            return res

    # Retry 2: Just use the very first word (which is almost always the neighborhood)
    parts = address.split()
    first_word = parts[0].replace(",", "").strip() if parts else ""
    if first_word and first_word not in (address, first_chunk):
        logger.info(f"Geocoding chunk failed. Retrying with primary keyword: '{first_word}'")
        res = await geocode_google(first_word)
        if res:
            return res

    # Fallback: Bengaluru city center
    logger.warning(f"All geocoding failed for '{address}'. Using Bengaluru center as fallback.")
    return {
        "lat": 12.9716,
        "lng": 77.5946,
        "confidence": 0.1,
        "provider": "fallback_center",
        "display_name": "Bengaluru City Center (fallback)",
    }
