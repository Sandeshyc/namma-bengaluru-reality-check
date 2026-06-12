import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Dict, Tuple

from app.graph.nodes._decorator import node
from app.models.schemas import AgentState
from app.services.routing import get_commute_time

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent
TECH_PARKS_FILE = BASE_DIR / "data" / "processed" / "tech_parks.json"

# Be polite to Ola Maps: at most 3 in flight at once. Prevents accidental
# bursts when a frontend session triggers many runs in parallel.
_OLA_CONCURRENCY = 3
_PER_PARK_TIMEOUT_SEC = 6.0


async def _fetch_one(
    sem: asyncio.Semaphore,
    lat: float,
    lng: float,
    tp: Dict[str, Any],
) -> Tuple[str, int | None, Exception | None]:
    async with sem:
        try:
            mins = await asyncio.wait_for(
                get_commute_time(lat, lng, tp["lat"], tp["lng"]),
                timeout=_PER_PARK_TIMEOUT_SEC,
            )
            return tp["id"], int(mins), None
        except Exception as exc:  # noqa: BLE001 — collected, not re-raised
            return tp["id"], None, exc


@node("commute", timeout=15.0, fatal=False)
async def process(state: AgentState) -> dict:
    """Calculate commute to all target tech parks concurrently."""
    logger.info("Calculating commute times...")

    lat = state.get("latitude")
    lng = state.get("longitude")
    if lat is None or lng is None:
        logger.warning("No coordinates to route.")
        return {"commutes": {}}

    if not TECH_PARKS_FILE.exists():
        logger.warning("Tech parks file missing at %s", TECH_PARKS_FILE)
        return {"commutes": {}}

    with open(TECH_PARKS_FILE, "r") as f:
        tech_parks = json.load(f)

    sem = asyncio.Semaphore(_OLA_CONCURRENCY)
    results = await asyncio.gather(
        *(_fetch_one(sem, lat, lng, tp) for tp in tech_parks),
        return_exceptions=False,
    )

    commutes: Dict[str, int] = {}
    failures: list[str] = []
    for tp_id, mins, err in results:
        if err is None and mins is not None:
            commutes[tp_id] = mins
        else:
            failures.append(f"{tp_id}: {type(err).__name__ if err else 'no-result'}")

    update: dict = {"commutes": commutes}

    if failures:
        # Record but don't fail the node — scoring degrades gracefully on a
        # partial commute map (uses best-2 of whatever it gets).
        update["errors"] = [{
            "node": "commute",
            "type": "PartialResult",
            "message": f"failed for {len(failures)}/{len(tech_parks)} parks: {failures}",
            "retryable": True,
        }]

    logger.info("Commute fetched for %d/%d parks", len(commutes), len(tech_parks))
    return update
