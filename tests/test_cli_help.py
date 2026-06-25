"""Regression guard for CLI help rendering.

A literal ``%`` in any ``help=`` string makes argparse's HelpFormatter raise when
it ``%``-expands the text (e.g. ``50%-off`` was read as the ``%-o`` conversion and
``aieasybatch --help`` crashed with ``TypeError: %o format``). These tests format
every (sub)parser's help so any such mistake fails CI instead of the user.
"""
from __future__ import annotations

import argparse

import pytest

from aieasybatch import cli


def _format_every_parser(parser: argparse.ArgumentParser) -> None:
    parser.format_help()  # raises if a help= string has an unescaped '%'
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for sub in action.choices.values():
                _format_every_parser(sub)


def test_all_help_strings_format_cleanly():
    _format_every_parser(cli.build_parser())


def test_top_level_help_exits_zero():
    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"])
    assert exc.value.code == 0


def test_run_is_always_registered():
    # The single-file build is run-only; the package adds view/batch/lock. Either
    # way 'run' must be present and its help must render.
    text = cli.build_parser().format_help()
    assert "run" in text
