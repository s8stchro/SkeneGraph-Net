"""TEI parser for Greek-drama plays.

Extracts the data the network app needs:
  - characters (with mute / collective / chorus flags)
  - <move> elements in document order, each tagged with its containing div2/div3
  - <sp>  elements in document order, each tagged with its containing div2/div3
  - the div2 / div3 sequence itself, in document order

The parser is intentionally narrow: only what the segmenters / graph builders
need.  No metrics, no analysis.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set

from lxml import etree

log = logging.getLogger("SkeneGraph-Net.parser")

NS = {"tei": "http://www.tei-c.org/ns/1.0"}
XML_ID = "{http://www.w3.org/XML/1998/namespace}id"
XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"


@dataclass
class Character:
    id: str
    name_grc: str = ""
    name_en: str = ""
    sex: Optional[str] = None
    nature: Optional[str] = None    # raw @key from <trait type="nature">
    is_mute: bool = False
    is_collective: bool = False
    is_chorus: bool = False         # chorus or semichorus
    is_speaker_explicit: bool = False  # has #speaker in castItem @ana

    @property
    def display_name(self) -> str:
        return self.name_en or self.name_grc or self.id

    @property
    def nature_class(self) -> str:
        """Coarse normalised nature: 'human' / 'divine' / 'animal' / 'concept' / 'other'."""
        n = (self.nature or "").lower()
        if n == "human": return "human"
        if n == "divine": return "divine"
        if n == "animal": return "animal"
        if n in ("concept", "personified-concept", "abstraction"): return "concept"
        return "other"

    @property
    def sex_class(self) -> str:
        """Coarse normalised sex: 'male' / 'female' / 'unspecified'."""
        s = (self.sex or "").lower()
        if s == "male": return "male"
        if s == "female": return "female"
        return "unspecified"


@dataclass
class Move:
    # @type: one of 'entrance' | 'exit' | 'onStage' | 'state-change' | 'merge' | 'split'.
    # Of these, entrance / exit / onStage / merge / split are *structural*
    # (change WHO is on stage and trigger segment boundaries in the stage-
    # direction segmenter); state-change is *non-structural* (applies its
    # perception/visibility effect via the no-op branch in `_apply_move`
    # without flushing the segment).
    type: str
    who: Set[str] = field(default_factory=set)
    corresp: Set[str] = field(default_factory=set)
    # @subtype: space-separated controlled-vocabulary tokens describing the
    # character's perception / visibility / participation state.  Recognised
    # values (one per axis):
    #   location:      stage | voice-only         (default: stage)
    #   visibility:    unhidden | hidden           (default: unhidden)
    #   capacity:      awake | asleep              (default: awake)
    #   vitality:      alive | dead                (default: alive)
    #   engagement:    aware | unaware             (default: aware)
    #   participation: engaged | withdrawn         (default: engaged)
    # Allowed on entrance / onStage / state-change; forbidden on exit
    # (state inherits from the character's prior move history).  The
    # parser is permissive: it records whatever tokens it finds and
    # emits warnings on schema violations rather than rejecting.
    subtype: Set[str] = field(default_factory=set)
    pos: int = 0             # document order index (shared with Speech)
    div2_pos: Optional[int] = None  # unique position-key of containing div2
    div2_n: Optional[str] = None
    div2_type: Optional[str] = None
    div3_pos: Optional[int] = None  # unique position-key of containing div3
    div3_id: Optional[str] = None
    div3_n: Optional[str] = None
    source_line: Optional[int] = None

    @property
    def is_structural(self) -> bool:
        """True iff this move triggers a segment boundary under the
        stage-direction segmentation (rule 7 of the annotation schema).
        Structural moves are those that change WHO is on stage:
        entrance / exit / onStage (arrivals, departures, presence
        assertions) and merge / split (cast re-groupings)."""
        return self.type in ("entrance", "exit", "onStage", "merge", "split")


@dataclass
class Speech:
    who: Set[str] = field(default_factory=set)
    addressees: Set[str] = field(default_factory=set)
    verse_count: int = 0
    word_count: int = 0
    pos: int = 0
    div2_pos: Optional[int] = None
    div2_n: Optional[str] = None
    div2_type: Optional[str] = None
    div3_pos: Optional[int] = None
    div3_id: Optional[str] = None
    div3_n: Optional[str] = None
    source_line: Optional[int] = None


@dataclass
class Div:
    """A div2 or div3 boundary in document order."""
    level: int                # 2 or 3
    xml_id: Optional[str]
    n: Optional[str]
    type: Optional[str]
    pos: int                  # document order index
    parent_div2_n: Optional[str] = None
    parent_div2_type: Optional[str] = None

    @property
    def label(self) -> str:
        parts = []
        if self.type:
            parts.append(self.type)
        if self.n:
            parts.append(str(self.n))
        if self.xml_id:
            parts.append(self.xml_id)
        return "/".join(parts) if parts else f"div{self.level}-{self.pos}"


@dataclass
class Relation:
    """A typed relation between two characters from <listRelation>.

    Currently we only consume `partOf` (the `active` character is part of
    the `passive` one, e.g. `#chorosAndron partOf #choros`).  The corpus
    uses TEI's older `name="partOf"` form; we also accept the standard
    `type="partOf"` so the parser is forward-compatible.
    """
    name: str                # 'partOf' (others ignored downstream for now)
    active: str              # id of the part / member
    passive: str             # id of the whole / group


@dataclass
class PlayData:
    title_grc: str = ""
    title_en: str = ""
    author: str = ""
    play_id: str = ""
    source_xml: str = ""    # raw text of the TEI file, for the dashboard's TEI tab
    characters: Dict[str, Character] = field(default_factory=dict)
    moves: List[Move] = field(default_factory=list)
    speeches: List[Speech] = field(default_factory=list)
    div2s: List[Div] = field(default_factory=list)
    div3s: List[Div] = field(default_factory=list)
    relations: List[Relation] = field(default_factory=list)


def _refs(s: Optional[str]) -> Set[str]:
    """Parse a space-separated `who="#a #b"` value into a set of ids."""
    if not s:
        return set()
    return {tok.lstrip("#") for tok in s.split() if tok.strip()}


# Controlled @subtype vocabulary for the new annotation schema.  Tokens
# are grouped by axis; one token per axis is allowed.  See `Move.subtype`
# docstring for the full meaning.
_SUBTYPE_AXES: Dict[str, frozenset] = {
    "location":      frozenset({"stage", "voice-only"}),
    "visibility":    frozenset({"unhidden", "hidden"}),
    "capacity":      frozenset({"awake", "asleep"}),
    "vitality":      frozenset({"alive", "dead"}),
    "engagement":    frozenset({"aware", "unaware"}),
    "participation": frozenset({"engaged", "withdrawn"}),
}
_ALL_SUBTYPE_TOKENS: frozenset = frozenset().union(*_SUBTYPE_AXES.values())

# Move types that may (or must not) carry a @subtype attribute.
# Permissive parsing: violations log warnings, never raise.
_SUBTYPE_ALLOWED_ON   = frozenset({"entrance", "onStage", "state-change"})
_SUBTYPE_REQUIRED_ON  = frozenset({"state-change"})
_SUBTYPE_FORBIDDEN_ON = frozenset({"exit", "merge", "split"})


def _parse_move_states(ana_raw: Optional[str], subtype_raw: Optional[str],
                       move_type: str, source_line: Optional[int]) -> Set[str]:
    """Parse the character-state tokens carried by a <move> element.

    Primary source is @ana: space-separated #-references into the
    `move-subtype` taxonomy (e.g. `ana="#withdrawn #unaware"`).  This is
    the TEI-canonical way to attach multiple controlled-vocabulary
    categories to an element.  The leading `#` is stripped.

    Legacy fallback is @subtype: bare tokens used by the original
    encoding convention before the migration to @ana.  Still read so the
    parser doesn't break mid-migration, but emits a deprecation warning
    whenever it fires.  Once every TEI file has been migrated to @ana,
    this branch can be removed.

    Schema-violation warnings (state-change requires; exit forbids;
    unknown tokens; multi-axis conflicts) apply identically regardless
    of which attribute carried the tokens.
    """
    tokens: Set[str] = set()
    # 1. @ana (preferred).  Each value is a #-prefixed reference.
    if ana_raw:
        for tok in ana_raw.split():
            tok = tok.strip().lstrip("#")
            if not tok:
                continue
            tokens.add(tok)
    # 2. @subtype (legacy).  Each value is a bare token (no #).
    if subtype_raw:
        legacy_tokens = {t.strip().lstrip("#") for t in subtype_raw.split() if t.strip()}
        if legacy_tokens:
            log.warning(
                "move at line %s uses legacy @subtype=%r; migrate to "
                "@ana with #-prefixed references (e.g. ana=\"#%s\")",
                source_line, subtype_raw, " #".join(sorted(legacy_tokens)),
            )
            tokens |= legacy_tokens

    # Vocabulary check: warn on unknown tokens regardless of source.
    for tok in tokens:
        if tok not in _ALL_SUBTYPE_TOKENS:
            log.warning(
                "move at line %s carries unknown state token %r "
                "(allowed: %s)",
                source_line, tok, ", ".join(sorted(_ALL_SUBTYPE_TOKENS)),
            )
    # Schema-violation warnings (parser still records the tokens).
    if tokens and move_type in _SUBTYPE_FORBIDDEN_ON:
        log.warning(
            "move type=%r at line %s should not carry state tokens "
            "(state inherits from prior move history); tokens=%s",
            move_type, source_line, sorted(tokens),
        )
    if not tokens and move_type in _SUBTYPE_REQUIRED_ON:
        log.warning(
            "move type=%r at line %s lacks state tokens "
            "(state-change must specify the target state)",
            move_type, source_line,
        )
    # Multi-axis conflict check: more than one token in the same axis.
    for axis_name, axis_tokens in _SUBTYPE_AXES.items():
        overlap = tokens & axis_tokens
        if len(overlap) > 1:
            log.warning(
                "move at line %s has conflicting %s-axis tokens %s; "
                "downstream will use whichever is read first",
                source_line, axis_name, sorted(overlap),
            )
    return tokens


def _local(elem) -> str:
    return etree.QName(elem.tag).localname if isinstance(elem.tag, str) else ""


def _text_in(elem) -> str:
    return " ".join(t for t in elem.itertext() if t)


def _word_count(text: str) -> int:
    return sum(1 for w in text.split() if w.strip())


def _extract_metadata(root, play: PlayData, file_path: str) -> None:
    titles = root.findall(".//tei:titleStmt/tei:title", NS)
    for t in titles:
        text = (t.text or "").strip()
        if not text:
            continue
        if t.get(XML_LANG) == "grc" and not play.title_grc:
            play.title_grc = text
        elif t.get(XML_LANG) == "en" and not play.title_en:
            play.title_en = text
    if not play.title_en and titles:
        play.title_en = (titles[0].text or "").strip()

    author_el = root.find(".//tei:titleStmt/tei:author", NS)
    if author_el is not None and author_el.text:
        play.author = author_el.text.strip()

    div1 = root.find(".//tei:body//tei:div1", NS)
    if div1 is not None:
        play.play_id = div1.get("n") or play.title_en or Path(file_path).stem
    else:
        play.play_id = play.title_en or Path(file_path).stem


def _extract_characters(root, play: PlayData) -> None:
    # Step 1: <person> / <personGrp> in <listPerson>
    for person_el in root.findall(".//tei:listPerson/tei:person", NS):
        cid = person_el.get(XML_ID)
        if not cid:
            continue
        ch = Character(id=cid)
        for pn in person_el.findall("tei:persName", NS):
            txt = (pn.text or "").strip()
            if pn.get(XML_LANG) == "grc":
                ch.name_grc = txt
            elif pn.get(XML_LANG) == "en":
                ch.name_en = txt
        for trait in person_el.findall("tei:trait", NS):
            t = trait.get("type")
            k = trait.get("key")
            if t == "sex":
                ch.sex = k
            elif t == "nature":
                ch.nature = k
        play.characters[cid] = ch
    for grp_el in root.findall(".//tei:listPerson/tei:personGrp", NS):
        cid = grp_el.get(XML_ID)
        if not cid:
            continue
        ch = Character(id=cid, is_collective=True)
        for pn in grp_el.findall("tei:persName", NS):
            txt = (pn.text or "").strip()
            if pn.get(XML_LANG) == "grc":
                ch.name_grc = txt
            elif pn.get(XML_LANG) == "en":
                ch.name_en = txt
        for trait in grp_el.findall("tei:trait", NS):
            t = trait.get("type")
            k = trait.get("key")
            if t == "sex":
                ch.sex = k
            elif t == "nature":
                ch.nature = k
        play.characters[cid] = ch

    # Step 2: <castItem> @ana drives collective / chorus / speaker flags.
    # NB: muteness is decided behaviourally further down (see `_classify_mutes`)
    #     -- the @ana annotation is often missing for mute characters.
    for ci in root.findall(".//tei:castList/tei:castItem", NS):
        corresp = ci.get("corresp", "")
        cid = corresp.lstrip("#") if corresp else ""
        if not cid or cid not in play.characters:
            continue
        ch = play.characters[cid]
        ana = ci.get("ana", "")
        cats = {tok.lstrip("#") for tok in ana.split() if tok.strip()}
        if "speaker" in cats:
            ch.is_speaker_explicit = True
        if "collective" in cats:
            ch.is_collective = True
        if "chorus" in cats or "semichorus" in cats:
            ch.is_chorus = True


def _extract_relations(root, play: PlayData) -> None:
    """Pull <relation> entries out of every <listRelation> in the header.

    The corpus annotates split-chorus structure as

        <listRelation type="dramatic-structure">
          <relation name="partOf" active="#chorosAndron" passive="#choros">...</relation>
        </listRelation>

    We accept both `name=` (the corpus's older convention) and `type=`
    (the current TEI Guidelines wording) on the <relation> element.
    Only relations whose endpoints are known characters in this play
    are kept; unknown ids are silently dropped to avoid dangling refs.
    """
    for rel in root.findall(".//tei:listRelation/tei:relation", NS):
        rel_name = (rel.get("name") or rel.get("type") or "").strip()
        if not rel_name:
            continue
        active_raw = rel.get("active") or ""
        passive_raw = rel.get("passive") or ""
        active_ids = list(_refs(active_raw))
        passive_ids = list(_refs(passive_raw))
        if not active_ids or not passive_ids:
            continue
        # `active` and `passive` may each contain multiple ids
        # (e.g. several parts of the same whole on one element).  Expand.
        for a in active_ids:
            for p in passive_ids:
                if a in play.characters and p in play.characters:
                    play.relations.append(Relation(name=rel_name, active=a, passive=p))
                else:
                    missing = []
                    if a not in play.characters: missing.append(f"active #{a}")
                    if p not in play.characters: missing.append(f"passive #{p}")
                    log.warning(
                        "relation %s '%s -> %s' dropped: %s not in <listPerson>",
                        rel_name, a, p, " and ".join(missing),
                    )


def _classify_mutes(play: PlayData) -> None:
    """Set `is_mute` from observed behaviour: strict <l>-based rule.

    A character is mute iff they have NO non-empty `<l>` element attributed
    to them anywhere in the play (i.e. no speech with verse_count > 0 has
    that character in @who).  This is the strict reading that matches the
    per-segment "mute / speaker" definition the dashboard uses for the
    mutes-out network model:

        speaker-in-segment = >=1 non-empty <l> attributed in that segment
        play-mute (cat 2)  = speaker-in-segment for *no* segment

    More reliable than trusting the editor's `#mute` annotation, which is
    frequently omitted on minor mute roles; and consistent with treating
    `<l>` (with text) as the marker of dialogic agency in verse drama.
    """
    spoken: Dict[str, int] = {}
    for sp in play.speeches:
        if sp.verse_count <= 0:
            continue
        for cid in sp.who:
            spoken[cid] = spoken.get(cid, 0) + sp.verse_count
    for cid, ch in play.characters.items():
        ch.is_mute = spoken.get(cid, 0) == 0


def _walk_body(root, play: PlayData) -> None:
    """Single document-order walk through <body> collecting moves, speeches and div boundaries.

    `pos` is incremented for every move, speech and div element so the three
    streams can be re-interleaved later by the segmenters.
    """
    body = root.find(".//tei:body", NS)
    if body is None:
        return

    pos = 0
    cur_div2_pos: Optional[int] = None
    cur_div2_n: Optional[str] = None
    cur_div2_type: Optional[str] = None
    cur_div3_pos: Optional[int] = None
    cur_div3_id: Optional[str] = None
    cur_div3_n: Optional[str] = None

    sp_depth = 0  # so we don't double-walk into <sp>'s descendants

    for event, elem in etree.iterwalk(body, events=("start", "end")):
        name = _local(elem)
        if event == "start":
            if name == "div2":
                pos += 1
                cur_div2_pos = pos
                cur_div2_n = elem.get("n")
                cur_div2_type = elem.get("type")
                play.div2s.append(Div(
                    level=2,
                    xml_id=elem.get(XML_ID),
                    n=cur_div2_n,
                    type=cur_div2_type,
                    pos=cur_div2_pos,
                ))
            elif name == "div3":
                pos += 1
                cur_div3_pos = pos
                cur_div3_id = elem.get(XML_ID)
                cur_div3_n = elem.get("n")
                play.div3s.append(Div(
                    level=3,
                    xml_id=cur_div3_id,
                    n=cur_div3_n,
                    type=elem.get("type"),
                    pos=cur_div3_pos,
                    parent_div2_n=cur_div2_n,
                    parent_div2_type=cur_div2_type,
                ))
            elif name == "move":
                pos += 1
                m_type = (elem.get("type") or "").strip()
                play.moves.append(Move(
                    type=m_type,
                    who=_refs(elem.get("who")),
                    corresp=_refs(elem.get("corresp")),
                    subtype=_parse_move_states(
                        elem.get("ana"), elem.get("subtype"),
                        m_type, elem.sourceline),
                    pos=pos,
                    div2_pos=cur_div2_pos,
                    div2_n=cur_div2_n,
                    div2_type=cur_div2_type,
                    div3_pos=cur_div3_pos,
                    div3_id=cur_div3_id,
                    div3_n=cur_div3_n,
                    source_line=elem.sourceline,
                ))
            elif name == "sp" and sp_depth == 0:
                sp_depth = 1
                pos += 1
                # Count <l> children (verses) and words across all text in <sp>.
                lines = elem.findall(".//tei:l", NS)
                verse_count = sum(1 for l in lines if (_text_in(l).strip()))
                word_count = sum(_word_count(_text_in(l)) for l in lines)
                # If no <l> at all, fall back to direct text.
                if not lines:
                    word_count = _word_count(_text_in(elem))
                play.speeches.append(Speech(
                    who=_refs(elem.get("who")),
                    addressees=_refs(elem.get("toWhom")),
                    verse_count=verse_count,
                    word_count=word_count,
                    pos=pos,
                    div2_pos=cur_div2_pos,
                    div2_n=cur_div2_n,
                    div2_type=cur_div2_type,
                    div3_pos=cur_div3_pos,
                    div3_id=cur_div3_id,
                    div3_n=cur_div3_n,
                    source_line=elem.sourceline,
                ))
            elif name == "sp":
                sp_depth += 1
        else:  # end
            if name == "div2":
                cur_div2_pos = None
                cur_div2_n = None
                cur_div2_type = None
            elif name == "div3":
                cur_div3_pos = None
                cur_div3_id = None
                cur_div3_n = None
            elif name == "sp":
                sp_depth -= 1


def parse_play(file_path: str | Path) -> PlayData:
    file_path = str(file_path)
    play = PlayData()
    # Keep the raw TEI text alongside the parsed structure so the dashboard's
    # TEI tab can render the source with line numbers + per-segment jumps.
    try:
        with open(file_path, encoding="utf-8") as fh:
            play.source_xml = fh.read()
    except Exception:
        play.source_xml = ""
    tree = etree.parse(file_path)
    root = tree.getroot()
    _extract_metadata(root, play, file_path)
    _extract_characters(root, play)
    _extract_relations(root, play)
    _walk_body(root, play)

    # Behavioural mute classification: a character is mute iff they utter
    # zero words across the whole play.  Run AFTER `_walk_body` so all
    # speeches are available.
    _classify_mutes(play)

    # Mark chorus explicitly via id pattern as a fallback if @ana didn't say so
    for ch in play.characters.values():
        if not ch.is_chorus and ("chor" in ch.id.lower() or "chor" in ch.name_grc.lower()):
            if "semichor" in ch.id.lower() or ch.id.lower() in {"chorus", "choros"}:
                ch.is_chorus = True

    return play


__all__ = [
    "Character", "Move", "Speech", "Div", "Relation", "PlayData", "parse_play",
]
