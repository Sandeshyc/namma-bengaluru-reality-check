import asyncio
import logging
import os
from typing import Any, Iterable

from langchain_google_genai import GoogleGenerativeAIEmbeddings

from app.graph.nodes._decorator import node
from app.graph.nodes._water_scoring import compute_water_score
from app.models.schemas import AgentState, LivabilityScorecard, RentalListingSchema
from app.services.llm_throttle import throttle
from app.services.supabase_client import get_supabase

logger = logging.getLogger(__name__)

# Current Gemini embedding model. The older `models/embedding-001` and
# `models/text-embedding-004` IDs have been retired and now return 404s.
EMBEDDING_MODEL = os.getenv("GEMINI_EMBEDDING_MODEL", "models/gemini-embedding-001")
EMBEDDING_DIMENSIONS = 768
EMBEDDING_TIMEOUT_SEC = 8.0

# Dedup tuning. Tightened from a generic 0.85 since rental listings are
# repetitive boilerplate by nature ("2BHK fully furnished near...") and a
# loose threshold would flag distinct flats in the same neighborhood as dupes.
SIMILARITY_THRESHOLD = 0.92
SPATIAL_RADIUS_M = 500


def _vector_to_pg_literal(vec: Iterable[float]) -> str:
    """
    pgvector accepts string literals like '[0.1,0.2,...]' for vector casting.
    We use this format because PostgREST can't reliably serialize a Python
    list-of-floats to pgvector's binary representation across the wire.
    """
    return "[" + ",".join(f"{x:.8f}" for x in vec) + "]"


def _score_from_record(
    record: dict[str, Any],
    commutes: dict[str, int],
    parsed: RentalListingSchema,
) -> LivabilityScorecard:
    """Rebuild the scorecard for a cached duplicate from persisted fields."""
    scorecard = LivabilityScorecard()

    if commutes:
        best_two = sorted(commutes.items(), key=lambda item: item[1])[:2]
        best_avg = sum(minutes for _, minutes in best_two) / len(best_two)
        if best_avg <= 30:
            scorecard.commute_score = 40
        elif best_avg <= 45:
            scorecard.commute_score = 25
        elif best_avg <= 60:
            scorecard.commute_score = 10
    else:
        scorecard.red_flags.append("Commute data unavailable; score defaulted to 0.")

    water_breakdown, water_red_flags = compute_water_score(
        cauvery_stage=record.get("cauvery_stage"),
        water_risk_level=record.get("water_risk_level"),
        parsed_listing=parsed,
        gba_ward_name=record.get("gba_ward_name"),
    )
    scorecard.water_score = water_breakdown.total
    scorecard.water_breakdown = water_breakdown
    scorecard.red_flags.extend(water_red_flags)

    rent = record.get("rent_amount")
    deposit = record.get("security_deposit")
    if rent and deposit and rent > 0:
        months_dep = deposit / rent
        if months_dep <= 3:
            scorecard.financial_score = 15
        elif months_dep <= 6:
            scorecard.financial_score = 5
        else:
            scorecard.red_flags.append("High security deposit (>6 months).")
    else:
        scorecard.red_flags.append("Rent or deposit details missing from listing.")

    corp = record.get("gba_corporation") or ""
    if "Central" in corp or "South" in corp:
        scorecard.civic_score = 10
    elif corp and corp != "Outside GBA":
        scorecard.civic_score = 5

    scorecard.total_score = (
        scorecard.commute_score
        + scorecard.water_score
        + scorecard.financial_score
        + scorecard.civic_score
    )
    if record.get("livability_score") is not None and record["livability_score"] != scorecard.total_score:
        logger.debug(
            "Recomputed duplicate score differs from persisted total: persisted=%s recomputed=%s",
            record["livability_score"],
            scorecard.total_score,
        )
    if scorecard.total_score < 50:
        scorecard.alternatives = [
            {"neighborhood": "Malleshwaram", "reason": "Better water security and Central GBA."},
            {"neighborhood": "Jayanagar", "reason": "Consistent Cauvery Stage 1 coverage."},
        ]
    return scorecard


