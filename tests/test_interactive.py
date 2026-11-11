"""The guided prompt that runs when the app is started with no subcommand.

Untested until now, and it is the path a user takes by double-clicking or by
running `python -m app` with nothing after it.
"""

from __future__ import annotations

import builtins

import pytest

import interactive
from interactive import _strip_quotes, run_interactive


def _answers(monkeypatch, *replies):
    """Feed the prompts a fixed script of answers."""
    it = iter(replies)

    def fake_input(prompt=""):
        try:
            return next(it)
        except StopIteration:
            raise EOFError("script exhausted")

    monkeypatch.setattr(builtins, "input", fake_input)


# ---------------------------------------------------------------------------
# Pasted paths
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw, expected", [
    ('"C:\\plays\\Ar-01-Ach.xml"', "C:\\plays\\Ar-01-Ach.xml"),
    ("'/home/x/plays'",            "/home/x/plays"),
    ("C:\\plays\\Ar-01-Ach.xml",   "C:\\plays\\Ar-01-Ach.xml"),
    ('"unbalanced',                '"unbalanced'),
    ('"',                          '"'),
    ("",                           ""),
])
def test_strip_quotes(raw, expected):
    assert _strip_quotes(raw) == expected


def test_single_play_flow_strips_a_pasted_quoted_path(monkeypatch):
    """Windows' "Copy as path" hands over the quotes, and input() keeps them.

    The corpus flow stripped them and the single-play flow did not, so the
    commoner of the two prompts was the one that broke on a pasted path.
    """
    _answers(monkeypatch, "1", '"C:\\plays\\Ar-01-Ach.xml"', "n", "out")
    monkeypatch.setattr(interactive.os.path, "isfile", lambda p: True)
    command, kw = run_interactive()
    assert command == "analyze"
    assert kw["file"] == "C:\\plays\\Ar-01-Ach.xml"


def test_corpus_flow_strips_a_pasted_quoted_path(monkeypatch, tmp_path):
    d = tmp_path / "comedy"
    d.mkdir()
    (d / "one.xml").write_text("<TEI/>", encoding="utf-8")
    _answers(monkeypatch, "2", f'"{d}"', "", "", "out")
    command, kw = run_interactive()
    assert command == "corpus"
    assert kw["paths"] == [str(d)]


# ---------------------------------------------------------------------------
# No terminal attached
# ---------------------------------------------------------------------------

def test_end_of_input_cancels_instead_of_raising(monkeypatch):
    """`python -m app` with stdin closed used to end in an EOFError
    traceback; there is nobody to ask, which is not an error."""
    def eof(prompt=""):
        raise EOFError

    monkeypatch.setattr(builtins, "input", eof)
    assert run_interactive() is None


def test_interrupt_cancels_instead_of_raising(monkeypatch):
    def interrupt(prompt=""):
        raise KeyboardInterrupt

    monkeypatch.setattr(builtins, "input", interrupt)
    assert run_interactive() is None


def test_quit_option_returns_none(monkeypatch):
    _answers(monkeypatch, "3")
    assert run_interactive() is None
