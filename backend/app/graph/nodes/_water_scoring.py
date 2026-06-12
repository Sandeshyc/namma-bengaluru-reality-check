"""
Water security scoring logic (Tiers 1 + 3 of the water audit).

Lives in its own module so it can be unit-tested in isolation and swapped
out via A/B (just bind a different `compute_water_score` callable in
scoring_node.process). Pure functions — no I/O, no side effects.

Design contract:
    Input:  cauvery_stage:str | None
            water_risk_level:str | None
            parsed_listing:RentalListingSchema | None
            ward_name:str | None  (for "Outside GBA" handling)
    Output: WaterScoreBreakdown (total, sub-scores, confidence, rationale)
            + a list of differentiated red-flag strings to surface in the
              scorecard's red_flags list.

Score composition (additive, max 35):
    cauvery_supply        : 0-17
    groundwater_resilience: 0-11
    building_signals      : 0-7
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from app.models.schemas import (
    LivabilityScorecard,
    RentalListingSchema,
    WaterConfidence,
    WaterScoreBreakdown,
)

# ----- Lookup tables ---------------------------------------------------------

# Cauvery stage -> sub-score (0-17). Smoother than the original 3-bucket cliff:
# Stage 2 isn't quite as good as Stage 1, Stage 4 Phase 2 isn't quite as bad
# as no connection at all, "Unknown" gets the mid-point with a confidence
# downgrade rather than the worst-case slap.
_CAUVERY_SCORE = {
    "stage_1":    17,
    "stage_2":    15,
    "stage_3":    11,
    "stage_4_p1":  7,
    "stage_4_p2":  4,
    "outside":     2,
    "unknown":     9,   # mean-of-range; paired with confidence="low"
}

# Groundwater risk -> sub-score (0-11). Layered on top of Cauvery because
# they're independent failure modes: you can have great Cauvery + dead
# borewells (HSR), or weak Cauvery + healthy aquifer (parts of Devanahalli).
_GROUNDWATER_SCORE = {
    "low":      11,
    "medium":    8,
    "high":      5,
    "unknown":   6,   # mean-of-range
}

_BUILDING_SIGNALS_NEUTRAL = 3   # baseline when listing gives no info either way
_BUILDING_SIGNALS_MIN = 0
_BUILDING_SIGNALS_MAX = 7


# ----- Normalizers -----------------------------------------------------------

def _normalize_stage(stage: Optional[str]) -> str:
    """Collapse the messy variant spellings into our 7-bucket key set."""
    if not stage:
        return "unknown"
    s = stage.lower().strip()
    if "stage 1" in s:
        return "stage_1"
    if "stage 2" in s:
        return "stage_2"
    if "stage 3" in s:
        return "stage_3"
    if "stage 4" in s:
        if "phase 2" in s or "ph 2" in s or "p2" in s:
            return "stage_4_p2"
        return "stage_4_p1"
    return "unknown"


def _normalize_risk(risk: Optional[str]) -> str:
    if not risk:
        return "unknown"
    r = risk.lower().strip()
    if r in ("low", "medium", "high"):
        return r
    return "unknown"


# ----- Sub-score computers ---------------------------------------------------

def _cauvery_supply_score(stage_key: str) -> Tuple[int, str]:
    """Return (sub_score, rationale_line)."""
    score = _CAUVERY_SCORE.get(stage_key, _CAUVERY_SCORE["unknown"])
    rationale_by_key = {
        "stage_1":    "Cauvery Stage 1 — reliable BWSSB supply year-round.",
        "stage_2":    "Cauvery Stage 2 — generally reliable, occasional summer dips.",
        "stage_3":    "Cauvery Stage 3 — partial supply; expect 1–2 day gaps in summer.",
        "stage_4_p1": "Cauvery Stage 4 Phase 1 — limited supply; primarily borewell/tanker dependent.",
        "stage_4_p2": "Cauvery Stage 4 Phase 2 — minimal Cauvery; tanker dependence likely.",
        "outside":    "Outside Cauvery network — water comes from borewells or private tankers.",
        "unknown":    "Cauvery supply for this address couldn't be confirmed — using a neutral default.",
    }
    return score, rationale_by_key[stage_key]


def _groundwater_score(risk_key: str) -> Tuple[int, str]:
    score = _GROUNDWATER_SCORE.get(risk_key, _GROUNDWATER_SCORE["unknown"])
    rationale_by_key = {
        "low":     "Groundwater stress 'Low' — borewells should remain reliable.",
        "medium":  "Groundwater stress 'Medium' — borewells may struggle in peak summer.",
        "high":    "Groundwater stress 'High' — borewell failures common, especially May–June.",
        "unknown": "Groundwater conditions for this area aren't classified — using a neutral default.",
    }
    return score, rationale_by_key[risk_key]


def _building_signals_score(
    parsed: Optional[RentalListingSchema],
) -> Tuple[int, List[str]]:
    """
    Apply Tier-2 listing-text signals as a bounded modifier around a neutral
    baseline. Returns (sub_score, list_of_rationale_lines).
    """
    rationale: List[str] = []
    score = _BUILDING_SIGNALS_NEUTRAL

    if parsed is None:
        return score, ["No listing-level water signals to apply."]

    if parsed.cauvery_mentioned is True:
        score += 2
        rationale.append("Listing claims Cauvery water (+2).")
    if parsed.water_24x7 is True:
        score += 2
        rationale.append("Listing claims 24/7 / uninterrupted water (+2).")
    if parsed.rwh_mentioned is True:
        score += 1
        rationale.append("Listing mentions rainwater harvesting (+1).")
    if parsed.borewell_mentioned is True:
        score += 1
        rationale.append("Listing mentions borewell as backup source (+1).")
    if parsed.tanker_mentioned is True:
        score -= 3
        rationale.append("Listing acknowledges tanker dependence (−3).")

    score = max(_BUILDING_SIGNALS_MIN, min(_BUILDING_SIGNALS_MAX, score))
    if not rationale:
        rationale.append("Listing gave no water-related signals either way.")
    return score, rationale


# ----- Confidence + red flags ------------------------------------------------

def _confidence(
    stage_key: str,
    risk_key: str,
    parsed: Optional[RentalListingSchema],
) -> WaterConfidence:
    ward_known = stage_key != "unknown" or risk_key != "unknown"
    signals = parsed is not None and any(
        v is not None for v in (
            parsed.cauvery_mentioned,
            parsed.borewell_mentioned,
            parsed.water_24x7,
            parsed.rwh_mentioned,
            parsed.tanker_mentioned,
        )
    )
    if ward_known and signals:
        return "high"
    if ward_known or signals:
        return "medium"
    return "low"


def _red_flags(
    stage_key: str,
    risk_key: str,
    parsed: Optional[RentalListingSchema],
    ward_name: Optional[str],
    confidence: WaterConfidence,
    total: int,
) -> List[str]:
    """
    Differentiated, actionable red flags. Each one names the failure mode AND
    gives the user a concrete question to ask the broker. Order matters: the
    most decision-relevant flags come first.
    """
    flags: List[str] = []

    # Severe supply
    if stage_key in ("stage_4_p1", "stage_4_p2", "outside"):
        flags.append(
            "No reliable Cauvery supply — likely tanker/borewell dependent. "
            "Ask broker: 'What was last May's monthly water bill?'"
        )
    elif stage_key == "stage_3":
        flags.append(
            "Cauvery Stage 3 — supply may be inconsistent. "
            "Ask broker: 'How many days/week does Cauvery actually come?'"
        )

    # Groundwater
    if risk_key == "high":
        flags.append(
            "Groundwater stress 'High' in this area — borewell failure risk. "
            "Ask broker: 'How deep is the building's borewell? When was it last drilled?'"
        )

    # Honest tanker disclosure in listing
    if parsed and parsed.tanker_mentioned is True:
        flags.append(
            "Listing explicitly mentions tankers — confirms summer dependency. "
            "Ask broker: 'Tanker frequency in May vs December? Cost per load?'"
        )

    # Silent listing in a weak-supply area
    weak_supply = stage_key in ("stage_3", "stage_4_p1", "stage_4_p2", "outside")
    listing_silent = parsed is None or all(
        v is None for v in (
            parsed.cauvery_mentioned,
            parsed.borewell_mentioned,
            parsed.water_24x7,
            parsed.tanker_mentioned,
        )
    )
    if weak_supply and listing_silent:
        flags.append(
            "Listing doesn't mention water source despite area being supply-stressed. "
            "Ask broker: 'Cauvery, borewell, or tanker? 24/7 or scheduled hours?'"
        )

    # Outside GBA — water infrastructure is opaque
    if ward_name == "Outside GBA":
        flags.append(
            "Address is outside core GBA water network — building-level infrastructure varies. "
            "Verify supply source before signing."
        )

    # Generic low-confidence catch-all
    if confidence == "low":
        flags.append(
            "Low confidence in water score — couldn't map address to known data. "
            "Verify supply details with broker before signing."
        )

    return flags


# ----- Public entrypoint -----------------------------------------------------

def compute_water_score(
    cauvery_stage: Optional[str],
    water_risk_level: Optional[str],
    parsed_listing: Optional[RentalListingSchema],
    gba_ward_name: Optional[str],
) -> Tuple[WaterScoreBreakdown, List[str]]:
    """
    Compute the water sub-score breakdown + the list of red flags to surface
    on the scorecard.

    Returns (breakdown, red_flags). The caller is responsible for setting
    scorecard.water_score = breakdown.total and extending scorecard.red_flags.
    """
    stage_key = _normalize_stage(cauvery_stage)
    risk_key = _normalize_risk(water_risk_level)

    # Outside-GBA is a stronger signal than just "Unknown" — collapse to a
    # dedicated bucket so the rationale can flag it specifically.
    if gba_ward_name == "Outside GBA" and stage_key == "unknown":
        stage_key = "outside"

    cauvery_pts, cauvery_line = _cauvery_supply_score(stage_key)
    ground_pts, ground_line = _groundwater_score(risk_key)
    signal_pts, signal_lines = _building_signals_score(parsed_listing)

    total = cauvery_pts + ground_pts + signal_pts
    confidence = _confidence(stage_key, risk_key, parsed_listing)

    rationale: List[str] = [cauvery_line, ground_line, *signal_lines]
    red_flags = _red_flags(
        stage_key=stage_key,
        risk_key=risk_key,
        parsed=parsed_listing,
        ward_name=gba_ward_name,
        confidence=confidence,
        total=total,
    )

    breakdown = WaterScoreBreakdown(
        total=total,
        cauvery_supply=cauvery_pts,
        groundwater_resilience=ground_pts,
        building_signals=signal_pts,
        confidence=confidence,
        rationale=rationale,
    )
    return breakdown, red_flags


# Re-export for downstream consumers
__all__ = ["compute_water_score"]


# Silence the "imported but unused" warning for the LivabilityScorecard type
# hint above; keeping the import documents the contract.
_ = LivabilityScorecard
