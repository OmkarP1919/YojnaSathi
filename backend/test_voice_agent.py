import asyncio
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.main import get_voice_agent
from services.voice_agent.extractor import ProfileExtractor


async def main() -> None:
    extractor = ProfileExtractor()
    extraction_cases = [
        ("I am a farmer from Maharashtra", "farmer", "maharashtra"),
        ("मी महाराष्ट्रातील शेतकरी आहे", "farmer", "maharashtra"),
        ("मैं महाराष्ट्र का किसान हूँ", "farmer", "maharashtra"),
        ("मला farmer साठी government scheme पाहिजे", "farmer", None),
        ("मी नाशिकमध्ये शेती करतो", "farmer", "maharashtra"),
    ]
    for text, occupation, state in extraction_cases:
        extracted = await extractor.extract(text, {}, None)
        assert extracted.occupation == occupation
        assert extracted.state == state

    agent = get_voice_agent()

    examples = [
        ("english", "I am a farmer from Maharashtra"),
        ("marathi", "\u092e\u0932\u093e \u0936\u0947\u0924\u0915\u0931\u094d\u092f\u093e\u0902\u0938\u093e\u0920\u0940 \u0938\u0930\u0915\u093e\u0930\u0940 \u092f\u094b\u091c\u0928\u093e \u092a\u093e\u0939\u093f\u091c\u0947"),
        ("hindi", "\u092e\u0941\u091d\u0947 \u0915\u093f\u0938\u093e\u0928\u094b\u0902 \u0915\u0947 \u0932\u093f\u090f \u0938\u0930\u0915\u093e\u0930\u0940 \u092f\u094b\u091c\u0928\u093e \u091a\u093e\u0939\u093f\u090f"),
    ]
    for name, text in examples:
        result = await agent.process(f"demo-{name}", text)
        print(f"{name}: [{result['language']}] {result['response_text']}")

    first = await agent.process("multi-turn", "I need a scheme")
    second = await agent.process("multi-turn", "farming")
    assert first["next_action"] == "ask_question"
    assert second["next_action"] == "ask_question"

    await agent.process("profile-memory", "मला सरकारी योजना पाहिजे")
    await agent.process("profile-memory", "मी शेतकरी आहे")
    await agent.process("profile-memory", "महाराष्ट्र")
    profile = agent.sessions["profile-memory"]["user_profile"]
    assert profile.occupation == "farmer"
    assert profile.state == "maharashtra"

    no_match = await agent.process("no-match", "I need a scheme for space tourism")
    assert not no_match["schemes"]
    print(f"no-match: {no_match['response_text']}")


if __name__ == "__main__":
    asyncio.run(main())
