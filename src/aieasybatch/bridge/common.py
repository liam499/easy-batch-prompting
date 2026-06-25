"""Bridge orchestration: build the grid, submit one native batch per eligible model,
write a handle file, then poll/fetch and normalise results into the unified JSONL.

Each backend implements four steps — ``submit(model, cells, sampling, system)``,
``poll(job)``, ``fetch(job)`` — behind a tiny duck-typed interface, so adding a provider
is one file. ``cells`` is a list of ``{"custom_id", "messages"}``; ``fetch`` returns
``{custom_id: {output, finish_reason, usage, model_returned, served_by, error}}``.
"""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path

from ..core import run as live_run
from ..prompts import load_prompts
from ..record import Record, Sampling, custom_id, now_iso
from ..roster import load_roster
from ..usage import estimate_cost, normalize_usage

HANDLE_SCHEMA = "aieasybatch/batch-handle/v1"
_DEFAULT_ENV = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}

_BACKENDS = {}   # provider name -> backend class


def register_backend(name, cls):
    _BACKENDS[name] = cls


def get_backend(provider):
    if provider in _BACKENDS:
        return _BACKENDS[provider]
    if provider == "openai":
        from .openai_batch import OpenAIBatch
        _BACKENDS["openai"] = OpenAIBatch
        return OpenAIBatch
    if provider == "anthropic":
        from .anthropic_batch import AnthropicBatch
        _BACKENDS["anthropic"] = AnthropicBatch
        return AnthropicBatch
    return None


def eligible(provider) -> bool:
    return get_backend(provider) is not None


def _messages(system, text):
    msgs = [{"role": "system", "content": system}] if system else []
    msgs.append({"role": "user", "content": text})
    return msgs


def _open_out(out):
    if out == "-":
        return None, (lambda line: sys.stdout.write(line + "\n")), None
    if out in ("", None):
        return None, (lambda line: None), None
    fh = open(str(out), "a", encoding="utf-8")     # append: collect is resumable

    def write(line):
        fh.write(line + "\n")
        fh.flush()

    return str(out), write, fh.close


def _save_handle(path, handle):
    Path(path).write_text(json.dumps(handle, ensure_ascii=False, indent=2), encoding="utf-8")


def submit_batch(prompts, models, handle_path="run.batch.json", *, system=None,
                 repeats=1, temperature=1.0, top_p=1.0, max_tokens=512, seed=0,
                 live_fallback=False, live_out=None, timeout=120.0):
    """Submit one native batch job per eligible model; write a handle file. Returns
    ``(handle_path, jobs)``. Ineligible providers are skipped (or run live with
    ``live_fallback=True``)."""
    prompt_list = load_prompts(prompts)
    roster = load_roster(models)
    run_id = uuid.uuid4().hex[:12]
    prompts_json = [{"id": p.id, "text": p.text, "meta": p.meta} for p in prompt_list]

    eligible_specs = [s for s in roster if eligible(s.provider)]
    ineligible_specs = [s for s in roster if not eligible(s.provider)]
    jobs = []

    for spec in eligible_specs:
        env = spec.key_env or _DEFAULT_ENV.get(spec.provider)
        api_key = os.environ.get(env) if env else None
        if env and not api_key:
            print(f"[skip] {spec.label}: set {env} to submit a batch", file=sys.stderr)
            continue
        backend = get_backend(spec.provider)(api_key=api_key, base_url=spec.base_url, timeout=timeout)
        job_max = spec.max_tokens or max_tokens
        sampling = Sampling(temperature=temperature, top_p=top_p, max_tokens=job_max,
                            seed=seed, reasoning_effort=spec.reasoning_effort)
        cells, payload = {}, []
        for i, p in enumerate(prompt_list):
            for r in range(repeats):
                cid = custom_id(spec.provider, spec.model, p.text, system, r)
                cells[cid] = [i, r]
                payload.append({"custom_id": cid, "messages": _messages(system, p.text)})
        try:
            fields = backend.submit(spec.model, payload, sampling, system)
        except Exception as exc:
            print(f"[error] submit {spec.label}: {exc}", file=sys.stderr)
            continue
        jobs.append({"provider": spec.provider, "model": spec.model, "key_env": env,
                     "model_meta": spec.meta, "reasoning_effort": spec.reasoning_effort,
                     "max_tokens": job_max, "cells": cells, "collected": False, **fields})
        print(f"[submit] {spec.label}: batch {fields.get('batch_id')} ({len(cells)} requests)",
              file=sys.stderr)

    handle = {"schema": HANDLE_SCHEMA, "run_id": run_id, "ts": now_iso(),
              "system": system, "temperature": temperature, "top_p": top_p, "seed": seed,
              "prompts": prompts_json, "jobs": jobs}
    _save_handle(handle_path, handle)
    print(f"wrote handle {handle_path} ({len(jobs)} batch jobs). "
          f"Collect with: aieasybatch batch collect {handle_path} -o answers.jsonl --wait",
          file=sys.stderr)

    if ineligible_specs:
        labels = ", ".join(s.label for s in ineligible_specs)
        if live_fallback:
            print(f"[live] running non-batch providers live: {labels}", file=sys.stderr)
            live_run(prompt_list, ineligible_specs, out=live_out or (str(handle_path) + ".live.jsonl"),
                     repeats=repeats, temperature=temperature, top_p=top_p,
                     max_tokens=max_tokens, seed=seed, system=system)
        else:
            print(f"[skip] no batch API for: {labels}. Re-run with --live-fallback to run them live.",
                  file=sys.stderr)
    return handle_path, jobs


