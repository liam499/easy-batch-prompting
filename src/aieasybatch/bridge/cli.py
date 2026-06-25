"""``aieasybatch batch submit`` / ``aieasybatch batch collect`` — the bridge CLI."""
from __future__ import annotations

import sys

from ..roster import load_roster
from .common import collect_batch, submit_batch


def add_cli(sub):
    p = sub.add_parser("batch", help="run on providers' native 50%-off async batch APIs "
                                     "(OpenAI, Anthropic); other providers via --live-fallback")
    bsub = p.add_subparsers(dest="batchcmd")

    s = bsub.add_parser("submit", help="submit one batch job per eligible model; write a handle file")
    s.add_argument("prompts", nargs="?", help="prompts file, or '-' for stdin")
    s.add_argument("-p", "--prompt", action="append", metavar="TEXT")
    s.add_argument("-m", "--model", action="append", metavar="PROVIDER:ID")
    s.add_argument("--roster", metavar="FILE")
    s.add_argument("--handle", default="run.batch.json", help="handle file to write (default run.batch.json)")
    s.add_argument("--system")
    s.add_argument("--repeats", type=int, default=1)
    s.add_argument("--temperature", type=float, default=1.0)
    s.add_argument("--top-p", type=float, default=1.0, dest="top_p")
    s.add_argument("--max-tokens", type=int, default=512, dest="max_tokens")
    s.add_argument("--seed", type=int, default=0)
    s.add_argument("--live-fallback", action="store_true", dest="live_fallback",
                   help="also run non-batch providers via the live path")
    s.set_defaults(func=_cmd_submit)

    c = bsub.add_parser("collect", help="poll batch jobs and fetch results into one JSONL")
    c.add_argument("handle", help="the handle file written by `batch submit`")
    c.add_argument("-o", "--out", default="-", help="output JSONL path, or '-' for stdout")
    c.add_argument("--wait", action="store_true", help="keep polling until every job finishes")
    c.add_argument("--poll-interval", type=float, default=30.0, dest="poll_interval")
    c.set_defaults(func=_cmd_collect)

    p.set_defaults(func=lambda a: (p.print_help(sys.stderr) or 1))


def _cmd_submit(args) -> int:
    if args.prompt:
        prompts = list(args.prompt)
    elif args.prompts:
        prompts = args.prompts
    else:
        print("error: provide prompts (a file, '-', or one or more -p)", file=sys.stderr)
        return 2
    models = list(args.model or [])
    if args.roster:
        models += load_roster(args.roster)
    if not models:
        print("error: provide at least one -m provider:model or a --roster file", file=sys.stderr)
        return 2
    submit_batch(prompts, models, args.handle, system=args.system, repeats=args.repeats,
                 temperature=args.temperature, top_p=args.top_p, max_tokens=args.max_tokens,
                 seed=args.seed, live_fallback=args.live_fallback)
    return 0


def _cmd_collect(args) -> int:
    if args.out in ("-", "") and args.wait:
        print("note: --wait writes to stdout incrementally as jobs finish", file=sys.stderr)
    collect_batch(args.handle, args.out, wait=args.wait, poll_interval=args.poll_interval)
    return 0
