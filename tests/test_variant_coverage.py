"""Every control the dashboard offers must have a block behind it.

The toolbar renders one checkbox per `partOf` group and a radio per network
model, and `currentSegData()` looks up the combination they name. A missing
combination used to fall through to the unaggregated stage-presence block --
a different model, a different node set, and the radio, the chips and the
figure captions all still naming the model that was not on screen.

The gap was a nested chain: with A partOf B partOf C, aggregation resolved
every member to C before filtering by the selected group, so selecting B
matched nothing and no variant for it was ever written.
"""

from __future__ import annotations

import json

import pytest

from conftest import build_tei, move, sp, stage

MODELS = ("full", "p-speaking", "s-speaking")

NESTED_RELATIONS = """  <listRelation>
    <relation name="partOf" active="#a" passive="#b"/>
    <relation name="partOf" active="#b" passive="#c"/>
  </listRelation>
"""


def payload_of(html: str) -> dict:
    i = html.index("const DATA = ")
    return json.loads(html[i + 13:html.index("\n", i)].rstrip().rstrip(";"))


@pytest.fixture(scope="module")
def nested_payload(tmp_path_factory) -> dict:
    """A play with a nested group chain and a mute, run through the app."""
    from app import analyze_one

    tmp = tmp_path_factory.mktemp("nested")
    body = "\n".join([
        stage(move("entrance", "a x")), sp("a", "one two three"),
        stage(move("entrance", "b c")), sp("b", "four five"), sp("c", "six"),
    ])
    tei = build_tei(["a", "b:group", "c:group", "x"], body, title="Nested")
    tei = tei.replace("</listPerson>", "</listPerson>\n" + NESTED_RELATIONS, 1)
    src = tmp / "nested.xml"
    src.write_text(tei, encoding="utf-8")
    out = tmp / "out"
    out.mkdir()
    analyze_one(xml_path=src, seg_modes=["sd"], out_root=out,
                export_model="full", edge_weight="segments",
                make_dashboard=True)
    return payload_of(next(out.rglob("dashboard.html")).read_text(
        encoding="utf-8"))


@pytest.mark.slow
def test_every_offered_group_has_a_block_in_every_model(nested_payload):
    groups = nested_payload["play"]["aggregate_groups"]
    assert groups == ["b", "c"], groups
    variants = nested_payload["segmentations"]["sd"]["variants"]
    missing = [f"{m}:{g}" for g in groups for m in MODELS
               if f"{m}:{g}" not in variants]
    assert not missing, missing


@pytest.mark.slow
def test_the_intermediate_group_collapses_only_what_it_holds(nested_payload):
    """Selecting B must mean B: A folded in, C still its own node."""
    variants = nested_payload["segmentations"]["sd"]["variants"]
    nodes = {key: sorted(n["id"] for n in blk["metrics"]["nodes"])
             for key, blk in variants.items()}
    assert nodes["p-speaking:b"] == ["b", "c"]
    assert nodes["p-speaking:c"] == ["c"]


@pytest.mark.slow
def test_the_speaking_model_never_shows_the_mute(nested_payload):
    """The fallback's actual damage: `x` never speaks, so no speaking-model
    block may contain it, aggregated or not."""
    variants = nested_payload["segmentations"]["sd"]["variants"]
    for key, blk in variants.items():
        if key.startswith("full:"):
            continue
        ids = {n["id"] for n in blk["metrics"]["nodes"]}
        assert "x" not in ids, key


@pytest.mark.slow
def test_the_checkbox_list_comes_from_the_writer(nested_payload):
    """Not from the relations: a group that is not a declared character is
    no aggregation target, and must not be offered as one."""
    declared = {r["passive"] for r in nested_payload["play"]["relations"]}
    offered = set(nested_payload["play"]["aggregate_groups"])
    assert offered <= declared
    characters = {c["id"]
                  for c in nested_payload["segmentations"]["sd"]["characters"]}
    assert offered <= characters
