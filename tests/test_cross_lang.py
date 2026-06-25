"""Cross-language parity: the Python and JS ports must agree on the record schema and on
custom_id hashing — the contract that lets a run (or a batch) produced by one be read,
merged, or resumed by the other."""
import json
import shutil
import subprocess
from pathlib import Path

from aieasybatch.record import Record, Sampling, custom_id

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "custom_ids.json"

CANONICAL_FIELDS = {
    "schema", "custom_id", "run_id", "ts", "provider", "model", "model_returned", "served_by",
    "prompt_id", "prompt", "system", "messages", "sampling", "repeat", "output", "finish_reason",
    "error", "usage", "cost_usd", "latency_ms", "prompt_meta", "model_meta", "raw",
}


def test_python_custom_id_matches_fixture():
    for c in json.loads(FIXTURE.read_text(encoding="utf-8")):
        assert custom_id(c["provider"], c["model"], c["prompt"], c["system"], c["repeat"]) == c["custom_id"]


def test_python_record_field_set_is_canonical():
    rec = Record(custom_id="c", run_id="r", provider="mock", model="x",
                 prompt_id="0", prompt="p", sampling=Sampling())
    assert set(json.loads(rec.to_json())) == CANONICAL_FIELDS


def test_js_agrees_with_python():
    """Run the JS test suite (which checks the same fixture + schema) if node is present."""
    node = shutil.which("node")
    if not node:
        import pytest
        pytest.skip("node not available")
    proc = subprocess.run([node, "--test"], cwd=ROOT / "js", capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr
