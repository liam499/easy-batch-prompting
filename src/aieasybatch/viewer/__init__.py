"""The ``view`` verb — render a run's JSONL as a self-contained HTML comparison grid.

One template, two ways in: open ``template.html`` directly and drop a ``.jsonl`` on it
(pure client-side), or bake the data in for a shareable artifact::

    aieasybatch view run.jsonl -o report.html

The viewer is package-only (it ships an HTML asset), so it is intentionally absent from
the single-file build.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_TEMPLATE = Path(__file__).with_name("template.html")
_PLACEHOLDER = "__AEB_DATA__"


def render_html(records) -> str:
    """Inject a list of record dicts into the template, producing a standalone HTML page."""
    # Escape ``</`` so an output containing "</script>" can't break out of the data tag.
    data = json.dumps(list(records), ensure_ascii=False).replace("</", "<\\/")
    return _TEMPLATE.read_text(encoding="utf-8").replace(_PLACEHOLDER, data)


def _read_records(path) -> list:
    if path == "-":
        text = sys.stdin.read()
    else:
        text = Path(path).read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def add_cli(sub):
    p = sub.add_parser("view", help="render a run's JSONL as a standalone HTML comparison grid")
    p.add_argument("jsonl", help="a run JSONL file, or '-' for stdin")
    p.add_argument("-o", "--out", default=None, help="output HTML path (default: alongside input)")
    p.add_argument("--open", action="store_true", dest="open_", help="open the report in a browser")
    p.set_defaults(func=_cmd_view)


def _cmd_view(args) -> int:
    records = _read_records(args.jsonl)
    if args.out:
        out = args.out
    elif args.jsonl == "-":
        out = "report.html"
    else:
        out = str(Path(args.jsonl).with_suffix("")) + ".html"
    Path(out).write_text(render_html(records), encoding="utf-8")
    print(f"wrote {out} ({len(records)} records)", file=sys.stderr)
    if getattr(args, "open_", False):
        import webbrowser
        webbrowser.open("file://" + str(Path(out).resolve()))
    return 0
