import logging

from app.graph.nodes._decorator import node
from app.models.schemas import AgentState
from app.services.geocoding import geocode

logger = logging.getLogger(__name__)


@node("geocode", timeout=20.0, fatal=True)
async def process(state: AgentState) -> dict:
    """Geocode the extracted location."""
    parsed = state.get("parsed_listing")
    if not parsed or not parsed.raw_location:
        logger.error("No location to geocode; aborting downstream stages.")
        return {
            "errors": [{
                "node": "geocode",
                "type": "MissingInput",
                "message": "parsed_listing.raw_location is empty",
                "retryable": False,
            }],
            "pipeline_status": "failed",
        }

    logger.info("Geocoding location: %s", parsed.raw_location)
    result = await geocode(parsed.raw_location)

    if result:
        return {
            "latitude": result["lat"],
            "longitude": result["lng"],
            "geocode_confidence": result["confidence"],
            "geocode_provider": result["provider"],
        }

    # `geocode()` already returns a fallback dict, so this branch shouldn't
    # normally trigger. Defensive fallback for the None edge case.
    logger.warning("Geocoding returned None. Using default center.")
    return {
        "latitude": 12.9716,
        "longitude": 77.5946,
        "geocode_confidence": 0.0,
        "geocode_provider": "fallback_center",
    }
