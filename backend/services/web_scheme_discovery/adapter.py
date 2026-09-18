"""Adapter module to convert validated DiscoveredScheme objects into canonical Scheme models."""
from __future__ import annotations

from datetime import datetime, timezone
import logging
import re
from typing import List, Optional, Set

from app.schemas import (
    ApplicationGuidance,
    LocalizedList,
    LocalizedString,
    OfflineApplication,
    OnlineApplication,
    Scheme,
)
from services.web_scheme_discovery.deduplicator import normalize_name
from services.web_scheme_discovery.schemas import DiscoveredScheme

logger = logging.getLogger("yojnasathi.web_discovery.adapter")

CATEGORY_KEYWORD_RULES = [
    ("agriculture", ["farm", "kisan", "crop", "fasal", "cultivat", "krishi", "agriculture", "fertilizer", "tractor", "seed"]),
    ("education", ["student", "scholarship", "vidyarthi", "school", "college", "tuition", "education", "study", "exam", "hostel"]),
    ("health", ["health", "hospital", "arogya", "ayushman", "treatment", "medical", "disease", "patient", "medicine", "doctor", "clinic"]),
    ("housing", ["house", "housing", "awas", "awaas", "pucca", "shelter", "homeless", "home construction"]),
    ("women", ["woman", "women", "mahila", "girl", "ladki", "bahin", "mother", "maternity", "pregnant", "widow", "kanya", "beti"]),
    ("small businesses", ["business", "vendor", "entrepreneur", "svanidhi", "micro enterprise", "shopkeeper", "self-employed", "artisan", "vishwakarma", "loan for business"]),
    ("employment", ["employment", "job", "mgnrega", "nrega", "rozgar", "wage", "skill", "training", "unemployed", "worker", "labor"]),
    ("insurance", ["insurance", "bima", "pension", "accidental cover", "life cover"]),
    ("financial inclusion", ["bank", "savings", "jan dhan", "zero balance", "account opening"]),
    ("social welfare", ["social welfare", "tribal", "sc/st", "divyang", "disability", "differently abled", "destitute"]),
]

TARGET_GROUP_RULES = [
    ({"farmers", "rural citizens"}, ["farmer", "kisan", "cultivat", "landholding", "rural"]),
    ({"students", "youth"}, ["student", "scholarship", "youth", "school", "college"]),
    ({"women"}, ["woman", "women", "female", "girl", "ladki", "mother", "maternity", "pregnant", "widow", "kanya"]),
    ({"street vendors", "small business owners"}, ["street vendor", "vendor", "small business", "entrepreneur", "self-employed", "artisan", "shop"]),
    ({"unorganized sector workers"}, ["unorganized", "daily wage", "laborer", "unskilled", "worker", "contract worker"]),
    ({"low-income households"}, ["bpl", "low income", "poor", "below poverty line", "economically weaker", "ews"]),
]


