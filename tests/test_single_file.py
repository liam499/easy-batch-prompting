"""The vendorable single file must (a) be in sync with src/ and (b) behave identically."""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SINGLE = ROOT / "aieasybatch.py"


def _load_builder():
    spec = importlib.util.spec_from_file_location("build_single", ROOT / "tools" / "build_single.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["build_single"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_single_file_is_in_sync():
    """The committed aieasybatch.py must equal a fresh build — regenerate after editing src/."""
    fresh = _load_builder().build(write=False)
    assert SINGLE.exists(), "aieasybatch.py missing — run: python tools/build_single.py"
    assert fresh == SINGLE.read_text(encoding="utf-8"), \
        "aieasybatch.py is stale — run: python tools/build_single.py"


def test_single_file_runs_mock(tmp_path):
    spec = importlib.util.spec_from_file_location("aieasybatch_single", SINGLE)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["aieasybatch_single"] = mod        # register so dataclasses resolve annotations
    spec.loader.exec_module(mod)
    out = tmp_path / "s.jsonl"
    res = mod.run(prompts=["a", "b"], models=["mock:x"], out=str(out))
    assert res.ok == 2
    recs = [json.loads(l) for l in out.read_text().splitlines()]
    assert all(r["schema"] == "aieasybatch/v1" for r in recs)
    # the single file exposes the same public surface as the package
    assert all(hasattr(mod, n) for n in
               ["run", "load_prompts", "load_roster", "Record", "Sampling", "register"])


def test_single_file_cli(tmp_path):
    out = tmp_path / "c.jsonl"
    proc = subprocess.run(
        [sys.executable, str(SINGLE), "run", "-p", "hi", "-m", "mock:a", "-o", str(out), "-q"],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert len(out.read_text().splitlines()) == 1
