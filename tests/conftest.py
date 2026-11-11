"""Shared fixtures for the SkeneGraph-Net test suite.

The app modules live at the repository root as flat modules (`parser.py`,
`segmentation.py`, ...), so the root is put on `sys.path` here rather than
requiring an installed package.

Two kinds of input are used:

* the real demo play (`examples/Ar-07-Lys.xml`), parsed once per session --
  it exercises the pipeline on genuine TEI with mutes, a split chorus and
  all three segmentation spines;
* synthetic mini-plays built by `tiny_play`, which reach the edge cases a
  real file cannot be relied on to contain (empty placeholder speeches,
  joint speeches, schema violations, off-stage state-changes).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterable, Optional

import pytest

APP_DIR = Path(__file__).resolve().parent.parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from parser import parse_play  # noqa: E402
from segmentation import SEGMENTERS  # noqa: E402

DEMO_XML = APP_DIR / "examples" / "Ar-07-Lys.xml"

PARSER_LOGGER = "SkeneGraph-Net.parser"


# ---------------------------------------------------------------------------
# The real demo play
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def demo_path() -> Path:
    assert DEMO_XML.is_file(), f"demo play missing: {DEMO_XML}"
    return DEMO_XML


@pytest.fixture(scope="session")
def demo_play(demo_path):
    """Parsed demo play.  Session-scoped: parsing is the slow step."""
    return parse_play(demo_path)


@pytest.fixture(scope="session")
def demo_segments(demo_play):
    """All three spines of the demo play, keyed by segmenter name."""
    return {name: fn(demo_play) for name, fn in SEGMENTERS.items()}


# ---------------------------------------------------------------------------
# Synthetic mini-plays
# ---------------------------------------------------------------------------

_TEI = """<?xml version="1.0" encoding="UTF-8"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0">
  <teiHeader>
    <fileDesc>
      <titleStmt>
{titles}
{authors}
      </titleStmt>
{file_extra}
    </fileDesc>
    <profileDesc>
      <particDesc>
        <listPerson>
{persons}
        </listPerson>
      </particDesc>
{profile_extra}
    </profileDesc>
  </teiHeader>
  <text>
    <body>
      <div type="play">
{body}
      </div>
    </body>
  </text>
</TEI>
"""


def _person(spec: str) -> str:
    """`spec` is "id" or "id:group" or "id:group:sex:nature"."""
    parts = spec.split(":")
    cid = parts[0]
    kind = parts[1] if len(parts) > 1 and parts[1] else "person"
    sex = parts[2] if len(parts) > 2 and parts[2] else None
    nature = parts[3] if len(parts) > 3 and parts[3] else None
    tag = "personGrp" if kind == "group" else "person"
    traits = ""
    if sex:
        traits += f'\n            <trait type="sex" key="{sex}"/>'
    if nature:
        traits += f'\n            <trait type="nature" key="{nature}"/>'
    return (f'          <{tag} xml:id="{cid}">'
            f'\n            <persName xml:lang="en">{cid}</persName>'
            f'{traits}\n          </{tag}>')


def build_tei(
    persons: Iterable[str],
    body: str,
    title: str = "TestPlay",
    titles: Optional[str] = None,
    authors: Optional[str] = None,
    profile_extra: str = "",
    file_extra: str = "",
) -> str:
    """Assemble a minimal well-formed TEI document.

    `persons` are specs understood by `_person`; `body` is raw TEI markup
    (moves wrapped in <stage>, <sp> elements, milestones).  `titles` and
    `authors` override the default single-language titleStmt entries,
    `profile_extra` is injected into <profileDesc> (used for <textClass>),
    and `file_extra` into <fileDesc> after the titleStmt, where the corpus
    keeps its <sourceDesc> and the play's identifiers.
    """
    return _TEI.format(
        title=title,
        titles=titles if titles is not None
        else f'        <title xml:lang="en">{title}</title>',
        authors=authors if authors is not None
        else '        <author>Test Author</author>',
        file_extra=file_extra,
        persons="\n".join(_person(p) for p in persons),
        profile_extra=profile_extra,
        body=body,
    )


def stage(*moves: str) -> str:
    """Wrap one or more <move/> strings in a single <stage> cluster.

    Move grouping matters: the stage-direction segmenter opens one segment
    per <stage> that contains a structural move, so tests must be explicit
    about which moves share a cluster.
    """
    inner = "\n          ".join(moves)
    return f"        <stage>\n          {inner}\n        </stage>"


def move(type_: str, who: str = "", ana: str = "", corresp: str = "") -> str:
    attrs = [f'type="{type_}"']
    if who:
        attrs.append('who="' + " ".join("#" + w for w in who.split()) + '"')
    if corresp:
        attrs.append('corresp="' + " ".join("#" + c for c in corresp.split()) + '"')
    if ana:
        attrs.append(f'ana="{ana}"')
    return f'<move {" ".join(attrs)}/>'


def sp(who: str, *lines: str) -> str:
    """A <sp>.  Pass no lines for an empty <sp><l/></sp> placeholder."""
    who_attr = " ".join("#" + w for w in who.split())
    if not lines:
        return f'        <sp who="{who_attr}"><l/></sp>'
    body = "\n          ".join(f"<l>{ln}</l>" for ln in lines)
    return f'        <sp who="{who_attr}">\n          {body}\n        </sp>'


def milestone(unit: str, xml_id: str, type_: Optional[str] = None) -> str:
    t = f' type="{type_}"' if type_ else ""
    return f'        <milestone unit="{unit}" xml:id="{xml_id}"{t}/>'


@pytest.fixture
def tiny_play(tmp_path):
    """Factory: build a synthetic play, write it, return the parsed PlayData.

    Usage:
        play = tiny_play(["a", "b"], stage(move("entrance", "a b")) + sp("a", "x y"))
    """
    counter = {"n": 0}

    def _make(persons: Iterable[str], body: str, title: str = "TestPlay",
              **kwargs):
        counter["n"] += 1
        path = tmp_path / f"tiny_{counter['n']}.xml"
        path.write_text(build_tei(persons, body, title, **kwargs),
                        encoding="utf-8")
        return parse_play(path)

    return _make


@pytest.fixture
def tiny_path(tmp_path):
    """Like `tiny_play`, but returns the file path instead of parsing it."""
    counter = {"n": 0}

    def _make(persons: Iterable[str], body: str, title: str = "TestPlay") -> Path:
        counter["n"] += 1
        path = tmp_path / f"tinypath_{counter['n']}.xml"
        path.write_text(build_tei(persons, body, title), encoding="utf-8")
        return path

    return _make
