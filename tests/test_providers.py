"""Offline provider tests: payload construction, provider-quirk handling, registry
resolution, and missing-key behaviour. No network — we test the request we *would*
send, which is where the hard-won provider knowledge actually lives."""
import pytest

from aieasybatch.providers.anthropic import AnthropicProvider
from aieasybatch.providers.gemini import GeminiProvider
from aieasybatch.providers.openai_compat import OpenAICompatProvider
from aieasybatch.record import Sampling
from aieasybatch.registry import get_provider
from aieasybatch.roster import parse_model

USER = [{"role": "user", "content": "hi"}]


def test_openai_compat_standard_payload():
    p = OpenAICompatProvider("gpt-4o-mini", base_url="http://x/v1", key_env=None)
    body = p._payload(USER, Sampling(temperature=0.7, top_p=0.9, max_tokens=100, seed=5))
    assert body["model"] == "gpt-4o-mini"
    assert body["temperature"] == 0.7 and body["max_tokens"] == 100
    assert body["top_p"] == 0.9 and body["seed"] == 5
    assert "max_completion_tokens" not in body


def test_openai_compat_reasoning_quirks():
    p = OpenAICompatProvider("gpt-5", base_url="http://x/v1", key_env=None, reasoning_effort="low")
    body = p._payload(USER, Sampling(temperature=0.7, top_p=0.5, max_tokens=2000))
    assert body["max_completion_tokens"] == 2000 and "max_tokens" not in body
    assert "temperature" not in body and "top_p" not in body   # reasoning models reject them
    assert body["reasoning_effort"] == "low"


def test_openai_compat_detects_reasoning_behind_vendor_prefix():
    p = OpenAICompatProvider("openai/o3-mini", base_url="http://x/v1", key_env=None)
    assert p._is_reasoning() is True


def test_openai_compat_missing_key_raises():
    with pytest.raises(ValueError):
        OpenAICompatProvider("gpt-4o-mini", base_url="https://api.openai.com/v1",
                             key_env="AEB_DEFINITELY_MISSING_KEY")


def test_openai_compat_routing_passed_through():
    p = OpenAICompatProvider("x", base_url="http://x/v1", key_env=None,
                             routing={"order": ["anthropic"], "allow_fallbacks": False})
    body = p._payload(USER, Sampling())
    assert body["provider"] == {"order": ["anthropic"], "allow_fallbacks": False}


def test_anthropic_payload_splits_system():
    p = AnthropicProvider("claude-x", api_key="sk-test")
    body = p._payload([{"role": "system", "content": "be brief"}] + USER, Sampling(max_tokens=50))
    assert body["system"] == "be brief" and body["max_tokens"] == 50
    assert all(m["role"] != "system" for m in body["messages"])


def test_gemini_role_and_system_mapping():
    p = GeminiProvider("gemini-2.0-flash", api_key="k")
    body = p._payload(
        [{"role": "system", "content": "S"}, {"role": "user", "content": "U"},
         {"role": "assistant", "content": "A"}], Sampling(max_tokens=64))
    assert body["systemInstruction"]["parts"][0]["text"] == "S"
    assert [c["role"] for c in body["contents"]] == ["user", "model"]
    assert body["generationConfig"]["maxOutputTokens"] == 64


def test_registry_resolves_openai_compat_shorthand(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "x")
    p = get_provider(parse_model("groq:llama-3.1-8b-instant"))
    assert p.base_url.endswith("groq.com/openai/v1")
    assert p.model == "llama-3.1-8b-instant"


def test_registry_local_provider_needs_no_key():
    p = get_provider(parse_model("ollama:llama3"))     # no key required
    assert p.api_key is None and p.base_url.endswith("11434/v1")


def test_registry_unknown_provider_is_clear():
    with pytest.raises(ValueError, match="unknown provider"):
        get_provider(parse_model("nope:whatever"))
