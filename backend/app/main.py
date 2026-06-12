import logging
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Header, Depends, HTTPException, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from datetime import datetime, timezone

load_dotenv(dotenv_path="../.env", override=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def commute_best_two_average_minutes(commutes: Dict[str, int]) -> Optional[float]:
    """
    Mean of the two shortest tech-park commute times (same basis as livability
    commute scoring). ``commutes`` maps tech_park_id -> minutes.
    """
    if not commutes:
        return None
    sorted_pairs = sorted(commutes.items(), key=lambda x: x[1])
    best_two = sorted_pairs[:2]
    if not best_two:
        return None
    return sum(t for _, t in best_two) / len(best_two)


app = FastAPI(title="Namma Bengaluru Reality-Check Engine API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AnalyzeRequest(BaseModel):
    raw_text: str
    source_platform: str = "manual"
    source_msg_id: str = ""


# Map AgentState.pipeline_status -> HTTP status code. Lets clients/gateways
# branch on the response status without parsing the body.
_STATUS_HTTP_MAP: Dict[str, int] = {
    "success":   200,
    "partial":   200,   # scorecard still returned; client decides what to surface
    "duplicate": 200,
    "running":   202,   # shouldn't happen on a terminal response, but defensive
    "timeout":   504,
    "failed":    502,
}

_anonymous_ip_counts: Dict[str, int] = {}
_anonymous_ip_date: str = ""

async def get_current_user_optional(authorization: Optional[str] = Header(None)) -> Optional[Dict[str, Any]]:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.split(" ")[1]
    from app.services.supabase_client import get_user_from_token
    return get_user_from_token(token)


async def get_current_user_required(user: Optional[Dict[str, Any]] = Depends(get_current_user_optional)) -> Dict[str, Any]:
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing authentication token"
        )
    return user


@app.get("/api/health")
async def health_check():
    """Endpoint for Supabase keepalive cron and general health check."""
    return {"status": "ok", "message": "Namma Bengaluru Reality-Check Engine is running."}


@app.post("/api/analyze")
async def analyze_listing(
    request: AnalyzeRequest,
    req: Request,
    user: Optional[Dict[str, Any]] = Depends(get_current_user_optional)
) -> JSONResponse:
    """
    Main endpoint to process a raw rental listing through the LangGraph pipeline.

    Response HTTP status reflects the pipeline's terminal status so callers can
    distinguish a real success from a timeout/failure without parsing the body.
    """
    logger.info("Received listing for analysis from %s", request.source_platform)

    # --- Rate Limiting Logic ---
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    global _anonymous_ip_date, _anonymous_ip_counts
    
    # Reset in-memory counter if it's a new day
    if _anonymous_ip_date != today_str:
        _anonymous_ip_date = today_str
        _anonymous_ip_counts = {}

    from app.services.supabase_client import get_supabase
    client = get_supabase()

    if user:
        if client:
            today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
            try:
                count_res = client.table("user_searches")\
                    .select("id", count="exact")\
                    .eq("user_id", user["id"])\
                    .gte("created_at", today_start)\
                    .execute()
                
                daily_searches = count_res.count if count_res.count is not None else len(count_res.data)
                if daily_searches >= 5:
                    raise HTTPException(
                        status_code=429, 
                        detail="You have reached your daily limit of 5 searches. Please try again tomorrow."
                    )
            except HTTPException:
                raise
            except Exception as e:
                logger.error("Failed to check rate limit in DB: %s", e)
    else:
        # Anonymous IP rate limiting (strict limit of 1 per day)
        client_ip = req.client.host if req.client else "unknown"
        if _anonymous_ip_counts.get(client_ip, 0) >= 1:
             raise HTTPException(
                 status_code=429, 
                 detail="Anonymous search limit reached (1 per day). Please log in to search up to 5 listings per day."
             )
        _anonymous_ip_counts[client_ip] = _anonymous_ip_counts.get(client_ip, 0) + 1
    # ---------------------------

    from app.graph.pipeline import run_pipeline

    result: Dict[str, Any] = await run_pipeline(
        request.raw_text, request.source_platform, request.source_msg_id
    )

    pipeline_status = result.get("pipeline_status", "failed")
    http_status = _STATUS_HTTP_MAP.get(pipeline_status, 500)

    listing_id = result.get("id")
    if user and listing_id:
        if client:
            try:
                client.table("user_searches").upsert({
                    "user_id": user["id"],
                    "listing_id": listing_id
                }).execute()
                logger.info("Recorded search for user %s, listing %s", user["id"], listing_id)
            except Exception as e:
                logger.error("Failed to record user search in DB: %s", e)

    return JSONResponse(
        status_code=http_status,
        content={
            "status": pipeline_status,
            "id": listing_id,
            "duplicate_of": result.get("duplicate_of"),
            "pipeline_result": _jsonable(result),
        },
    )


@app.get("/api/listings/history")
async def get_listings_history(
    limit: int = 20,
    offset: int = 0,
    user: Dict[str, Any] = Depends(get_current_user_required)
):
    """Fetch user's previously searched listings."""
    from app.services.supabase_client import get_supabase
    client = get_supabase()
    if not client:
        return {"listings": [], "total": 0}

    try:
        # Fetch matching searches from user_searches joined with rental_listings
        res = client.table("user_searches")\
            .select("created_at, rental_listings(*)")\
            .eq("user_id", user["id"])\
            .order("created_at", desc=True)\
            .range(offset, offset + limit - 1)\
            .execute()

        # Count total searches for the user
        count_res = client.table("user_searches")\
            .select("id", count="exact")\
            .eq("user_id", user["id"])\
            .execute()

        total = count_res.count if count_res.count is not None else len(res.data)

        listings = []
        for row in res.data:
            listing = row.get("rental_listings")
            if listing:
                # Format to look like standard listing card summary
                listings.append({
                    "id": listing["id"],
                    "search_date": row["created_at"],
                    "raw_location": listing["raw_location"],
                    "bhk_type": listing["bhk_type"],
                    "rent_amount": listing["rent_amount"],
                    "security_deposit": listing["security_deposit"],
                    "livability_score": listing["livability_score"],
                    "water_risk_level": listing["water_risk_level"],
                    "created_at": listing["created_at"],
                })

        listing_ids = [item["id"] for item in listings]
        commute_avg_by_listing: Dict[str, Optional[float]] = {}
        if listing_ids:
            comm_res = (
                client.table("commute_results")
                .select("listing_id, tech_park_id, minutes")
                .in_("listing_id", listing_ids)
                .execute()
            )
            by_listing: Dict[str, Dict[str, int]] = {}
            for crow in comm_res.data or []:
                lid = crow.get("listing_id")
                pid = crow.get("tech_park_id")
                mins = crow.get("minutes")
                if lid and pid is not None and mins is not None:
                    by_listing.setdefault(str(lid), {})[str(pid)] = int(mins)
            for lid, cmap in by_listing.items():
                commute_avg_by_listing[lid] = commute_best_two_average_minutes(cmap)

        for item in listings:
            raw_avg = commute_avg_by_listing.get(str(item["id"]))
            item["commute_avg_minutes"] = (
                int(round(raw_avg)) if raw_avg is not None else None
            )

        return {"listings": listings, "total": total}
    except Exception as e:
        logger.error("Failed to fetch search history: %s", e)
        raise HTTPException(status_code=500, detail="Database fetch failed")


@app.get("/api/listings/{listing_id}")
async def get_listing_detail(
    listing_id: str,
    user: Dict[str, Any] = Depends(get_current_user_required)
):
    """Retrieve detailed listing and reconstruct its scorecard."""
    from app.services.supabase_client import get_supabase
    client = get_supabase()
    if not client:
        raise HTTPException(status_code=500, detail="Database connection unavailable")

    try:
        # 1. Verify user actually searched or owns this listing check
        check_res = client.table("user_searches")\
            .select("id")\
            .eq("user_id", user["id"])\
            .eq("listing_id", listing_id)\
            .execute()
        if not check_res.data:
            raise HTTPException(status_code=403, detail="Forbidden: You haven't searched this listing")

        # 2. Fetch the listing
        listing_res = client.table("rental_listings").select("*").eq("id", listing_id).execute()
        if not listing_res.data:
            raise HTTPException(status_code=404, detail="Listing not found")
        listing = listing_res.data[0]

        # 3. Fetch commutes
        commutes_res = client.table("commute_results").select("tech_park_id, minutes").eq("listing_id", listing_id).execute()
        commutes = {row["tech_park_id"]: row["minutes"] for row in commutes_res.data}

        # 4. Reconstruct scorecard
        from app.graph.nodes._water_scoring import compute_water_score
        from app.models.schemas import RentalListingSchema

        parsed_listing = RentalListingSchema(
            rent_amount=listing.get("rent_amount"),
            security_deposit=listing.get("security_deposit"),
            bhk_type=listing.get("bhk_type"),
            raw_location=listing.get("raw_location"),
            preferred_gender=listing.get("preferred_gender"),
            restrictions=listing.get("restrictions"),
            cauvery_mentioned=listing.get("cauvery_mentioned"),
            borewell_mentioned=listing.get("borewell_mentioned"),
            water_24x7=listing.get("water_24x7"),
            rwh_mentioned=listing.get("rwh_mentioned"),
            tanker_mentioned=listing.get("tanker_mentioned")
        )

        water_breakdown, water_red_flags = compute_water_score(
            cauvery_stage=listing.get("cauvery_stage"),
            water_risk_level=listing.get("water_risk_level"),
            parsed_listing=parsed_listing,
            gba_ward_name=listing.get("gba_ward_name"),
        )

        # Reconstruct commute score
        commute_score = 0
        red_flags = []
        best_avg = commute_best_two_average_minutes(commutes)
        if best_avg is not None:
            if best_avg <= 30:
                commute_score = 40
            elif best_avg <= 45:
                commute_score = 25
            elif best_avg <= 60:
                commute_score = 10
            else:
                commute_score = 0
        else:
            red_flags.append("Commute data unavailable; score defaulted to 0.")

        red_flags.extend(water_red_flags)

        # Reconstruct financial score
        financial_score = 0
        if parsed_listing.security_deposit and parsed_listing.rent_amount and parsed_listing.rent_amount > 0:
            months_dep = parsed_listing.security_deposit / parsed_listing.rent_amount
            if months_dep <= 3:
                financial_score = 15
            elif months_dep <= 6:
                financial_score = 5
            else:
                financial_score = 0
                red_flags.append("High security deposit (>6 months).")
        else:
            financial_score = 0
            red_flags.append("Rent or deposit details missing from listing.")

        # Reconstruct civic score
        corp = listing.get("gba_corporation") or ""
        if "Central" in corp or "South" in corp:
            civic_score = 10
        elif corp and corp != "Outside GBA":
            civic_score = 5
        else:
            civic_score = 0

        total_score = commute_score + water_breakdown.total + financial_score + civic_score

        alternatives = []
        if total_score < 50:
            alternatives = [
                {"neighborhood": "Malleshwaram", "reason": "Better water security and Central GBA."},
                {"neighborhood": "Jayanagar", "reason": "Consistent Cauvery Stage 1 coverage."},
            ]

        scorecard = {
            "total_score": total_score,
            "commute_score": commute_score,
            "water_score": water_breakdown.total,
            "financial_score": financial_score,
            "civic_score": civic_score,
            "water_breakdown": {
                "total": water_breakdown.total,
                "cauvery_supply": water_breakdown.cauvery_supply,
                "groundwater_resilience": water_breakdown.groundwater_resilience,
                "building_signals": water_breakdown.building_signals,
                "confidence": water_breakdown.confidence,
                "rationale": water_breakdown.rationale
            },
            "red_flags": red_flags,
            "alternatives": alternatives
        }

        # Build payload matching frontend ApiResponse structure
        return {
            "status": "success",
            "id": listing["id"],
            "pipeline_result": {
                "pipeline_status": "success",
                "scorecard": scorecard,
                "parsed_listing": {
                    "raw_location": listing["raw_location"],
                    "bhk_type": listing["bhk_type"],
                    "rent_amount": listing["rent_amount"],
                    "security_deposit": listing["security_deposit"]
                },
                "commutes": commutes,
                "latitude": float(listing["latitude"]) if listing["latitude"] else None,
                "longitude": float(listing["longitude"]) if listing["longitude"] else None,
                "geocode_provider": listing["geocode_provider"],
                "geocode_confidence": float(listing["geocode_confidence"]) if listing["geocode_confidence"] else None
            }
        }
    except Exception as e:
        logger.error("Failed to fetch listing detail: %s", e)
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail="Database fetch failed")


# Heavy fields we never want to ship to the browser — `embedding` is 768
# floats, useless to the UI and bloats every response.
_OMIT_KEYS = {"embedding"}


def _jsonable(state: Dict[str, Any]) -> Dict[str, Any]:
    """Convert pydantic models inside AgentState to plain dicts for JSON."""
    out: Dict[str, Any] = {}
    for key, value in state.items():
        if key in _OMIT_KEYS:
            continue
        if isinstance(value, BaseModel):
            out[key] = value.model_dump()
        else:
            out[key] = value
    return out


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)

