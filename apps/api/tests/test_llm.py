from app.cache import MemoryCache
from app.config import Settings
from app.llm import LLMClient


def test_identical_prompts_hit_the_cache():
    calls = {"n": 0}

    def transport(system, user):
        calls["n"] += 1
        return "briefing"

    client = LLMClient(Settings(vertex_llm_api_key=""), MemoryCache(), transport=transport)
    first = client.complete("system", "user")
    second = client.complete("system", "user")
    assert first == ("briefing", False)
    assert second == ("briefing", True)
    assert calls["n"] == 1
