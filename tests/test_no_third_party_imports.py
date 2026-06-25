"""The invariant that makes 'drops into any environment' true and the single-file build
a ~100-line concatenator instead of a bundler: the core imports the standard library and
its own siblings — nothing else.

If this ever fails, either the import is genuinely stdlib (add it below) or a real
dependency crept in (remove it — the whole pitch is zero dependencies).
"""
import ast
import sys
from pathlib import Path

PKG = Path(__file__).resolve().parent.parent / "src" / "aieasybatch"

# Python 3.10+ ships the authoritative set; fall back to what we actually use on 3.8/3.9.
_FALLBACK = {
    "__future__", "abc", "argparse", "ast", "base64", "collections", "concurrent",
    "contextlib", "csv", "dataclasses", "datetime", "functools", "glob", "hashlib",
    "html", "importlib", "io", "itertools", "json", "math", "os", "pathlib", "random",
    "re", "shutil", "subprocess", "sys", "tempfile", "textwrap", "threading", "time",
    "typing", "urllib", "uuid", "webbrowser",
}
STDLIB = set(getattr(sys, "stdlib_module_names", _FALLBACK)) | _FALLBACK


def _root(name):
    return name.split(".")[0]


def test_core_imports_stdlib_and_siblings_only():
    offenders = []
    for py in sorted(PKG.rglob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if _root(alias.name) not in STDLIB:
                        offenders.append(f"{py.relative_to(PKG)}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                if node.level and node.level > 0:
                    continue                       # relative import = sibling, allowed
                if node.module and _root(node.module) not in STDLIB:
                    offenders.append(f"{py.relative_to(PKG)}: from {node.module} import ...")
    assert not offenders, "non-stdlib imports found (zero-dependency invariant):\n  " + \
        "\n  ".join(offenders)
