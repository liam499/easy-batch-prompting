"""Bridge tests, fully offline: the pure payload/result helpers, plus a submit→collect
round-trip through a fake backend that proves the handle file and record reconstruction
(and that batch custom_ids align with the live path)."""
import json

import pytest

from aieasybatch.bridge import common, register_backend
from aieasybatch.bridge.anthropic_batch import build_params, parse_results_jsonl
from aieasybatch.bridge.openai_batch import build_request_body, parse_output_jsonl
from aieasybatch.record import Sampling, custom_id

USER = [{"role": "user", "content": "hi"}]


# ---- pure helpers ----------------------------------------------------------

def test_openai_body_standard_and_reasoning():
    b = build_request_body("gpt-4o-mini", USER, Sampling(temperature=0.5, max_tokens=99, top_p=0.8))
    assert b["max_tokens"] == 99 and b["temperature"] == 0.5 and b["top_p"] == 0.8
    r = build_request_body("o3-mini", USER, Sampling(max_tokens=2048, reasoning_effort="low"))
    assert r["max_completion_tokens"] == 2048 and "max_tokens" not in r and "temperature" not in r
    assert r["reasoning_effort"] == "low"


def test_openai_parse_output_success_and_error():
    text = "\n".join([
        json.dumps({"custom_id": "c1", "response": {"status_code": 200, "body": {
            "choices": [{"message": {"content": "hello"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 2}, "model": "gpt-4o-mini"}}}),
        json.dumps({"custom_id": "c2", "response": {"status_code": 400, "body": {
            "error": {"message": "bad"}}}}),
    ])
    res = parse_output_jsonl(text)
    assert res["c1"]["output"] == "hello" and res["c1"]["error"] is None
    assert res["c2"]["output"] is None and res["c2"]["error"]["type"] == "permanent"


def test_anthropic_params_and_results():
    p = build_params("claude-x", [{"role": "system", "content": "be brief"}] + USER,
                     Sampling(max_tokens=64))
    assert p["system"] == "be brief" and p["max_tokens"] == 64
    text = "\n".join([
        json.dumps({"custom_id": "c1", "result": {"type": "succeeded", "message": {
            "content": [{"type": "text", "text": "hi there"}], "stop_reason": "end_turn",
            "usage": {"input_tokens": 4, "output_tokens": 3}, "model": "claude-x"}}}),
        json.dumps({"custom_id": "c2", "result": {"type": "errored", "error": {"message": "nope"}}}),
    ])
    res = parse_results_jsonl(text)
    assert res["c1"]["output"] == "hi there" and res["c1"]["usage"]["output_tokens"] == 3
    assert res["c2"]["output"] is None and res["c2"]["error"]["type"] == "permanent"


# ---- submit -> collect round-trip via a fake backend -----------------------

class FakeBackend:
    eligible = True
    submitted = {}

    def __init__(self, api_key=None, base_url=None, timeout=120.0, max_retries=4):
        pass

    def submit(self, model, cells, sampling, system):
        FakeBackend.submitted[model] = cells
        return {"batch_id": "fake-" + model, "status": "submitted", "state": {"model": model}}

    def poll(self, job):
        return {"status": "completed", "done": True, "failed": False}

    def fetch(self, job):
        cells = FakeBackend.submitted[job["model"]]
        return {c["custom_id"]: {
            "output": "ANS:" + c["messages"][-1]["content"], "finish_reason": "stop",
            "usage": {"input_tokens": 5, "output_tokens": 7},
            "model_returned": job["model"], "served_by": "fake", "error": None}
            for c in cells}


@pytest.fixture
def fake():
    register_backend("fake", FakeBackend)
    FakeBackend.submitted = {}
    yield


def test_submit_writes_handle(tmp_path, fake):
    handle = tmp_path / "h.json"
    common.submit_batch(["a", "b"], ["fake:m1", "fake:m2"], str(handle))
    h = json.loads(handle.read_text())
    assert h["schema"].startswith("aieasybatch/batch-handle")
    assert len(h["jobs"]) == 2 and len(h["prompts"]) == 2
    assert all("cells" in j and j["batch_id"].startswith("fake-") for j in h["jobs"])


def test_collect_reconstructs_records(tmp_path, fake):
    handle = tmp_path / "h.json"
    common.submit_batch(["a", "b"], ["fake:m1", "fake:m2"], str(handle))
    out = tmp_path / "ans.jsonl"
    path, n = common.collect_batch(str(handle), str(out))
    assert n == 4
    recs = [json.loads(l) for l in out.read_text().splitlines()]
    for r in recs:
        assert r["schema"] == "aieasybatch/v1"
        assert r["output"].startswith("ANS:")
        assert r["usage"]["total_tokens"] == 12
        assert r["raw"]["batch"] is True
    # batch custom_ids are identical to what the live path would produce -> diffable
    assert any(r["custom_id"] == custom_id("fake", "m1", "a", None, 0) for r in recs)


def test_collect_is_idempotent(tmp_path, fake):
    handle = tmp_path / "h.json"
    common.submit_batch(["a"], ["fake:m1"], str(handle))
    out = tmp_path / "ans.jsonl"
    common.collect_batch(str(handle), str(out))
    # collecting again must not duplicate (jobs already marked collected, ids already written)
    _, n2 = common.collect_batch(str(handle), str(out))
    assert n2 == 0
    assert len(out.read_text().splitlines()) == 1


def test_batch_cli_submit_then_collect(tmp_path, fake):
    """The `batch` verb registers and runs end-to-end through the real CLI dispatcher."""
    from aieasybatch import cli
    handle = tmp_path / "h.json"
    assert cli.main(["batch", "submit", "-p", "a", "-p", "b", "-m", "fake:m1",
                     "--handle", str(handle)]) == 0
    assert handle.exists()
    out = tmp_path / "ans.jsonl"
    assert cli.main(["batch", "collect", str(handle), "-o", str(out)]) == 0
    assert len(out.read_text().splitlines()) == 2
