import logging

from app.graph.nodes._decorator import node
from app.models.schemas import AgentState
from app.services.spatial import get_ward_data_async
from app.services.water_data import water_db

logger = logging.getLogger(__name__)


@node("civic_water", timeout=6.0, fatal=False)
async def process(state: AgentState) -> dict:
    """Look up civic and water data via PostGIS spatial join."""
    logger.info("Looking up civic and water data.")
    lat = state.get("latitude")
    lng = state.get("longitude")

    if lat is None or lng is None:
        return {}

    ward_data = await get_ward_data_async(lat, lng)
    if not ward_data:
        logger.warning("Coordinates not within any GBA ward.")
        return {
            "gba_ward_name": "Outside GBA",
            "cauvery_stage": "Unknown",
            "water_risk_level": "High",
        }

    update: dict = {
        "gba_ward_name": ward_data.get("ward_name"),
        "gba_corporation": ward_data.get("gba_corporation"),
        "cauvery_stage": ward_data.get("cauvery_stage", "Unknown"),
        "water_risk_level": ward_data.get("groundwater_risk", "Unknown"),
    }

    # Fallback: Administrative ward names (e.g. 'Hoysala Nagara Central') often
    # don't match colloquial BWSSB water mapping names (e.g. 'Indiranagar').
    # Apply a dynamic fuzzy match against the raw dataset before giving up.
    if update["cauvery_stage"] == "Unknown":
        parsed = state.get("parsed_listing")
        if parsed and parsed.raw_location:
            match = water_db.fuzzy_match_location(parsed.raw_location)
            if match:
                update["cauvery_stage"] = match["stage"]
                update["water_risk_level"] = match["risk"]
                logger.info(
                    "Fuzzy fallback match successful: %s -> %s",
                    parsed.raw_location, match["stage"],
                )

    return update
