import logging

from app.graph.nodes._decorator import node
from app.graph.nodes._water_scoring import compute_water_score
from app.models.schemas import AgentState, LivabilityScorecard

logger = logging.getLogger(__name__)


@node("scoring", timeout=5.0, fatal=False)
async def process(state: AgentState) -> dict:
    """Calculate the final Livability Score based on 100-point formula."""
    logger.info("Calculating Livability Score...")

    scorecard = LivabilityScorecard()

    # 1. Commute Score (40 pts)
    # Use the BEST 2 commute times (nearest tech parks) instead of averaging all 5.
    # Rationale: A person commutes to ONE workplace, not all 5. Using best-2
    # gives a realistic buffer for couples/roommates working at different parks.
    commutes = state.get("commutes") or {}
    if commutes:
        sorted_commutes = sorted(commutes.items(), key=lambda x: x[1])
        best_two = sorted_commutes[:2]
        best_avg = sum(t for _, t in best_two) / len(best_two)

        logger.info("Commute breakdown: %s", dict(sorted_commutes))
        logger.info("Best 2 parks: %s -> avg %.0f min", best_two, best_avg)

        if best_avg <= 30:
            scorecard.commute_score = 40
        elif best_avg <= 45:
            scorecard.commute_score = 25
        elif best_avg <= 60:
            scorecard.commute_score = 10
        else:
            scorecard.commute_score = 0
    else:
        scorecard.red_flags.append("Commute data unavailable; score defaulted to 0.")

    # 2. Water Score (35 pts) — decomposed sub-scoring (see _water_scoring.py).
    water_breakdown, water_red_flags = compute_water_score(
        cauvery_stage=state.get("cauvery_stage"),
        water_risk_level=state.get("water_risk_level"),
        parsed_listing=state.get("parsed_listing"),
        gba_ward_name=state.get("gba_ward_name"),
    )
    scorecard.water_score = water_breakdown.total
    scorecard.water_breakdown = water_breakdown
    scorecard.red_flags.extend(water_red_flags)
    logger.info(
        "Water score: total=%d (cauvery=%d, ground=%d, signals=%d, confidence=%s)",
        water_breakdown.total,
        water_breakdown.cauvery_supply,
        water_breakdown.groundwater_resilience,
        water_breakdown.building_signals,
        water_breakdown.confidence,
    )

    # 3. Financial Score (15 pts)
    parsed = state.get("parsed_listing")
    if parsed and parsed.security_deposit and parsed.rent_amount and parsed.rent_amount > 0:
        months_dep = parsed.security_deposit / parsed.rent_amount
        if months_dep <= 3:
            scorecard.financial_score = 15
        elif months_dep <= 6:
            scorecard.financial_score = 5
        else:
            scorecard.financial_score = 0
            scorecard.red_flags.append("High security deposit (>6 months).")
    else:
        scorecard.financial_score = 0
        scorecard.red_flags.append("Rent or deposit details missing from listing.")

    # 4. Civic Score (10 pts)
    corp = state.get("gba_corporation") or ""
    if "Central" in corp or "South" in corp:
        scorecard.civic_score = 10
    elif corp and corp != "Outside GBA":
        scorecard.civic_score = 5
    else:
        scorecard.civic_score = 0

    scorecard.total_score = (
        scorecard.commute_score
        + scorecard.water_score
        + scorecard.financial_score
        + scorecard.civic_score
    )

    if scorecard.total_score < 50:
        scorecard.alternatives = [
            {"neighborhood": "Malleshwaram", "reason": "Better water security and Central GBA."},
            {"neighborhood": "Jayanagar", "reason": "Consistent Cauvery Stage 1 coverage."},
        ]

    # Preserve any "partial" status set by an earlier soft-failing node; only
    # promote to "success" when nothing went wrong upstream.
    final_status = "partial" if state.get("errors") else "success"

    return {"scorecard": scorecard, "pipeline_status": final_status}
