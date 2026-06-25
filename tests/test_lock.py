"""Offline tests for the provider-lock endpoint picker (the network call is not tested)."""
from aieasybatch.lock import pick_endpoint


def test_prefers_models_own_vendor():
    eps = [
        {"tag": "groq/x", "quantization": "fp8", "uptime_last_30m": 0.99},
        {"tag": "anthropic/x", "quantization": "fp16", "uptime_last_30m": 0.50},
    ]
    assert pick_endpoint("anthropic/claude-3-5-haiku", eps)["tag"] == "anthropic/x"


def test_prefers_precision_then_uptime_without_vendor_match():
    eps = [
        {"tag": "novita/x", "quantization": "int4", "uptime_last_30m": 0.99},
        {"tag": "together/x", "quantization": "bf16", "uptime_last_30m": 0.40},
        {"tag": "deepinfra/x", "quantization": "bf16", "uptime_last_30m": 0.90},
    ]
    # no vendor match for this slug -> highest precision (bf16), then best uptime (deepinfra)
    assert pick_endpoint("xyzcorp/some-model", eps)["tag"] == "deepinfra/x"


def test_empty_endpoints_returns_none():
    assert pick_endpoint("x/y", []) is None
