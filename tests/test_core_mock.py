"""End-to-end offline tests — the M0 milestone. No keys, no network."""
import json
import os
import subprocess
import sys
from pathlib import Path

import aieasybatch as ab

ROOT = Path(__file__).resolve().parent.parent


def test_run_mock_grid(tmp_path):
    out = tmp_path / "r.jsonl"
    res = ab.run(prompts=["a", "b"], models=["mock:x", "mock:y"], out=str(out))
    assert (res.ok, res.failed) == (4, 0)
    recs = [json.loads(l) for l in out.read_text().splitlines()]
    assert len(recs) == 4
    for r in recs:
        assert r["schema"] == "aieasybatch/v1"
        assert r["custom_id"] and r["provider"] == "mock"
        assert r["output"].startswith("[" + r["model"] + "]")
        assert r["usage"]["total_tokens"] >= 0
        assert r["error"] is None
    # every cell got a distinct custom_id
    assert len({r["custom_id"] for r in recs}) == 4


def test_deterministic_under_seed():
    a = ab.run(prompts=["a", "b"], models=["mock:x"], out="", seed=1)
    b = ab.run(prompts=["a", "b"], models=["mock:x"], out="", seed=1)
    assert [r["output"] for r in a.records()] == [r["output"] for r in b.records()]


def test_repeats_make_distinct_cells():
    res = ab.run(prompts=["a"], models=["mock:x"], out="", repeats=3)
    ids = [r["custom_id"] for r in res.records()]
    assert len(ids) == 3 and len(set(ids)) == 3


def test_resume_is_idempotent(tmp_path):
    out = tmp_path / "r.jsonl"
    ab.run(prompts=["a", "b"], models=["mock:x"], out=str(out))
    n1 = len(out.read_text().splitlines())
    res = ab.run(prompts=["a", "b"], models=["mock:x"], out=str(out), resume=True)
    n2 = len(out.read_text().splitlines())
    assert n1 == 2 and n2 == 2 and res.ok == 0   # nothing re-run, nothing appended


def test_resume_fills_only_the_gap(tmp_path):
    out = tmp_path / "r.jsonl"
    ab.run(prompts=["a"], models=["mock:x"], out=str(out))          # 1 cell
    res = ab.run(prompts=["a", "b"], models=["mock:x"], out=str(out), resume=True)
    assert res.ok == 1                                              # only "b" was new
    assert len(out.read_text().splitlines()) == 2


def test_in_memory_out():
    res = ab.run(prompts=["a"], models=["mock:x"], out="")
    assert res.path is None
    assert len(list(res.records())) == 1


def test_cli_run_to_stdout():
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
    proc = subprocess.run(
        [sys.executable, "-m", "aieasybatch", "run", "-p", "hello",
         "-m", "mock:a", "-o", "-", "-q"],
        cwd=ROOT, capture_output=True, text=True, env=env,
    )
    assert proc.returncode == 0, proc.stderr
    lines = [l for l in proc.stdout.splitlines() if l.strip()]
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["provider"] == "mock" and rec["prompt"] == "hello"
