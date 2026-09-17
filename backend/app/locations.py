import json
import logging
from pathlib import Path
from typing import List, Optional

from app.schemas import ApplicationLocation

logger = logging.getLogger("yojnasathi.locations")
LOCATIONS_PATH = Path(__file__).resolve().parent.parent / "data" / "locations.json"

_CACHED_LOCATIONS: Optional[List[ApplicationLocation]] = None


def load_locations_data(reload: bool = False) -> List[ApplicationLocation]:
    """Load and parse locations data from data/locations.json."""
    global _CACHED_LOCATIONS
    if _CACHED_LOCATIONS is not None and not reload:
        return _CACHED_LOCATIONS

    if not LOCATIONS_PATH.exists():
        logger.warning("Locations file does not exist at %s", LOCATIONS_PATH)
        _CACHED_LOCATIONS = []
        return _CACHED_LOCATIONS

    try:
        with open(LOCATIONS_PATH, "r", encoding="utf-8") as f:
            raw_locations = json.load(f)
        _CACHED_LOCATIONS = [ApplicationLocation(**item) for item in raw_locations]
    except Exception as exc:
        logger.error("Failed to load locations from %s: %s", LOCATIONS_PATH, exc)
        _CACHED_LOCATIONS = []

    return _CACHED_LOCATIONS


def _matches_scheme(scheme_id: str, location_scheme_ids: List[str]) -> bool:
    target = scheme_id.strip().lower()
    for sid in location_scheme_ids:
        cleaned = sid.strip().lower()
        if cleaned == "*" or cleaned == target:
            return True
    return False


def find_locations(
    scheme_id: str,
    state: Optional[str],
    district: Optional[str] = None,
    taluka: Optional[str] = None,
    locations_pool: Optional[List[ApplicationLocation]] = None,
) -> List[ApplicationLocation]:
    """
    Deterministically find physical application locations for a scheme and citizen jurisdiction.

    Matching hierarchy:
    1. Filter by scheme + state compatibility.
    2. If taluka is supplied, prefer exact taluka matches.
    3. If no taluka match exists, fall back to matching district-level offices.
    4. If no district-specific location exists, fall back to broader state-level headquarters
       (where district is None and taluka is None).
    5. If none match, return an empty list.

    Never fabricates or assumes a location.
    """
    if not state or not scheme_id:
        return []

    s_id = scheme_id.strip().lower()
    s_state = state.strip().lower()
    s_dist = district.strip().lower() if district and district.strip() else None
    s_tal = taluka.strip().lower() if taluka and taluka.strip() else None

    pool = locations_pool if locations_pool is not None else load_locations_data()

    # Step 1: Filter by state and scheme compatibility
    candidates: List[ApplicationLocation] = []
    for loc in pool:
        if loc.state.strip().lower() != s_state:
            continue
        if not _matches_scheme(s_id, loc.scheme_ids):
            continue
        candidates.append(loc)

    if not candidates:
        return []

    # Step 2: Exact taluka match
    if s_tal:
        taluka_matches = [
            loc for loc in candidates
            if loc.taluka and loc.taluka.strip().lower() == s_tal
            and (s_dist is None or (loc.district and loc.district.strip().lower() == s_dist))
        ]
        if taluka_matches:
            return taluka_matches

    # Step 3: District fallback
    if s_dist:
        district_matches = [
            loc for loc in candidates
            if loc.district and loc.district.strip().lower() == s_dist
            and (loc.taluka is None or loc.taluka.strip() == "")
        ]
        if district_matches:
            return district_matches

    # Step 4: Broader state-level location (district=None, taluka=None)
    state_matches = [
        loc for loc in candidates
        if (loc.district is None or loc.district.strip() == "")
        and (loc.taluka is None or loc.taluka.strip() == "")
    ]
    if state_matches:
        return state_matches

    return []
