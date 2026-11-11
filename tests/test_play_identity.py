"""Two plays of one title stay two plays, in every output.

Sophocles and Euripides both wrote an Electra, and both cite as "El.".  A
title identifies nothing, so each play is identified by its TLG work number,
read from the header's CTS URN, and every output that names a play must
keep the two apart: the folders, metrics.json, the dashboards' payloads and
comparison exports, and the labels a reader sees.
"""

from __future__ import annotations

import json
import logging

import pytest

from conftest import build_tei, move, sp, stage

TITLES = """        <title xml:lang="grc">Ἠλέκτρα</title>
        <title xml:lang="en">Electra</title>
        <title xml:lang="lat"><choice><expan>Electra</expan><abbr>El.</abbr></choice></title>"""

PLAYS = {
    # file name: (English author, Latin abbreviation, TLG work, cast)
    "So-Ele.xml": ("Sophocles", "Soph.", "tlg0011.tlg005", ("elektra", "orestes")),
    "Eu-Ele.xml": ("Euripides", "Eur.", "tlg0006.tlg012", ("elektra", "autourgos")),
}


def _tei(author, abbr, work, cast):
    authors = (f'        <author xml:lang="en">{author}</author>\n'
               f'        <author xml:lang="lat"><choice><expan>{author}</expan>'
               f'<abbr>{abbr}</abbr></choice></author>')
    source = ('      <sourceDesc><bibl type="digitalSource">'
              f'<idno type="CTS-URN">urn:cts:greekLit:{work}.perseus-grc2</idno>'
              '</bibl></sourceDesc>')
    body = "\n".join([stage(move("entrance", " ".join(cast))),
                      sp(cast[0], "one two three"), sp(cast[1], "four five")])
    return build_tei(list(cast), body, titles=TITLES, authors=authors,
                     file_extra=source)


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    """Both Electras through the corpus command, as a user would run it."""
    import app

    tmp = tmp_path_factory.mktemp("electras")
    corpus = tmp / "tragedy"
    corpus.mkdir()
    for name, spec in PLAYS.items():
        (corpus / name).write_text(_tei(*spec), encoding="utf-8")
    out = tmp / "out"
    logging.disable(logging.WARNING)
    try:
        args = app.build_parser().parse_args(
            ["corpus", str(corpus), "--out", str(out)])
        assert args.func(args) == 0
    finally:
        logging.disable(logging.NOTSET)
    html = (out / "corpus_dashboard.html").read_text(encoding="utf-8")
    i = html.index("const DATA = ")
    data = json.loads(html[i + 13:html.index("\n", i)].rstrip().rstrip(";"))
    return out, data


@pytest.mark.slow
def test_each_play_is_identified_by_its_work_number(run):
    _, data = run
    ids = {p["author"]: p["id"] for p in data["plays"]}
    assert ids == {"Sophocles": "tlg0011.tlg005", "Euripides": "tlg0006.tlg012"}


@pytest.mark.slow
def test_metrics_json_carries_the_two_ids(run):
    out, _ = run
    ids = sorted(json.loads(m.read_text(encoding="utf-8"))["id"]
                 for m in out.rglob("sd/metrics.json"))
    assert ids == ["tlg0006.tlg012", "tlg0011.tlg005"]


@pytest.mark.slow
def test_the_folders_stay_named_for_the_title(run):
    """The output tree reads as a list of plays; the marker says which is
    which."""
    out, _ = run
    dirs = sorted(d.name for d in out.iterdir() if d.is_dir())
    assert all(d.startswith("Electra") for d in dirs) and len(dirs) == 2
    recorded = {json.loads((out / d / "source.json").read_text(
        encoding="utf-8"))["play_id"] for d in dirs}
    assert recorded == {"tlg0011.tlg005", "tlg0006.tlg012"}


@pytest.mark.slow
def test_the_payload_carries_what_the_labels_need(run):
    """The dashboard labels a shared title with the author's citation form,
    so the payload must carry it."""
    _, data = run
    cites = {p["author_lat_abbr"] for p in data["plays"]}
    assert cites == {"Soph.", "Eur."}
    assert {p["title_lat_abbr"] for p in data["plays"]} == {"El."}