def discovered_to_canonical_scheme(
    candidate: DiscoveredScheme,
    fallback_category: Optional[str] = None,
) -> Scheme:
    """
    Convert a verified, active DiscoveredScheme into a canonical Scheme model.

    safety & Determinism Rules:
    - Rejects unverified or inactive candidates.
    - Preserves discovered text, URLs, and state scoping.
    - Derives eligibility_criteria ONLY for official portal catalogues (e.g.
      MahaDBT), and only from the official detail-page text via a generic parser.
      Candidates from secondary/search sources keep eligibility_criteria=None:
      fabricating constraints from unstructured snippets is never allowed.
    - Derives category and target_groups conservatively from evidence text.
    """
    if candidate.validation_status != "verified" or candidate.active_status != "active":
        raise ValueError(
            f"Only verified and active discovered schemes can be converted to canonical Scheme. "
            f"Got validation_status={candidate.validation_status!r}, active_status={candidate.active_status!r}"
        )

    # 1. Deterministic collision-safe ID
    norm = candidate.normalized_name or normalize_name(candidate.scheme_name)
    slug = re.sub(r"[^a-z0-9]+", "-", norm.lower()).strip("-")
    scheme_id = f"web-{slug}" if slug else f"web-scheme-{abs(hash(candidate.scheme_name))}"

    # 2. Combined text for conservative keyword scanning
    combined_text = " ".join([
        candidate.scheme_name or "",
        candidate.description or "",
        " ".join(candidate.benefits or []),
        " ".join(candidate.eligibility or []),
        " ".join(candidate.application_process or []),
        " ".join(candidate.documents_required or []),
    ]).lower()

    # 3. State scoping: central/all-India -> "all-india", state -> normalized state
    gov_level = (candidate.government_level or "").lower().strip()
    cand_type = (candidate.scheme_type or "").lower().strip()
    cand_state = (candidate.state or "").lower().strip()

    if (
        gov_level == "central"
        or cand_type == "central"
        or not cand_state
        or cand_state in ("all-india", "all india", "india", "central")
    ):
        state = "all-india"
    else:
        state = cand_state

    # 4. Conservative Category Derivation using weighted frequency
    category_scores: dict[str, int] = {}
    name_lower = (candidate.scheme_name or "").lower()
    for cat_name, keywords in CATEGORY_KEYWORD_RULES:
        score = 0
        for kw in keywords:
            if kw in name_lower:
                score += 3  # Strong weight for scheme name mentions
            if kw in combined_text:
                score += 1
        if score > 0:
            category_scores[cat_name] = score

    derived_category: Optional[str] = None
    if category_scores:
        derived_category = max(category_scores.items(), key=lambda item: item[1])[0]

    # Never inherit the citizen's selected UI category (fallback_category) when
    # the scheme's own evidence has no category match: doing so mislabels
    # unrelated schemes (e.g. Marathi-transliterated education/hostel schemes)
    # as e.g. "women". Schemes without recognizable domain evidence stay under
    # the neutral "social welfare" bucket instead.
    if not derived_category:
        derived_category = "social welfare"

    # 5. Conservative Target Groups Derivation
    target_groups_set: Set[str] = set()
    for tg_group, keywords in TARGET_GROUP_RULES:
        if any(kw in combined_text for kw in keywords):
            target_groups_set.update(tg_group)

    target_groups = sorted(target_groups_set)

    # 6. Localized fields
    name: LocalizedString = {
        "en": candidate.scheme_name,
        "hi": candidate.scheme_name,
        "mr": candidate.scheme_name,
    }

    desc = (candidate.description or "").strip()
    description: LocalizedString = {
        "en": desc,
        "hi": desc,
        "mr": desc,
    }

    benefits_list = list(candidate.benefits) if candidate.benefits else []
    benefits: LocalizedList = {
        "en": benefits_list,
        "hi": benefits_list,
        "mr": benefits_list,
    }

    elig_list = list(candidate.eligibility) if candidate.eligibility else []
    eligibility: LocalizedList = elig_list

    docs_list = list(candidate.documents_required) if candidate.documents_required else []
    required_information: LocalizedList = {
        "en": docs_list,
        "hi": docs_list,
        "mr": docs_list,
    }

    department: LocalizedString = {
        "en": "Official Government Department",
        "hi": "आधिकारिक सरकारी विभाग",
        "mr": "अधिकृत सरकारी विभाग",
    }

    app_url = (candidate.application_url or candidate.source_url or "").strip()
    src_url = (candidate.source_url or candidate.application_url or "").strip()
    last_verified = candidate.last_verified or datetime.now(timezone.utc).isoformat()

    portal_name = None
    if app_url:
        host = app_url.split("//")[-1].split("/")[0].lower()
        if host.startswith("www."):
            host = host[4:]
        portal_name = host or None

    custom_guidance = None
    app_proc_text = " ".join(candidate.application_process or []).strip()
    if app_proc_text:
        from app.location_search import AuthorityExtractionParser
        auth_res = AuthorityExtractionParser.parse_text(app_proc_text)
        channel = None
        if "citizen_service_center" in auth_res.designated_authorities:
            channel = "CSC / Maha e-Seva / Setu Kendra"
        elif "tahsil_office" in auth_res.designated_authorities:
            channel = "Tahsil Office"
        elif "district_agriculture_office" in auth_res.designated_authorities:
            channel = "District Agriculture Office"
        elif "civil_hospital" in auth_res.designated_authorities:
            channel = "Civil Hospital"

        custom_guidance = ApplicationGuidance(
            documents_required=required_information,
            online_application=OnlineApplication(
                available=bool(app_url),
                portal_name=portal_name,
                portal_url=app_url or None,
            ),
            offline_application=OfflineApplication(
                available=bool(channel or app_proc_text),
                authorized_channel=channel,
                instructions=app_proc_text,
            ),
        )

    # 7. Structured eligibility only for official-portal catalogues whose detail
    #    text was parsed by the service layer (never from secondary snippets).
    eligibility_criteria = None
    if candidate.source_type == "official_government_portal":
        from services.web_scheme_discovery.eligibility_parser import (
            derive_eligibility_criteria,
        )

        eligibility_criteria = derive_eligibility_criteria(
            name=candidate.scheme_name,
            eligibility_lines=candidate.eligibility,
            overview=candidate.description,
            benefits=candidate.benefits,
        )

    return Scheme(
        id=scheme_id,
        name=name,
        description=description,
        category=derived_category,
        target_groups=target_groups,
        benefits=benefits,
        eligibility=eligibility,
        required_information=required_information,
        state=state,
        department=department,
        application_url=app_url,
        source_url=src_url,
        last_verified=last_verified,
        eligibility_criteria=eligibility_criteria,
        custom_application_guidance=custom_guidance,
    )