def _record_from(handle, job, cid, res):
    i, r = job["cells"][cid]
    p = handle["prompts"][i]
    base_seed = handle.get("seed", 0)
    sampling = Sampling(temperature=handle.get("temperature", 1.0), top_p=handle.get("top_p", 1.0),
                        max_tokens=job["max_tokens"],
                        seed=(base_seed + r) if base_seed is not None else None,
                        reasoning_effort=job.get("reasoning_effort"))
    usage = normalize_usage(job["provider"], res.get("usage"))
    return Record(
        custom_id=cid, run_id=handle.get("run_id"), provider=job["provider"], model=job["model"],
        prompt_id=p["id"], prompt=p["text"], system=handle.get("system"), sampling=sampling, repeat=r,
        output=res.get("output"), finish_reason=res.get("finish_reason"), error=res.get("error"),
        model_returned=res.get("model_returned"), served_by=res.get("served_by") or job["provider"],
        usage=usage, cost_usd=estimate_cost(job["model"], usage),
        prompt_meta=p.get("meta", {}), model_meta=job.get("model_meta", {}),
        raw={"batch": True, "batch_id": job.get("batch_id")},
    )


def collect_batch(handle_path, out="-", *, wait=False, poll_interval=30.0, timeout=120.0):
    """Poll each job; for completed ones, fetch results and append normalised records to
    ``out`` (idempotent — already-written custom_ids are skipped). Returns ``(path, n)``."""
    handle = json.loads(Path(handle_path).read_text(encoding="utf-8"))

    written = set()
    if isinstance(out, str) and out not in ("-", "") and Path(out).exists():
        for line in Path(out).read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    written.add(json.loads(line)["custom_id"])
                except Exception:
                    pass

    path, write, close = _open_out(out)
    n = 0
    try:
        while True:
            pending = [j for j in handle["jobs"] if not j.get("collected")]
            for job in pending:
                env = job.get("key_env") or _DEFAULT_ENV.get(job["provider"])
                api_key = os.environ.get(env) if env else None
                backend = get_backend(job["provider"])(api_key=api_key, timeout=timeout)
                try:
                    status = backend.poll(job)
                except Exception as exc:
                    print(f"[error] poll {job['provider']}:{job['model']}: {exc}", file=sys.stderr)
                    continue
                job["status"] = status.get("status")
                if status.get("failed"):
                    print(f"[failed] {job['provider']}:{job['model']} batch {job.get('batch_id')}: "
                          f"{status.get('status')}", file=sys.stderr)
                    job["collected"] = True
                    continue
                if not status.get("done"):
                    print(f"[wait] {job['provider']}:{job['model']}: {status.get('status')}", file=sys.stderr)
                    continue
                results = backend.fetch(job)
                for cid, res in results.items():
                    if cid in written or cid not in job["cells"]:
                        continue
                    write(_record_from(handle, job, cid, res).to_json())
                    written.add(cid)
                    n += 1
                job["collected"] = True
                print(f"[done] {job['provider']}:{job['model']}: {len(results)} results", file=sys.stderr)
            _save_handle(handle_path, handle)
            if not wait or all(j.get("collected") for j in handle["jobs"]):
                break
            time.sleep(poll_interval)
    finally:
        if close:
            close()
    done = sum(1 for j in handle["jobs"] if j.get("collected"))
    print(f"collected {n} records from {done}/{len(handle['jobs'])} jobs -> {path or 'stdout'}",
          file=sys.stderr)
    return path, n
