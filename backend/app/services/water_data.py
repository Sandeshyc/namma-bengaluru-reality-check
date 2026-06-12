import csv
import logging
from pathlib import Path
import difflib

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
CSV_PATH = BASE_DIR / "data" / "raw" / "groundwater_risk.csv"

class WaterDataManager:
    def __init__(self):
        self.mapping = {}
        self._load_data()

    def _load_data(self):
        if not CSV_PATH.exists():
            logger.warning(f"Water dataset not found at {CSV_PATH}")
            return
            
        try:
            with open(CSV_PATH, 'r', encoding='latin-1') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    for stage, area in row.items():
                        if area and area.strip():
                            # Assign risk based on stage heuristic
                            stg = stage.strip()
                            if stg in ["Cauvery Stage 1", "Stage 2"]:
                                risk = "Low"
                            elif stg == "Stage 3":
                                risk = "Medium"
                            elif stg in ["Stage 4 Ph 1", "Stage 4 Phase 2"]:
                                risk = "High"
                            else:
                                risk = "Unknown"
                                
                            self.mapping[area.strip().lower()] = {
                                "stage": stg,
                                "risk": risk
                            }
            logger.info(f"Loaded {len(self.mapping)} colloquial water mapping areas.")
        except Exception as e:
            logger.error(f"Failed to load water data CSV: {e}")

    def fuzzy_match_location(self, raw_location: str) -> dict:
        """Find the closest matching water stage using curated fallbacks, then fuzzy string matching."""
        if not raw_location:
            return None
            
        loc_lower = raw_location.lower()
        
        # 0. Curated Major Neighborhood Fallbacks (Highest Priority)
        # The raw BWSSB CSV often lists specific expansion layouts/slums, which causes
        # fuzzy matching to misidentify core areas (e.g. matching "Indiranagar slum" in Stage 4 
        # instead of core Indiranagar in Stage 1).
        curated_fallbacks = {
            "indiranagar": {"stage": "Cauvery Stage 1", "risk": "Low"},
            "indira nagar": {"stage": "Cauvery Stage 1", "risk": "Low"},
            "koramangala": {"stage": "Cauvery Stage 1", "risk": "Low"},
            "kormangala": {"stage": "Cauvery Stage 1", "risk": "Low"},
            "jayanagar": {"stage": "Cauvery Stage 1", "risk": "Low"},
            "malleswaram": {"stage": "Cauvery Stage 1", "risk": "Low"},
            "malleshwaram": {"stage": "Cauvery Stage 1", "risk": "Low"},
            "basavanagudi": {"stage": "Cauvery Stage 1", "risk": "Low"},
            "banashankari": {"stage": "Cauvery Stage 1", "risk": "Low"},
            "rajajinagar": {"stage": "Cauvery Stage 1", "risk": "Low"},
            "vijayanagar": {"stage": "Cauvery Stage 1", "risk": "Low"},
            "hsr": {"stage": "Stage 3", "risk": "Medium"},
            "btm": {"stage": "Stage 3", "risk": "Medium"},
            "sarjapur": {"stage": "Stage 3", "risk": "Medium"},
            "bellandur": {"stage": "Stage 3", "risk": "Medium"},
            "whitefield": {"stage": "Stage 4 Phase 2", "risk": "High"},
            "marathahalli": {"stage": "Stage 4 Ph 1", "risk": "High"},
            "electronic city": {"stage": "Stage 4 Phase 2", "risk": "High"},
            "hebbal": {"stage": "Stage 4 Phase 1", "risk": "Medium"},
            "yelahanka": {"stage": "Stage 4 Phase 2", "risk": "High"},
        }
        
        # Test full string, then first chunk, then first word (Progressive stripping)
        first_chunk = loc_lower.split(',')[0].strip()
        first_word = loc_lower.split()[0].replace(',', '').strip()
        
        test_strings = [loc_lower, first_chunk, first_word]
        
        # 1. Curated Fallback Check
        for test_str in test_strings:
            for key, data in curated_fallbacks.items():
                if key in test_str:
                    return data
                
        if not self.mapping:
            return None
            
        # 2. Direct substring match against CSV
        for test_str in test_strings:
            for area, data in self.mapping.items():
                if area in test_str or test_str in area:
                    return data
                
        # 3. Fuzzy match fallback against CSV
        areas = list(self.mapping.keys())
        for test_str in test_strings:
            # Skip fuzzy matching on extremely short strings to avoid false positives
            if len(test_str) < 4: continue
            matches = difflib.get_close_matches(test_str, areas, n=1, cutoff=0.7)
            if matches:
                return self.mapping[matches[0]]
            
        return None

# Singleton
water_db = WaterDataManager()
