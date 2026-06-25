"""Provider registry — resolve a ``ModelSpec`` to a live ``Provider``.

Most providers speak the OpenAI chat-completions dialect, so a single adapter covers
them all; the registry just remembers each one's ``base_url`` and key environment
variable, which is why ``groq:llama-3.1-8b`` or ``ollama:llama3`` work with no extra
configuration. Anthropic and Gemini get dedicated adapters. Add your own backend in one
line with ``aieasybatch.register("name", factory)``.

Live adapters are imported lazily so the offline core (mock provider) has zero import
cost and zero chance of breaking if an adapter file is absent.
"""
from __future__ import annotations

from .providers.mock import MockProvider

# name -> (base_url, key_env, options). key_env=None means "no key needed" (local).
_OPENAI_COMPAT = {
    "openai":     ("https://api.openai.com/v1",            "OPENAI_API_KEY",     {}),
    "openrouter": ("https://openrouter.ai/api/v1",         "OPENROUTER_API_KEY",
                   {"headers": {"HTTP-Referer": "https://github.com/liam499/easy-batch-prompting",
                                "X-Title": "aieasybatch"}, "supports_routing": True}),
    "groq":       ("https://api.groq.com/openai/v1",       "GROQ_API_KEY",       {}),
    "together":   ("https://api.together.xyz/v1",          "TOGETHER_API_KEY",   {}),
    "fireworks":  ("https://api.fireworks.ai/inference/v1", "FIREWORKS_API_KEY", {}),
    "deepinfra":  ("https://api.deepinfra.com/v1/openai",  "DEEPINFRA_API_KEY",  {}),
    "deepseek":   ("https://api.deepseek.com",             "DEEPSEEK_API_KEY",   {}),
    "xai":        ("https://api.x.ai/v1",                  "XAI_API_KEY",        {}),
    "mistral":    ("https://api.mistral.ai/v1",            "MISTRAL_API_KEY",    {}),
    "ollama":     ("http://localhost:11434/v1",            None,                 {}),
    "lmstudio":   ("http://localhost:1234/v1",             None,                 {}),
    "vllm":       ("http://localhost:8000/v1",             None,                 {}),
}

_REGISTRY = {}   # custom name -> factory(spec) -> Provider


def register(name, factory):
    """Register a custom provider: ``factory`` takes a ``ModelSpec``, returns a ``Provider``."""
    _REGISTRY[name] = factory


def known_providers():
    return sorted(set(_OPENAI_COMPAT) | {"anthropic", "gemini", "mock"} | set(_REGISTRY))


def get_provider(spec):
    name = spec.provider
    if name in _REGISTRY:
        return _REGISTRY[name](spec)
    if name == "mock":
        return MockProvider(model=spec.model)
    if name in _OPENAI_COMPAT:
        return _make_openai_compat(name, spec)
    if name == "anthropic":
        from .providers.anthropic import AnthropicProvider
        return AnthropicProvider(model=spec.model, base_url=spec.base_url, key_env=spec.key_env)
    if name == "gemini":
        from .providers.gemini import GeminiProvider
        return GeminiProvider(model=spec.model, base_url=spec.base_url, key_env=spec.key_env)
    raise ValueError(
        f"unknown provider {name!r}. Known: {', '.join(known_providers())}. "
        f"Add one with aieasybatch.register({name!r}, factory)."
    )


def _make_openai_compat(name, spec):
    from .providers.openai_compat import OpenAICompatProvider
    base_url, key_env, opts = _OPENAI_COMPAT[name]
    routing = spec.extra.get("routing") if opts.get("supports_routing") else None
    return OpenAICompatProvider(
        model=spec.model,
        base_url=spec.base_url or base_url,
        key_env=spec.key_env or key_env,
        reasoning_effort=spec.reasoning_effort,
        routing=routing,
        extra_headers=opts.get("headers"),
        provider_name=name,
    )
