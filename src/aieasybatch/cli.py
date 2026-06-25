"""Command-line interface — a thin, honest wrapper over ``run()``.

The whole tool is essentially one verb::

    aieasybatch run prompts.txt -m mock:a -m mock:b -o run.jsonl

Prompts come from a file, ``-`` (stdin), or repeated ``-p``; models from repeated
``-m provider:model`` and/or a ``--roster`` file. Output is JSONL to a file or to
stdout (``-o -``), so it pipes straight into ``aieasybatch view`` or ``jq``.
"""
from __future__ import annotations

import argparse
import sys

from . import __version__
from .core import run
from .roster import load_roster


def _add_run(sub):
    p = sub.add_parser("run", help="fan prompts across a roster of models (live calls)")
    p.add_argument("prompts", nargs="?", help="prompts file, or '-' for stdin")
    p.add_argument("-p", "--prompt", action="append", metavar="TEXT",
                   help="an inline prompt (repeatable)")
    p.add_argument("-m", "--model", action="append", metavar="PROVIDER:ID",
                   help="a model selector like openai:gpt-4o-mini (repeatable)")
    p.add_argument("--roster", metavar="FILE", help="a roster JSON file of models")
    p.add_argument("-o", "--out", default="-", metavar="FILE",
                   help="output JSONL path, or '-' for stdout (default)")
    p.add_argument("--system", metavar="TEXT", help="system prompt applied to every call")
    p.add_argument("--repeats", type=int, default=1)
    p.add_argument("--temperature", type=float, default=1.0)
    p.add_argument("--top-p", type=float, default=1.0, dest="top_p")
    p.add_argument("--max-tokens", type=int, default=512, dest="max_tokens")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--concurrency", type=int, default=16, help="total in-flight calls")
    p.add_argument("--per-model", type=int, default=None, dest="per_model",
                   help="max simultaneous calls to any one model (the 429 guard)")
    p.add_argument("--resume", action="store_true",
                   help="skip cells already complete in --out; fill only the gaps")
    p.add_argument("--retry-errors", action="store_true", dest="retry_errors",
                   help="on resume, also retry cells that previously errored")
    p.add_argument("-q", "--quiet", action="store_true", help="don't print the summary")
    p.set_defaults(func=_cmd_run)


def _cmd_run(args) -> int:
    # prompts: inline -p wins, else positional path/stdin
    if args.prompt:
        prompts = list(args.prompt)
    elif args.prompts:
        prompts = args.prompts
    else:
        print("error: provide prompts (a file, '-', or one or more -p)", file=sys.stderr)
        return 2

    # models: combine -m selectors and a --roster file
    models = list(args.model or [])
    if args.roster:
        models += load_roster(args.roster)
    if not models:
        print("error: provide at least one -m provider:model or a --roster file", file=sys.stderr)
        return 2

    if args.resume and args.out in ("-", ""):
        print("error: --resume needs a file --out (not stdout)", file=sys.stderr)
        return 2

    result = run(
        prompts, models, out=args.out,
        repeats=args.repeats, temperature=args.temperature, top_p=args.top_p,
        max_tokens=args.max_tokens, seed=args.seed,
        concurrency=args.concurrency, per_model_concurrency=args.per_model,
        resume=args.resume, retry_errors=args.retry_errors, system=args.system,
    )
    if not args.quiet:
        where = result.path or "stdout"
        print(f"wrote {result.ok + result.failed} records "
              f"({result.ok} ok, {result.failed} failed) to {where}", file=sys.stderr)
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="aieasybatch",
        description="Brain-dead-simple batch prompting: prompts × a roster of models "
                    "-> one JSONL with every answer. Zero dependencies.",
    )
    ap.add_argument("--version", action="version", version=f"aieasybatch {__version__}")
    sub = ap.add_subparsers(dest="cmd")
    _add_run(sub)
    _maybe_add_optional(sub)
    return ap


def _maybe_add_optional(sub):
    """Register the view/batch verbs if their modules are present (added in later phases)."""
    try:
        from .viewer import add_cli as add_view
        add_view(sub)
    except Exception:
        pass
    try:
        from .bridge import add_cli as add_batch
        add_batch(sub)
    except Exception:
        pass


def main(argv=None) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)
    if not getattr(args, "func", None):
        ap.print_help(sys.stderr)
        return 1
    return args.func(args)
