"""
Location requirements evaluator for YojnaSathi.

Evaluates citizen profiles against matched schemes to determine whether location
information is required for:
1. Eligibility confirmation (state-specific schemes where state is missing)
2. Physical application guidance (resolving physical offices from cataloged locations)

Deterministic and decoupled from matching and client interfaces.
"""
from typing import List, Optional, Set
from app.locations import _matches_scheme, load_locations_data
from app.schemas import ApplicationLocation, CitizenProfile, LocationRequirement, SchemeMatchResult


def evaluate_location_requirement(
    profile: CitizenProfile,
    matched_schemes: List[SchemeMatchResult],
    locations_pool: Optional[List[ApplicationLocation]] = None,
) -> LocationRequirement:
    """
    Deterministically evaluates if and what location information is needed.

    - Distinguishes eligibility requirement (State) from application guidance (District/Taluka).
    - Checks whether cataloged physical offices exist for the matched schemes.
    - Guides clients on the next missing location level ("state" | "district" | "taluka" | None).
    """
    req = LocationRequirement()

    if not matched_schemes:
        return req

    # -------------------------------------------------------------
    # 1. State Requirement for Eligibility
    # -------------------------------------------------------------
    # Check if any candidate/matched scheme is state-specific
    state_specific_schemes = [
        r.scheme for r in matched_schemes
        if r.scheme.state and r.scheme.state.strip().lower() != "all-india"
    ]

    profile_state = profile.state.strip().lower() if profile.state and profile.state.strip() else None

    if state_specific_schemes and not profile_state:
        req.state_required_for_eligibility = True
        req.next_needed_level = "state"

    # -------------------------------------------------------------
    # 2. Physical Application Guidance Check
    # -------------------------------------------------------------
    pool = locations_pool if locations_pool is not None else load_locations_data()
    matched_scheme_ids = {r.scheme.id.strip().lower() for r in matched_schemes}

    # Find physical locations matching any matched scheme
    relevant_locs = [
        loc for loc in pool
        if any(_matches_scheme(sid, loc.scheme_ids) for sid in matched_scheme_ids)
    ]

    if not relevant_locs:
        req.has_physical_offices = False
        return req

    # If state is not provided:
    if not profile_state:
        # Relevant offices exist in the database (e.g. Maharashtra), but user has not given a state yet
        req.has_physical_offices = True
        if not req.next_needed_level:
            req.next_needed_level = "state"
        return req

    # Filter locations for user's specific state
    state_locs = [
        loc for loc in relevant_locs
        if loc.state.strip().lower() == profile_state
    ]

    if not state_locs:
        # No physical offices cataloged for this state
        req.has_physical_offices = False
        if not req.state_required_for_eligibility:
            req.next_needed_level = None
        return req

    req.has_physical_offices = True

    # Cataloged districts in this state for the matched schemes
    supported_districts = sorted({
        loc.district.strip().lower()
        for loc in state_locs
        if loc.district and loc.district.strip()
    })
    req.supported_districts = supported_districts

    profile_dist = (
        profile.district.strip().lower()
        if profile.district and profile.district.strip() and profile.district.strip().lower() != "other"
        else None
    )

    if not profile_dist:
        # User has not provided district yet
        if supported_districts:
            req.next_needed_level = "district"
        else:
            # Only broader state-level offices exist (district=None)
            req.next_needed_level = None
        return req

    # District is provided: inspect offices in this district
    dist_locs = [
        loc for loc in state_locs
        if loc.district and loc.district.strip().lower() == profile_dist
    ]

    if not dist_locs:
        # User's district is outside cataloged physical offices
        req.next_needed_level = None
        return req

    # Check if there are taluka-specific offices for this district and schemes
    supported_talukas = sorted({
        loc.taluka.strip().lower()
        for loc in dist_locs
        if loc.taluka and loc.taluka.strip() and loc.taluka.strip().lower() != "other"
    })
    req.supported_talukas = supported_talukas

    profile_tal = (
        profile.taluka.strip().lower()
        if profile.taluka and profile.taluka.strip() and profile.taluka.strip().lower() != "other"
        else None
    )

    if supported_talukas:
        if not profile_tal:
            req.next_needed_level = "taluka"
        else:
            req.next_needed_level = None
    else:
        # Only district-level offices exist (taluka=None)
        # Do not unnecessarily request taluka
        req.next_needed_level = None

    return req
