"""``run()`` — the whole engine, in one function.

Build the grid (every model × every prompt × every repeat), fan it through a thread
pool, cap how many calls may hit any single model at once (the 429 guard), and write
each answer to JSONL the instant it lands. Re-running with ``resume=True`` skips the
cells already finished in the output, so an interrupted sweep just tops itself up.

Design choices worth knowing:

- **Errors are records too.** A failed call still produces a record (with ``output:
  null`` and a structured ``error``), so "did model X refuse/time out?" is answerable
  and ``resume`` can retry exactly those cells. A cell counts as *done* when it has a
  successful record, or a *permanent*-error record (unless ``retry_errors=True``).
- **One provider instance per model**, reused across all its calls; concurrency lives
  here in the core (a per-model semaphore), not inside the adapters.
- **Parallel-safe by construction.** Point many workers at distinct ``out`` files
  (e.g. ``run_<uuid>.jsonl``) and merge — every record carries its own ``custom_id``.
"""
from __future__ import annotations

import json
import random
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from .prompts import load_prompts
from .record import Record, Sampling, custom_id
from .registry import get_provider
from .roster import load_roster
from .usage import estimate_cost, normalize_usage


@dataclass
class RunResult:
    path: str | None
    ok: int
    failed: int
    run_id: str
    _records: list | None = None

    def records(self):
        """Yield the run's records as dicts (from memory if ``out=""``, else re-read the file)."""
        if self._records is not None:
            yield from self._records
        elif self.path:
            for line in Path(self.path).read_text(encoding="utf-8").splitlines():
                if line.strip():
                    yield json.loads(line)


def _err_type(exc) -> str:
    transient = getattr(exc, "transient", None)
    if transient is True:
        return "transient"
    return "permanent"


def _completed_ids(path, retry_errors):
    """custom_ids already finished in ``path`` (success, or permanent error if not retrying)."""
    done = set()
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        cid = rec.get("custom_id")
        if not cid:
            continue
        err = rec.get("error")
        if err is None:
            done.add(cid)
        elif not retry_errors and err.get("type") == "permanent":
            done.add(cid)
    return done


def _open_sink(out, resume):
    """Return (path_or_None, write_fn_or_None, close_fn_or_None, in_memory_bool)."""
    if out == "-":
        return None, (lambda line: sys.stdout.write(line + "\n")), None, False
    if out == "" or out is None:
        return None, None, None, True
    path = str(out)
    fh = open(path, "a" if resume else "w", encoding="utf-8")

    def write(line):
        fh.write(line + "\n")
        fh.flush()

    return path, write, fh.close, False


def run(prompts, models, out="run.jsonl", *,
        repeats=1, temperature=1.0, top_p=1.0, max_tokens=512, seed=0,
        concurrency=16, per_model_concurrency=None,
        resume=False, retry_errors=False,
        system=None, on_record=None, registry=None, prices=None,
        timeout=60.0, max_retries=4):
    """Fan a list of prompts across a roster of models and collect every answer.

    Parameters mirror the CLI. ``prompts`` and ``models`` accept lists, file paths, or
    ``"-"`` (stdin) — see ``load_prompts`` / ``load_roster``. ``out`` is a file path,
    ``"-"`` for stdout, or ``""`` to keep records in memory (``RunResult.records()``).
    Returns a ``RunResult`` (``path, ok, failed, run_id``).
    """
    prompt_list = load_prompts(prompts)
    roster = load_roster(models)
    run_id = uuid.uuid4().hex[:12]

    # One provider per distinct model, built once and reused. A build failure (e.g. a
    # missing API key) skips that whole model with a clear message rather than emitting
    # an error record per cell — it's a config problem, not a per-call one.
    providers, sems = {}, {}
    for spec in roster:
        if spec.label in providers:
            continue
        try:
            providers[spec.label] = (registry.get(spec) if registry is not None
                                     else get_provider(spec))
        except Exception as exc:
            print(f"[skip] {spec.label}: {exc}", file=sys.stderr)
            providers[spec.label] = None
        if per_model_concurrency:
            sems[spec.label] = threading.BoundedSemaphore(per_model_concurrency)

    done = (_completed_ids(out, retry_errors)
            if resume and isinstance(out, str) and out not in ("", "-") and Path(out).exists()
            else set())

    # Build the grid: model × prompt × repeat, skipping cells already done.
    tasks = []
    for spec in roster:
        if providers.get(spec.label) is None:
            continue
        spec_max = spec.max_tokens or max_tokens
        for p in prompt_list:
            for r in range(repeats):
                cid = custom_id(spec.provider, spec.model, p.text, system, r)
                if cid in done:
                    continue
                sampling = Sampling(temperature=temperature, top_p=top_p, max_tokens=spec_max,
                                    seed=(None if seed is None else seed + r),
                                    reasoning_effort=spec.reasoning_effort)
                tasks.append((spec, p, r, cid, sampling))

    # Shuffle so models/providers interleave instead of running block-by-block — spreads
    # provider load and gives early cross-model coverage. Seeded for reproducibility.
    random.Random(seed or 0).shuffle(tasks)

    path, write, close, in_memory = _open_sink(out, resume)
    collected = [] if in_memory else None
    ok = failed = 0
    lock = threading.Lock()

    def work(task):
        spec, p, r, cid, sampling = task
        provider = providers[spec.label]
        sem = sems.get(spec.label)
        rec = Record(custom_id=cid, run_id=run_id, provider=spec.provider, model=spec.model,
                     prompt_id=p.id, prompt=p.text, system=system, sampling=sampling,
                     repeat=r, prompt_meta=p.meta, model_meta=spec.meta)
        t0 = time.monotonic()
        try:
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": p.text})
            if sem:
                sem.acquire()
            try:
                text, meta = provider.chat(messages, sampling)
            finally:
                if sem:
                    sem.release()
            meta = meta or {}
            rec.output = text
            rec.finish_reason = meta.get("finish_reason")
            rec.model_returned = meta.get("model_returned")
            rec.served_by = meta.get("served_by")
            rec.usage = normalize_usage(spec.provider, meta.get("usage"))
            rec.cost_usd = estimate_cost(spec.model, rec.usage, prices)
            for k in ("empty_reason", "response_id", "reasoning_effort"):
                if k in meta and meta[k] is not None:
                    rec.raw[k] = meta[k]
            success = True
        except Exception as exc:
            rec.error = {"type": _err_type(exc), "message": str(exc)[:600],
                         "attempts": getattr(exc, "attempts", None)}
            success = False
        rec.latency_ms = int((time.monotonic() - t0) * 1000)
        return rec, success

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(work, t) for t in tasks]
        for fut in as_completed(futures):
            rec, success = fut.result()
            line = rec.to_json()
            with lock:
                if write:
                    write(line)
                if collected is not None:
                    collected.append(json.loads(line))
                if success:
                    ok += 1
                else:
                    failed += 1
            if on_record:
                try:
                    on_record(rec)
                except Exception:
                    pass

    if close:
        close()
    return RunResult(path=path, ok=ok, failed=failed, run_id=run_id, _records=collected)