def _hydrate_duplicate(client: Any, listing_id: str) -> dict[str, Any]:
    """Fetch the canonical listing so duplicate submissions can reuse scores."""
    listing_res = (
        client.table("rental_listings")
        .select(
            "id,raw_text,rent_amount,security_deposit,bhk_type,raw_location,"
            "preferred_gender,restrictions,latitude,longitude,geocode_confidence,"
            "geocode_provider,water_risk_level,cauvery_stage,gba_corporation,"
            "gba_ward_name,livability_score,cauvery_mentioned,borewell_mentioned,"
            "water_24x7,rwh_mentioned,tanker_mentioned"
        )
        .eq("id", listing_id)
        .single()
        .execute()
    )
    record = listing_res.data
    if not isinstance(record, dict):
        return {}

    commute_res = (
        client.table("commute_results")
        .select("tech_park_id,minutes")
        .eq("listing_id", listing_id)
        .execute()
    )
    commutes = {
        str(row["tech_park_id"]): int(row["minutes"])
        for row in (commute_res.data or [])
        if row.get("tech_park_id") and row.get("minutes") is not None
    }

    parsed = RentalListingSchema(
        rent_amount=record.get("rent_amount"),
        security_deposit=record.get("security_deposit"),
        bhk_type=record.get("bhk_type"),
        raw_location=record.get("raw_location") or "Unknown",
        preferred_gender=record.get("preferred_gender"),
        restrictions=record.get("restrictions") or [],
        cauvery_mentioned=record.get("cauvery_mentioned"),
        borewell_mentioned=record.get("borewell_mentioned"),
        water_24x7=record.get("water_24x7"),
        rwh_mentioned=record.get("rwh_mentioned"),
        tanker_mentioned=record.get("tanker_mentioned"),
    )

    return {
        "parsed_listing": parsed,
        "latitude": float(record["latitude"]) if record.get("latitude") is not None else None,
        "longitude": float(record["longitude"]) if record.get("longitude") is not None else None,
        "geocode_confidence": (
            float(record["geocode_confidence"])
            if record.get("geocode_confidence") is not None
            else None
        ),
        "geocode_provider": record.get("geocode_provider"),
        "water_risk_level": record.get("water_risk_level"),
        "cauvery_stage": record.get("cauvery_stage"),
        "gba_corporation": record.get("gba_corporation"),
        "gba_ward_name": record.get("gba_ward_name"),
        "commutes": commutes,
        "scorecard": _score_from_record(record, commutes, parsed),
    }


@node("duplicate", timeout=12.0, fatal=False)
async def process(state: AgentState) -> dict:
    """Check for semantic duplicates within a spatial radius using pgvector."""
    logger.info("Checking for duplicates...")

    base = {"is_duplicate": False, "duplicate_of": None}

    api_key = os.getenv("GEMINI_API_KEY")
    client = get_supabase()

    if not api_key or not client:
        logger.warning("Missing API keys or DB client. Skipping duplicate check.")
        return base

    lat = state.get("latitude")
    lng = state.get("longitude")
    if lat is None or lng is None:
        logger.warning("No coordinates for spatial dedup; skipping.")
        return base

    # Throttle outbound embedding call alongside the extraction LLM — they
    # share the same Gemini quota bucket.
    await throttle("gemini")

    embeddings = GoogleGenerativeAIEmbeddings(
        model=EMBEDDING_MODEL,
        google_api_key=api_key,
        output_dimensionality=EMBEDDING_DIMENSIONS,
        task_type="SEMANTIC_SIMILARITY",
    )

    # Inner asyncio.wait_for in addition to the outer decorator: the embedding
    # client doesn't expose a per-request timeout kwarg.
    vector = await asyncio.wait_for(
        embeddings.aembed_query(state["raw_text"]),
        timeout=EMBEDDING_TIMEOUT_SEC,
    )

    # Thread the embedding through state so persist_node can reuse it without
    # paying for a second Gemini call.
    base["embedding"] = vector

    # Spatial + semantic dedup: PostGIS ST_DWithin filter combined with
    # pgvector cosine-similarity. Single round-trip via the match_listings RPC.
    try:
        res = await asyncio.to_thread(
            lambda: client.rpc(
                "match_listings",
                {
                    "p_embedding": _vector_to_pg_literal(vector),
                    "p_lat": float(lat),
                    "p_lng": float(lng),
                    "p_radius_m": SPATIAL_RADIUS_M,
                    "p_similarity_threshold": SIMILARITY_THRESHOLD,
                },
            ).execute()
        )
    except Exception as e:
        # RPC missing (migration not yet applied) or transient DB blip — treat
        # as a cache miss. Don't fail the node; the listing just isn't
        # de-duplicated this run.
        logger.debug("match_listings RPC failed (non-fatal): %s", e)
        return base

    if not res or not res.data:
        return base

    match = res.data[0] if isinstance(res.data, list) else res.data
    if not isinstance(match, dict) or not match.get("id"):
        return base

    logger.info(
        "Duplicate detected: id=%s similarity=%.3f distance_m=%.0f",
        match["id"],
        float(match.get("similarity") or 0.0),
        float(match.get("distance_m") or 0.0),
    )
    duplicate_update = {
        "is_duplicate": True,
        "duplicate_of": str(match["id"]),
        "embedding": vector,
        "pipeline_status": "duplicate",
    }

    try:
        duplicate_update.update(
            await asyncio.to_thread(_hydrate_duplicate, client, str(match["id"]))
        )
    except Exception as e:
        logger.warning("Could not hydrate duplicate listing %s: %s", match["id"], e)

    return duplicate_update
