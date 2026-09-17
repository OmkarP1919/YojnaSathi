import asyncio
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.main import get_voice_agent
from services.voice_agent.extractor import ProfileExtractor


async def main() -> None:
    print("=== 1. TESTING PROFILE EXTRACTOR & CONTEXT-AWARE YES/NO ===")
    extractor = ProfileExtractor()
    extraction_cases = [
        ("I am a farmer from Maharashtra", "farmer", "maharashtra"),
        ("मी महाराष्ट्रातील शेतकरी आहे", "farmer", "maharashtra"),
        ("मैं महाराष्ट्र का किसान हूँ", "farmer", "maharashtra"),
        ("मला farmer साठी government scheme पाहिजे", "farmer", None),
        ("मी नाशिकमध्ये शेती करतो", "farmer", "maharashtra"),
        ("I am an OBC student from Maharashtra", "student", "maharashtra"),
    ]
    for text, occupation, state in extraction_cases:
        extracted = await extractor.extract(text, {}, None)
        assert extracted.occupation == occupation, f"Failed occupation for '{text}': got {extracted.occupation}"
        assert extracted.state == state, f"Failed state for '{text}': got {extracted.state}"

    # Context-aware yes/no and phrase extraction
    owns_land_true = await extractor.extract("माझ्याकडे शेतजमीन आहे", {}, None)
    assert owns_land_true.owns_land is True, "Expected owns_land=True from 'माझ्याकडे शेतजमीन आहे'"

    owns_land_false = await extractor.extract("माझ्याकडे जमीन नाही", {}, None)
    assert owns_land_false.owns_land is False, "Expected owns_land=False from 'माझ्याकडे जमीन नाही'"

    owns_house_true = await extractor.extract("माझ्याकडे पक्के घर आहे", {}, None)
    assert owns_house_true.owns_house is True, "Expected owns_house=True from 'माझ्याकडे पक्के घर आहे'"

    owns_house_false = await extractor.extract("नाही, माझ्याकडे पक्के घर नाही", {}, "owns_house")
    assert owns_house_false.owns_house is False, "Expected owns_house=False from 'नाही, माझ्याकडे पक्के घर नाही'"

    # Ordinary occurrence of "आहे" must NOT answer unrelated question
    unrelated_ahe = await extractor.extract("माझे वय ३५ आहे", {}, "owns_house")
    assert unrelated_ahe.owns_house is None, "Expected owns_house=None when user only states 'माझे वय ३५ आहे'"

    # Proactive income extraction
    income_info = await extractor.extract("माझे वार्षिक उत्पन्न २.५ लाख आहे", {}, None)
    assert income_info.annual_income == 250000.0, f"Expected 250000.0 income, got {income_info.annual_income}"

    # Social category Devanagari aliases
    ebc_info = await extractor.extract("मी ईबीसी प्रवर्गात मोडतो", {}, "social_category")
    assert ebc_info.social_category == "ebc", f"Expected 'ebc', got {ebc_info.social_category}"
    dnt_info = await extractor.extract("डीएनटी", {}, "social_category")
    assert dnt_info.social_category == "dnt", f"Expected 'dnt', got {dnt_info.social_category}"

    print("✓ Extractor tests & context-aware yes/no passed successfully.")

    print("\n=== 2. TESTING EMPTY INPUT (BUG 1 REGRESSION) ===")
    agent = get_voice_agent()
    empty_res = await agent.process("empty-test", "")
    assert empty_res["next_action"] == "ask_question"
    assert "Please tell me" in empty_res["response_text"] or len(empty_res["response_text"]) > 0
    print("✓ Empty input handled safely without UnboundLocalError.")

    print("\n=== 3. TESTING MULTILINGUAL & MULTI-TURN SCHEME RETRIEVAL (BUG 2 REGRESSION) ===")
    # Marathi Farmer multi-turn
    r_mr1 = await agent.process("farmer-mr", "मला शेतीसाठी योजना पाहिजे")
    assert r_mr1["language"] == "mr", f"Expected mr, got {r_mr1['language']}"
    r_mr2 = await agent.process("farmer-mr", "महाराष्ट्र")
    assert r_mr2["language"] == "mr", f"Expected mr, got {r_mr2['language']}"
    res_mr = await agent.process("farmer-mr", "होय, माझ्याकडे शेतजमीन आहे")
    assert res_mr["language"] == "mr", f"Expected mr, got {res_mr['language']}"
    assert res_mr["next_action"] == "completed"
    assert len(res_mr["schemes"]) > 0, "Expected schemes for Marathi farmer"
    # Ensure scheme name is a localized string, not raw dictionary repr
    assert isinstance(res_mr["schemes"][0]["name"], str)
    assert not res_mr["schemes"][0]["name"].startswith("{"), "Scheme name should not be raw dict"
    # Assert response text is genuinely in Marathi
    assert any(w in res_mr["response_text"] for w in ("योजना", "सापडली", "सापडल्या", "पात्रता")), "Response should be in Marathi"
    assert "मिलीं" not in res_mr["response_text"], "Hindi text should not appear in Marathi response"
    print(f"✓ Marathi Farmer Response:\n{res_mr['response_text']}\n")

    # Hindi Farmer multi-turn
    r_hi1 = await agent.process("farmer-hi", "मुझे किसानों के लिए योजना चाहिए")
    assert r_hi1["language"] == "hi", f"Expected hi, got {r_hi1['language']}"
    r_hi2 = await agent.process("farmer-hi", "महाराष्ट्र")
    assert r_hi2["language"] == "hi", f"Expected hi, got {r_hi2['language']}"
    res_hi = await agent.process("farmer-hi", "हाँ, मेरे पास जमीन है")
    assert res_hi["language"] == "hi", f"Expected hi, got {res_hi['language']}"
    assert res_hi["next_action"] == "completed"
    assert len(res_hi["schemes"]) > 0, "Expected schemes for Hindi farmer"
    # Assert response text is genuinely in Hindi, NOT Marathi!
    assert any(w in res_hi["response_text"] for w in ("योजनाएं", "मिलीं", "उपयुक्त", "जांचें")), "Response must be in Hindi"
    assert "सापडल्या" not in res_hi["response_text"], "Marathi text must not leak into Hindi response"
    print(f"✓ Hindi Farmer Response:\n{res_hi['response_text']}\n")

    print("\n=== 4. TESTING TENANT / LANDLESS FARMER (PMFBY preserved, PM-KISAN excluded) ===")
    await agent.process("tenant-farmer", "I am a farmer")
    await agent.process("tenant-farmer", "Maharashtra")
    res_tenant = await agent.process("tenant-farmer", "no")
    assert res_tenant["language"] == "en"
    scheme_ids = [s["id"] for s in res_tenant["schemes"]]
    assert "pmfby" in scheme_ids, "PMFBY should be recommended for tenant farmer"
    assert "pm-kisan" not in scheme_ids, "PM-KISAN must be excluded for farmer without land"
    print(f"✓ Tenant farmer schemes: {scheme_ids} (PMFBY present, PM-KISAN excluded).")

    print("\n=== 5. TESTING EDUCATION DOMAIN & SOCIAL CATEGORY QUESTION CONSISTENCY ===")
    # English flow
    await agent.process("student-test", "I am a student needing scholarship")
    res_edu2 = await agent.process("student-test", "Maharashtra")
    # Verify all 6 categories in English question
    assert all(cat in res_edu2["response_text"] for cat in ["General", "SC", "ST", "OBC", "EBC", "DNT"]), \
        f"English question missing categories: {res_edu2['response_text']}"
    res_edu3 = await agent.process("student-test", "OBC")
    # Criteria-aware planner now asks annual income (education schemes are income-gated)
    assert "earn" in res_edu3["response_text"].lower() or "income" in res_edu3["response_text"].lower(), \
        f"Expected annual income question after social category: {res_edu3['response_text']}"
    res_edu4 = await agent.process("student-test", "2 lakh")
    edu_scheme_ids = [s["id"] for s in res_edu4["schemes"]]
    assert "pm-yasasvi" in edu_scheme_ids, "PM-YASASVI should be recommended for OBC student"
    # Ensure no cross-domain schemes leaked
    for s in res_edu4["schemes"]:
        assert s["category"] == "education", f"Leaked non-education scheme: {s['id']}"
        assert "reason_codes" in s, "Scheme object must include reason_codes"
    print(f"✓ Student schemes: {edu_scheme_ids} (Clean category filtering).")

    # Hindi question consistency test
    await agent.process("student-hi", "मुझे पढ़ाई के लिए छात्रवृत्ति चाहिए")
    res_hi_edu2 = await agent.process("student-hi", "महाराष्ट्र")
    assert all(cat in res_hi_edu2["response_text"] for cat in ["General", "SC", "ST", "OBC", "EBC", "DNT"]), \
        f"Hindi question missing categories: {res_hi_edu2['response_text']}"
    print("✓ Hindi social category question contains General, SC, ST, OBC, EBC, DNT.")

    # Marathi question consistency test
    await agent.process("student-mr", "मला शिक्षणासाठी शिष्यवृत्ती पाहिजे")
    res_mr_edu2 = await agent.process("student-mr", "महाराष्ट्र")
    assert all(cat in res_mr_edu2["response_text"] for cat in ["General", "SC", "ST", "OBC", "EBC", "DNT"]), \
        f"Marathi question missing categories: {res_mr_edu2['response_text']}"
    print("✓ Marathi social category question contains General, SC, ST, OBC, EBC, DNT.")

    print("\n=== 6. TESTING HOUSING MULTI-TURN FLOW (REQUIREMENT 5) ===")
    # Housing intent -> state -> rural/urban -> owns_house
    await agent.process("housing-test", "I need a scheme for housing")
    res_h2 = await agent.process("housing-test", "Maharashtra")
    assert res_h2["next_action"] == "ask_question"
    assert "rural" in res_h2["response_text"].lower() or "urban" in res_h2["response_text"].lower()

    res_h3 = await agent.process("housing-test", "rural")
    assert res_h3["next_action"] == "ask_question"
    assert "pucca" in res_h3["response_text"].lower() or "house" in res_h3["response_text"].lower()

    res_h4 = await agent.process("housing-test", "no, I do not have a pucca house")
    assert res_h4["next_action"] == "completed"
    assert res_h4["profile"].get("rural_or_urban") == "rural"
    assert res_h4["profile"].get("owns_house") is False

    housing_schemes = res_h4["schemes"]
    assert len(housing_schemes) > 0, "Expected housing schemes for rural homeless citizen"
    housing_ids = [s["id"] for s in housing_schemes]
    assert "pmay-g" in housing_ids, "PMAY-G should be recommended for rural citizen without pucca house"
    assert "pmay-u" not in housing_ids, "PMAY-U must be excluded for rural citizen"

    for s in housing_schemes:
        assert s["category"] == "housing", f"Leaked non-housing scheme: {s['id']}"
        assert len(s["reason_codes"]) > 0, f"Scheme {s['id']} should have reason_codes"
        assert isinstance(s["name"], str), "Scheme name should be localized string"
        assert isinstance(s["benefits"], list), "Scheme benefits should be localized list"

    print(f"✓ Housing multi-turn verified: {housing_ids} (PMAY-G matched, PMAY-U excluded, no leakage).")

    print("\n=== 7. TESTING UNRECOGNIZED NEED & ZERO-MATCH QUERY ===")
    no_intent = await agent.process("no-intent", "I need a scheme for space tourism")
    assert not no_intent["schemes"]
    assert no_intent["next_action"] == "ask_question"
    assert "farming" in no_intent["response_text"].lower() or "शेती" in no_intent["response_text"]
    print(f"✓ Unrecognized intent prompted user: {no_intent['response_text']}")

    print("\n=== 8. TESTING SESSION RESET ===")
    agent.reset("farmer-mr")
    assert "farmer-mr" not in agent.sessions
    print("✓ Session reset verified.")

    print("\nALL VOICE AGENT TESTS PASSED SUCCESSFULLY!")


def test_voice_agent_complete_suite() -> None:
    asyncio.run(main())

if __name__ == "__main__":
    asyncio.run(main())
