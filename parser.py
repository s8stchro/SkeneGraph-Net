"""TEI parser for Greek-drama plays.

Extracts the data the network app needs:
  - characters (with mute / collective / chorus flags)
  - <move> elements in document order, each tagged with its containing large-seq/middle-seq
  - <sp>  elements in document order, each tagged with its containing large-seq/middle-seq
  - the large-seq / middle-seq sequence itself, in document order

The parser is intentionally narrow: only what the segmenters / graph builders
need.  No metrics, no analysis.
"""

from __future__ import annotations

import logging
import re
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
    # Every collective this character is a part of, transitively, from
    # <relation name="partOf">.  A part and its whole are one body on stage,
    # so the graph builders never join them by an edge (see network._pairs).
    part_of: Set[str] = field(default_factory=set)

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
        if n in ("concept", "personified-concept", "personified-abstraction",
                 "abstraction"): return "concept"
        return "other"

    @property
    def sex_class(self) -> str:
        """Coarse normalised sex: 'male' / 'female' / 'mixed' / 'unspecified'.

        `mixed` is kept apart from `unspecified` because it says something
        positive -- this collective comprises both -- where `irrelevant` and a
        missing trait say the question does not arise or was not recorded.
        """
        s = (self.sex or "").lower()
        if s == "male": return "male"
        if s == "female": return "female"
        if s == "mixed": return "mixed"
        return "unspecified"


@dataclass
class Move:
    # @type: one of 'entrance' | 'exit' | 'onStage' | 'state-change' |
    # 'crossing' | 'merge' | 'split'.
    # Of these, entrance / exit / onStage / merge / split are *structural*
    # (change WHO is on stage and trigger segment boundaries in the stage-
    # direction segmenter); state-change and crossing are *non-structural*
    # (applied by no-op branches in `apply_move` without flushing the
    # segment).  A `crossing` is a figure who appears and is gone within one
    # beat -- the stage occupancy before and after is identical, so they are
    # never in a constellation with anyone and never become a network node.
    # The corpus uses it for the anonymous prop-fetcher (@who="#tis",
    # @ana="#fetch-prop"), where the text gives an order but no departure,
    # so an encoded exit would assert a moment the text does not supply.
    type: str
    who: Set[str] = field(default_factory=set)
    corresp: Set[str] = field(default_factory=set)
    # @subtype: space-separated controlled-vocabulary tokens describing the
    # character's location, visibility and perception state.  Recognised
    # values (one per axis):
    #   location:      stage | voice-only         (default: stage)
    #   visibility:    unhidden | hidden           (default: unhidden)
    #   capacity:      awake | asleep              (default: awake)
    #   vitality:      alive | dead                (default: alive)
    #   engagement:    aware | unaware             (default: aware)
    #   crossing:      fetch-prop | signal-off     (crossing only; no default)
    # Allowed on entrance / onStage / state-change / crossing; forbidden on exit
    # (state inherits from the character's prior move history).  The
    # parser is permissive: it records whatever tokens it finds and
    # emits warnings on schema violations rather than rejecting.
    subtype: Set[str] = field(default_factory=set)
    pos: int = 0             # document order index (shared with Speech)
    large_seq_pos: Optional[int] = None  # unique position-key of containing large_seq
    large_seq_id: Optional[str] = None
    large_seq_type: Optional[str] = None
    middle_seq_pos: Optional[int] = None  # unique position-key of containing middle_seq
    middle_seq_id: Optional[str] = None
    source_line: Optional[int] = None
    stage_pos: Optional[int] = None  # position-key of the containing <stage> (move cluster)
    stage_line: Optional[int] = None  # source line of the containing <stage> (TEI highlight start)

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
    word_count: int = 0
    pos: int = 0
    large_seq_pos: Optional[int] = None
    large_seq_id: Optional[str] = None
    large_seq_type: Optional[str] = None
    middle_seq_pos: Optional[int] = None
    middle_seq_id: Optional[str] = None
    source_line: Optional[int] = None

    @property
    def attributed_words(self) -> int:
        """Words this speech credits to characters.

        A joint speech (`<sp who="#a #b">`) credits its full word count to
        each speaker named in @who, so it contributes once per speaker and
        the sum over speeches exceeds the number of words standing in the
        text.  This is the single word-quantity rule in the app: the
        play total, the per-character totals, the per-segment totals and the
        edge word totals are all sums of these credits, so every word figure
        on a dashboard reconciles with every other.  `word_count` alone is
        the text of one speech and is not summed anywhere.

        The Schematron requires @who on every <sp>, so no speech falls
        outside the rule and none can lose its words here.
        """
        return self.word_count * len(self.who)


@dataclass
class Div:
    """A large-seq or middle-seq boundary in document order."""
    level: int                # 2 or 3
    xml_id: Optional[str]
    n: Optional[str]
    type: Optional[str]
    pos: int                  # document order index
    parent_large_seq_id: Optional[str] = None
    parent_large_seq_type: Optional[str] = None

    @property
    def label(self) -> str:
        parts = []
        if self.type:
            parts.append(self.type)
        if self.n:
            parts.append(str(self.n))
        if self.xml_id:
            parts.append(self.xml_id)
        return "/".join(parts) if parts else f"{'large-seq' if self.level == 2 else 'middle-seq'}-{self.pos}"


@dataclass
class Relation:
    """A typed relation between two characters from <listRelation>.

    Currently we only consume `partOf` (the `active` character is part of
    the `passive` one, e.g. `#chorosGeronton partOf #choros`).  The corpus
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
    # The Latin title, from <title xml:lang="lat"><choice><expan>/<abbr>.  The
    # abbreviation is the scholarly citation form (Ach., Av., Thesm.) and is
    # what the corpus charts label plays with.
    title_lat: str = ""
    title_lat_abbr: str = ""
    author: str = ""          # display form: English if given, else Greek
    author_grc: str = ""
    author_en: str = ""
    # The Latin author, encoded like the Latin title.  Its abbreviation
    # (Soph., Eur.) is what tells two plays of one title apart on a chart.
    author_lat: str = ""
    author_lat_abbr: str = ""
    genre: str = ""           # from <textClass>; "" when unclassified
    # The play's identity: its TLG work number in CTS form (tlg0019.tlg003),
    # or the file name where the header carries none.  Never the title, which
    # two plays can share -- Sophocles' Electra and Euripides'.
    play_id: str = ""
    source_xml: str = ""    # raw text of the TEI file, for the dashboard's TEI tab
    characters: Dict[str, Character] = field(default_factory=dict)
    moves: List[Move] = field(default_factory=list)
    speeches: List[Speech] = field(default_factory=list)
    large_seqs: List[Div] = field(default_factory=list)
    middle_seqs: List[Div] = field(default_factory=list)
    relations: List[Relation] = field(default_factory=list)


def _refs(s: Optional[str]) -> Set[str]:
    """Parse a space-separated `who="#a #b"` value into a set of ids."""
    if not s:
        return set()
    return {tok.lstrip("#") for tok in s.split() if tok.strip()}


def apply_move(state: Set[str], move: Move) -> None:
    """Update the stage state with a move (mutates `state`).

    The transition semantics of the `<move>` vocabulary, kept here beside the
    `Move` dataclass that declares it, so the segmenters and the parser's own
    schema validation share one definition.
    """
    if move.type == "entrance":
        state.update(move.who)
    elif move.type == "exit":
        state.difference_update(move.who)
    elif move.type == "split":
        # The character splits into the @corresp ones; remove origin, add parts.
        state.difference_update(move.who)
        state.update(move.corresp)
    elif move.type == "merge":
        # The @who parts merge into @corresp; remove parts, add unified.
        state.difference_update(move.who)
        state.update(move.corresp)
    elif move.type == "onStage":
        # `onStage` with @who means "these characters are currently on stage".
        # Without @who it marks an empty stage (start/end of play).
        if move.who:
            state.update(move.who)
        else:
            state.clear()
    elif move.type == "state-change":
        # Annotation-only marker: the @ana tokens carry perception / visibility
        # / vitality state info for the directed-perception app.  The stage
        # state SET is unchanged -- the character was already on stage and
        # remains so; only their state-on-stage shifts.  The undirected
        # SkeneGraph-Net does not read those tokens.
        pass
    elif move.type == "crossing":
        # Annotation-only marker: a round trip completed inside one beat.  The
        # stage state SET is unchanged -- whoever crossed was not on stage
        # before and is not on stage after -- so they join no segment's cast
        # and form no edge.  The event stays countable through the <move>
        # itself (see Segment.num_crossings).
        pass
    # Unknown move types are silently ignored.


# Controlled @subtype vocabulary for the new annotation schema.  Tokens
# are grouped by axis; one token per axis is allowed.  See `Move.subtype`
# docstring for the full meaning.
_SUBTYPE_AXES: Dict[str, frozenset] = {
    "location":      frozenset({"stage", "voice-only"}),
    "visibility":    frozenset({"unhidden", "hidden"}),
    "capacity":      frozenset({"awake", "asleep"}),
    "vitality":      frozenset({"alive", "dead"}),
    "engagement":    frozenset({"aware", "unaware"}),
    # The five axes above qualify a character's state while on stage.  The
    # `crossing` axis is different in kind: it says what a `crossing` was, the
    # type having already said that no occupancy changed.  Kept in the same
    # attribute because it answers the same sort of question -- how to read the
    # move -- and so that a further purpose costs a token, not a new @type.
    #   fetch-prop: a figure seen in passing, bringing a property on.
    #   signal-off: a figure heard from off-stage, no verse assigned.
    "crossing":      frozenset({"fetch-prop", "signal-off"}),
}
_ALL_SUBTYPE_TOKENS: frozenset = frozenset().union(*_SUBTYPE_AXES.values())

# Move types that may (or must not) carry a @subtype attribute.
# Permissive parsing: violations log warnings, never raise.
_SUBTYPE_ALLOWED_ON   = frozenset({"entrance", "onStage", "state-change", "crossing"})
_SUBTYPE_REQUIRED_ON  = frozenset({"state-change", "crossing"})
_SUBTYPE_FORBIDDEN_ON = frozenset({"exit", "merge", "split"})


def _parse_move_states(ana_raw: Optional[str], subtype_raw: Optional[str],
                       move_type: str, source_line: Optional[int]) -> Set[str]:
    """Parse the character-state tokens carried by a <move> element.

    Primary source is @ana: space-separated #-references into the
    `move-ana` interpGrp (e.g. `ana="#voice-only #asleep"`).  This is
    the TEI-canonical way to attach multiple controlled-vocabulary
    categories to an element.  The leading `#` is stripped.

    Legacy fallback is @subtype: bare tokens used by the original
    encoding convention before the migration to @ana.  Still read so the
    parser doesn't break mid-migration, but emits a deprecation warning
    whenever it fires.  Once every TEI file has been migrated to @ana,
    this branch can be removed.

    Schema-violation warnings (state-change and crossing require; exit
    forbids; unknown tokens; crossing/state direction; multi-axis conflicts)
    apply identically regardless of which attribute carried the tokens.
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
    # Direction check (mirrors skenegraph.sch): the crossing axis is carried
    # by `crossing` alone, and a crossing carries nothing but that axis --
    # a state makes no claim about a figure present for no measurable time.
    crossing_tokens = tokens & _SUBTYPE_AXES["crossing"]
    if move_type == "crossing":
        stray = tokens - _SUBTYPE_AXES["crossing"]
        if stray:
            log.warning(
                "crossing at line %s carries state token(s) %s; a crossing "
                "names what it was (%s), not a state",
                source_line, sorted(stray),
                ", ".join("#" + t for t in sorted(_SUBTYPE_AXES["crossing"])),
            )
    elif crossing_tokens:
        log.warning(
            "move type=%r at line %s carries crossing token(s) %s; that "
            "vocabulary belongs to type 'crossing' only",
            move_type, source_line, sorted(crossing_tokens),
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
            "move type=%r at line %s lacks @ana tokens "
            "(a state-change must name the target state; a crossing "
            "what it was)",
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


# What a speech holds that is not spoken.  <note> is the editor speaking (a
# gesture gloss, a remark on line numbering), and <gap> marks text that is
# not there.  <speaker> is the label the edition prints, and <stage> is a
# direction -- where neither stands inside the verse, the prose fallback in
# `_walk_body` reads the whole <sp> and would count them.  Everything else
# nested in the verse counts, <del> included -- a deleted line is text the
# edition still prints, and whether to athetise it is the editor's judgement,
# not the word counter's.
_NOT_SPOKEN = {"note", "gap", "speaker", "stage"}


def _spoken_text(elem) -> str:
    """Text of `elem` that counts as spoken, editorial matter removed.

    A skipped element's *tail* is kept: that is the verse resuming after the
    interruption, not part of the note.  Dropping it would lose real words --
    22 of them follow a <gap> in the corpus and 7 follow a <note>.

    The fragments are concatenated as the source has them, with no separator
    of our own.  An element boundary is not a word boundary: a <q> or <add>
    closing before the comma leaves that comma in the tail, and joining on a
    space would count it as a word; <supplied> can split a single word in
    two.  What the file says is what is counted, so a missing space in the
    source shows up as a joined word here rather than being papered over.
    """
    parts: List[str] = []

    def walk(node) -> None:
        # Comments and PIs are not spoken either; lxml's itertext() would
        # otherwise yield their bodies as words.
        if not isinstance(node.tag, str) or _local(node) in _NOT_SPOKEN:
            return
        if node.text:
            parts.append(node.text)
        for child in node:
            walk(child)
            if child.tail:
                parts.append(child.tail)

    walk(elem)
    return "".join(parts)


# The units a speech's text comes in: verse lines, and for prose drama
# paragraphs and anonymous blocks.  Counted one block at a time, so that two
# blocks written without whitespace between them (`<p>a</p><p>b</p>`) are
# not run together into one word.
_SPOKEN_BLOCKS = {"l", "p", "ab"}


def _spoken_blocks(elem) -> List:
    """The verse lines (or prose blocks) of `elem` that count as spoken.

    `findall(".//tei:l")` reaches the lines inside a <note> as well, and
    `_spoken_text` cannot save them: it runs on one line at a time and never
    sees the excluded ancestor above it, so an editor's quotation of verse
    was counted as the character's speech.  The exclusion therefore belongs
    on the way down, where the note's whole subtree can be left unentered --
    one rule for what is editorial, applied once.

    A block is not entered once taken: its whole text is counted from it, so
    a block inside it -- an <l> in a <p> -- would be counted twice.
    """
    out: List = []

    def walk(node) -> None:
        for child in node:
            if not isinstance(child.tag, str) or _local(child) in _NOT_SPOKEN:
                continue
            if _local(child) in _SPOKEN_BLOCKS:
                out.append(child)
            else:
                walk(child)

    walk(elem)
    return out


def _word_count(text: str) -> int:
    """Whitespace-separated tokens holding at least one letter or digit.

    A sign standing alone is not a word: the crux the edition sets off by
    spaces (†) marks the text as corrupt, and a spaced dash marks a break.
    The corpus has 87 such tokens -- crux, dash and a few stray full stops --
    and each was credited to a character as a word spoken.  A crux attached
    to a word (†λόγος) leaves the word, which counts.
    """
    return sum(1 for w in text.split() if any(c.isalnum() for c in w))


def _by_lang(elements) -> tuple:
    """Split repeated <titleStmt> elements by @xml:lang.

    Returns (grc, en, first-non-empty).  Titles and authors are both given
    twice in the corpus, once per language, so neither may be read by
    document order alone.
    """
    grc = en = first = ""
    for el in elements:
        text = (el.text or "").strip()
        if not text:
            continue
        if not first:
            first = text
        lang = el.get(XML_LANG)
        if lang == "grc" and not grc:
            grc = text
        elif lang == "en" and not en:
            en = text
    return grc, en, first


def _extract_genre(root) -> str:
    """Genre from <textClass>, as a `genre`-taxonomy category id.

    Accepts either <catRef scheme="#genre" target="#comedy"/> (the corpus
    convention, pointing into the taxonomy declared in <classDecl>) or a
    plain <classCode scheme="#genre">comedy</classCode>.  Returns "" when
    the play carries no classification, which the dashboards treat as
    "fall back to the author heuristic".
    """
    def _scheme_matches(el) -> bool:
        scheme = (el.get("scheme") or "").strip().lstrip("#")
        return scheme in ("", "genre")

    for ref in root.findall(".//tei:textClass/tei:catRef", NS):
        if _scheme_matches(ref):
            target = (ref.get("target") or "").strip().lstrip("#")
            if target:
                return target
    for code in root.findall(".//tei:textClass/tei:classCode", NS):
        if _scheme_matches(code):
            text = (code.text or "").strip()
            if text:
                return text
    return ""


def _latin_choice(el) -> tuple:
    """(full form, abbreviation) of a Latin title or author.

    The corpus gives both in a <choice>: <expan>Nubes</expan><abbr>Nub.</abbr>.
    Without one, the element's whole text is the full form and there is no
    abbreviation.
    """
    ex = el.find(".//tei:expan", NS)
    ab = el.find(".//tei:abbr", NS)
    full = ((ex.text or "").strip() if ex is not None
            else " ".join("".join(el.itertext()).split()))
    return full, ((ab.text or "").strip() if ab is not None else "")


# urn:cts:greekLit:tlg0019.tlg003.perseus-grc2 -> text group, work.  The
# edition that follows names one digital text of the play, not the play.
_CTS_WORK = re.compile(r"^urn:cts:[^:]+:([^:.\s]+)\.([^:.\s]+)", re.I)
# A bare TLG number, as the canon cites it: 0019.003, "TLG 0019 003".
_TLG_NUMBER = re.compile(r"(\d{1,4})\D+(\d{1,3})")


def _work_id(root) -> str:
    """The play's work identifier from the header, or "" when it has none.

    A CTS URN is preferred, kept to text group and work: `tlg0019.tlg003` for
    Clouds whichever edition the URN names.  An <idno type="TLG"> holding the
    canon number is accepted too and brought to the same form.
    """
    idnos = root.findall(".//tei:teiHeader//tei:idno", NS)
    for idno in idnos:
        if (idno.get("type") or "").strip().lower() in ("cts-urn", "cts", "urn"):
            m = _CTS_WORK.match((idno.text or "").strip())
            if m:
                return f"{m.group(1)}.{m.group(2)}"
    for idno in idnos:
        if (idno.get("type") or "").strip().lower() == "tlg":
            m = _TLG_NUMBER.search(idno.text or "")
            if m:
                return f"tlg{int(m.group(1)):04d}.tlg{int(m.group(2)):03d}"
    return ""


def _extract_metadata(root, play: PlayData, file_path: str) -> None:
    play.title_grc, play.title_en, first_title = _by_lang(
        root.findall(".//tei:titleStmt/tei:title", NS))
    if not play.title_en:
        play.title_en = first_title

    XLANG = "{http://www.w3.org/XML/1998/namespace}lang"
    for t in root.findall(".//tei:titleStmt/tei:title", NS):
        if t.get(XLANG) == "lat":
            play.title_lat, play.title_lat_abbr = _latin_choice(t)
            break

    play.author_grc, play.author_en, first_author = _by_lang(
        root.findall(".//tei:titleStmt/tei:author", NS))
    if not play.author_en:
        play.author_en = first_author
    play.author = play.author_en or play.author_grc
    for a in root.findall(".//tei:titleStmt/tei:author", NS):
        if a.get(XLANG) == "lat":
            play.author_lat, play.author_lat_abbr = _latin_choice(a)
            break

    play.genre = _extract_genre(root)

    # The play's identity is its work number, never its title: Sophocles and
    # Euripides both wrote an Electra.  Where the header names no work, the
    # file name stands in -- unique within a corpus directory, and said so.
    play.play_id = _work_id(root)
    if not play.play_id:
        play.play_id = Path(file_path).stem
        log.warning(
            "no work identifier in the header (<idno type=\"CTS-URN\"> or "
            "<idno type=\"TLG\">); the play is identified by its file name, %s",
            play.play_id)


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

    # Step 2: the performer category on the nested <actor ana="#..."> drives the
    # chorus flag.  Collective comes from <personGrp> (Step 1); muteness is
    # decided behaviourally further down (see `_classify_mutes`) -- the performer
    # category (#actor / #extra) deliberately does NOT touch it, so a silent role
    # cast to an actor stays behaviourally mute.  Back-compat: fall back to a
    # legacy @ana on the <castItem> itself when there is no <actor> child.
    for ci in root.findall(".//tei:castList/tei:castItem", NS):
        corresp = ci.get("corresp", "")
        cid = corresp.lstrip("#") if corresp else ""
        if not cid or cid not in play.characters:
            continue
        ch = play.characters[cid]
        actor_el = ci.find("tei:actor", NS)
        ana = (actor_el.get("ana") if actor_el is not None else None) or ci.get("ana", "")
        cats = {tok.lstrip("#") for tok in ana.split() if tok.strip()}
        if "speaker" in cats:          # legacy token; current vocab uses #actor
            ch.is_speaker_explicit = True
        if "collective" in cats:       # legacy; collective now from <personGrp>
            ch.is_collective = True
        if "chorus" in cats or "semichorus" in cats:
            ch.is_chorus = True


def _extract_relations(root, play: PlayData) -> None:
    """Pull <relation> entries out of every <listRelation> in the header.

    The corpus annotates split-chorus structure as

        <listRelation type="dramatic-structure">
          <relation name="partOf" active="#chorosGeronton" passive="#choros">...</relation>
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

    # Each part's wholes, transitively: a semichorus is part of the chorus,
    # and of whatever the chorus is part of.
    parents: Dict[str, Set[str]] = {}
    for rel in play.relations:
        if rel.name == "partOf":
            parents.setdefault(rel.active, set()).add(rel.passive)
    for cid, direct in parents.items():
        wholes = play.characters[cid].part_of
        todo = list(direct)
        while todo:
            whole = todo.pop()
            if whole == cid or whole in wholes:
                continue                  # a cycle, or reached twice
            wholes.add(whole)
            todo.extend(parents.get(whole, ()))


def _classify_mutes(play: PlayData) -> None:
    """Set `is_mute` from observed behaviour: a character is mute iff the play
    never attributes an utterance to them.

    A character is mute iff no <sp> has that character in @who.  This keeps
    the play-level and per-segment definitions in step:

        speaker-in-segment = an <sp> attributed in that segment
        play-mute (cat 2)  = speaker-in-segment for *no* segment

    The test is the <sp>, not the word count: a speech whose text is lost is
    still a speech (see `Segment.speakers`).  No character in the corpus is
    affected -- every textless <sp> belongs to a chorus that speaks at length
    elsewhere -- but the two definitions must not be allowed to drift.

    More reliable than trusting the editor's `#mute` annotation, which is
    frequently omitted on minor mute roles.
    """
    spoke: Set[str] = set()
    for sp in play.speeches:
        spoke |= sp.who
    for cid, ch in play.characters.items():
        ch.is_mute = cid not in spoke


def _walk_body(root, play: PlayData) -> None:
    """Single document-order walk through <body> collecting moves, speeches and div boundaries.

    `pos` is incremented for every move, speech and div element so the three
    streams can be re-interleaved later by the segmenters.
    """
    body = root.find(".//tei:body", NS)
    if body is None:
        return

    pos = 0
    cur_large_seq_pos: Optional[int] = None
    cur_large_seq_id: Optional[str] = None
    cur_large_seq_type: Optional[str] = None
    cur_middle_seq_pos: Optional[int] = None
    cur_middle_seq_id: Optional[str] = None
    cur_stage_pos: Optional[int] = None
    cur_stage_line: Optional[int] = None
    stage_counter = 0
    # A <move> outside any <stage> breaks the schema.  Read leniently, as
    # every other violation is: consecutive bare moves with no speech or
    # <stage> between them form one beat, as a <stage> would have made them.
    # Left keyed on None, they all fell into one cluster with the first of
    # them, and no later bare move opened a segment.
    bare_stage: Optional[int] = None
    bare_stage_line: Optional[int] = None
    bare_lines: List[int] = []

    sp_depth = 0  # so we don't double-walk into <sp>'s descendants

    for event, elem in etree.iterwalk(body, events=("start", "end")):
        name = _local(elem)
        if event == "start":
            if name == "milestone":
                # Segmentation milestones: an empty point that opens a unit
                # running until the next milestone of the same level.
                # unit="large-seq" opens a coarse (act-like) unit, "middle-seq"
                # a finer (scene-like) one.
                #
                # Primary stream only: a milestone carrying @source (or legacy
                # @resp) belongs to a parallel scholarly segmentation, which the
                # schema admits but this app does not yet read.  Ignoring it here
                # keeps the primary views correct for files that carry such
                # streams; multi-stream reading is a potential future feature.
                if elem.get("source") or elem.get("resp"):
                    continue
                unit = elem.get("unit")
                if unit == "large-seq":
                    pos += 1
                    cur_large_seq_pos = pos
                    cur_large_seq_id = elem.get(XML_ID)
                    cur_large_seq_type = elem.get("type")
                    play.large_seqs.append(Div(
                        level=2,
                        xml_id=elem.get(XML_ID),
                        n=None,
                        type=cur_large_seq_type,
                        pos=cur_large_seq_pos,
                    ))
                elif unit == "middle-seq":
                    pos += 1
                    cur_middle_seq_pos = pos
                    cur_middle_seq_id = elem.get(XML_ID)
                    play.middle_seqs.append(Div(
                        level=3,
                        xml_id=cur_middle_seq_id,
                        n=None,
                        type=None,
                        pos=cur_middle_seq_pos,
                        parent_large_seq_id=cur_large_seq_id,
                        parent_large_seq_type=cur_large_seq_type,
                    ))
            elif name == "stage":
                stage_counter += 1
                cur_stage_pos = stage_counter
                cur_stage_line = elem.sourceline
                bare_stage = None
            elif name == "move":
                pos += 1
                m_type = (elem.get("type") or "").strip()
                stage_pos, stage_line = cur_stage_pos, cur_stage_line
                if stage_pos is None:
                    if bare_stage is None:
                        stage_counter += 1
                        bare_stage = stage_counter
                        bare_stage_line = elem.sourceline
                    stage_pos, stage_line = bare_stage, bare_stage_line
                    bare_lines.append(elem.sourceline)
                play.moves.append(Move(
                    type=m_type,
                    who=_refs(elem.get("who")),
                    corresp=_refs(elem.get("corresp")),
                    subtype=_parse_move_states(
                        elem.get("ana"), elem.get("subtype"),
                        m_type, elem.sourceline),
                    pos=pos,
                    large_seq_pos=cur_large_seq_pos,
                    large_seq_id=cur_large_seq_id,
                    large_seq_type=cur_large_seq_type,
                    middle_seq_pos=cur_middle_seq_pos,
                    middle_seq_id=cur_middle_seq_id,
                    source_line=elem.sourceline,
                    stage_pos=stage_pos,
                    stage_line=stage_line,
                ))
            elif name == "sp" and sp_depth == 0:
                sp_depth = 1
                pos += 1
                bare_stage = None
                # Count words across the verse of the <sp> (the sole speech-
                # quantity unit; verse-line counting was removed because
                # antilabai split one metrical line across speakers and lyric
                # lines vary wildly in length, so line counts misrepresent how
                # much a character actually says).  What is not spoken is
                # dropped twice over: `_spoken_blocks` never enters a note,
                # and `_spoken_text` drops what a spoken block holds;
                # `_NOT_SPOKEN` is the one list of it.
                blocks = _spoken_blocks(elem)
                word_count = sum(_word_count(_spoken_text(b)) for b in blocks)
                # No block at all: fall back to the speech's own text, which
                # `_spoken_text` reads without its <speaker> and <stage>.
                if not blocks:
                    word_count = _word_count(_spoken_text(elem))
                play.speeches.append(Speech(
                    who=_refs(elem.get("who")),
                    addressees=_refs(elem.get("toWhom")),
                    word_count=word_count,
                    pos=pos,
                    large_seq_pos=cur_large_seq_pos,
                    large_seq_id=cur_large_seq_id,
                    large_seq_type=cur_large_seq_type,
                    middle_seq_pos=cur_middle_seq_pos,
                    middle_seq_id=cur_middle_seq_id,
                    source_line=elem.sourceline,
                ))
            elif name == "sp":
                sp_depth += 1
        else:  # end
            if name == "stage":
                cur_stage_pos = None
                cur_stage_line = None
            elif name == "sp":
                sp_depth -= 1

    if bare_lines:
        log.warning(
            "%d move(s) stand outside any <stage> (first at line %s); the "
            "schema encloses every move in one.  Consecutive bare moves with "
            "no speech between them are read as one beat",
            len(bare_lines), bare_lines[0],
        )


def _validate_references(play: PlayData) -> None:
    """Warn on @who / @corresp / @toWhom ids not declared in <listPerson>.

    A misspelt id fails silently otherwise: it creates a phantom character
    that the stage-state machine tracks, while the intended character is left
    untouched -- e.g. an entrance that never brings them back on stage, so
    they vanish from every segment in which they are present but silent.
    Permissive as everywhere else: the id is kept, the error is only logged.
    """
    known = set(play.characters)
    for mv in play.moves:
        for attr, ids in (("who", mv.who), ("corresp", mv.corresp)):
            for cid in sorted(ids - known):
                log.warning(
                    "move type=%r at line %s references undeclared id #%s "
                    "in @%s (not in <listPerson>)",
                    mv.type, mv.source_line, cid, attr,
                )
    for sp in play.speeches:
        for attr, ids in (("who", sp.who), ("toWhom", sp.addressees)):
            for cid in sorted(ids - known):
                log.warning(
                    "sp at line %s references undeclared id #%s in @%s "
                    "(not in <listPerson>)",
                    sp.source_line, cid, attr,
                )


def _validate_stage_states(play: PlayData) -> None:
    """Warn when a `state-change` targets a character who is not on stage.

    `state-change` shifts a present character's perception / visibility /
    vitality state; it never puts anyone on stage.  Aimed at
    an absent character it is a silent no-op, which normally means the
    preceding entrance is missing or misspelt.
    """
    state: Set[str] = set()
    for mv in play.moves:
        if mv.type == "state-change":
            absent = sorted(mv.who - state)
            if absent:
                log.warning(
                    "move type='state-change' at line %s targets %s, who "
                    "%s not on stage at that point; state-change cannot add "
                    "characters (is an entrance missing or misspelt?)",
                    mv.source_line,
                    ", ".join("#" + c for c in absent),
                    "is" if len(absent) == 1 else "are",
                )
        apply_move(state, mv)


def _validate_speakers_on_stage(play: PlayData) -> None:
    """Warn when a speech is attributed to someone the moves have not put on
    stage.

    The segmenters place a speaker in the segment they speak in regardless,
    so the graphs do not lose them; but a speech from off the stage state
    normally means an entrance is missing or misspelt, and the character is
    then absent from every segment in which they stand silent.  A voice from
    off is encoded as an entrance with #voice-only, which this check accepts.
    """
    state: Set[str] = set()
    for item in sorted(list(play.moves) + list(play.speeches),
                       key=lambda x: x.pos):
        if isinstance(item, Move):
            apply_move(state, item)
            continue
        off = sorted(item.who - state)
        if off:
            log.warning(
                "sp at line %s is attributed to %s, who %s not on stage at "
                "that point (is an entrance missing or misspelt?); the speech "
                "still places them in its segment",
                item.source_line, ", ".join("#" + c for c in off),
                "is" if len(off) == 1 else "are",
            )


def _validate_spine_coverage(play: PlayData) -> None:
    """Warn when content stands before a spine's first milestone.

    A speech or move ahead of the first `<milestone unit="large-seq"/>` has
    no unit to belong to, and the milestone segmenters emit one segment per
    declared unit: the unkeyed content is never emitted.  For a move that
    costs little -- its effect on the stage state carries into the first
    unit's bucket all the same -- but a speech loses its words and its
    speaker from that spine's segment table, which then no longer reconciles
    with the play's word total, though the stage-direction spine still does.

    Silence was the odd one out here.  Every other schema violation the
    parser meets is logged and parsed through; this one changed the numbers
    and said nothing.
    """
    for unit, divs, attr in (("large-seq", play.large_seqs, "large_seq_pos"),
                             ("middle-seq", play.middle_seqs, "middle_seq_pos")):
        if not divs:
            continue          # spine not annotated: nothing to fall outside
        speeches = [s for s in play.speeches if getattr(s, attr) is None]
        moves = [m for m in play.moves if getattr(m, attr) is None]
        if not speeches and not moves:
            continue
        words = sum(s.attributed_words for s in speeches)
        first = min((i.source_line for i in speeches + moves if i.source_line),
                    default=None)
        log.warning(
            "%d speech(es) (%d words) and %d move(s) stand before the first "
            "%s milestone (from line %s); they fall outside every %s segment, "
            "so that spine's segment table will not reconcile with the play's "
            "word total",
            len(speeches), words, len(moves), unit, first, unit,
        )


def _validate_spine_alignment(play: PlayData) -> None:
    """Warn when a middle-seq unit straddles a large-seq boundary.

    The two milestone spines are ranked, so a large-seq boundary is also a
    middle-seq boundary and every middle-seq unit falls inside exactly one
    large-seq unit.  A middle-seq whose content lands in two large-seq units
    means one of the milestones is misplaced -- typically a large-seq
    milestone dropped into the middle of a scene.

    Skipped unless the file carries both spines, so a partially annotated
    play does not report the annotation it has not received yet.
    """
    if not play.large_seqs or not play.middle_seqs:
        return
    units: Dict[int, Dict] = {}
    for item in sorted(list(play.speeches) + list(play.moves),
                       key=lambda x: x.pos):
        if item.middle_seq_pos is None:
            continue
        unit = units.setdefault(item.middle_seq_pos, {
            "id": item.middle_seq_id,
            "line": item.source_line,
            "large": set(),
        })
        unit["large"].add(item.large_seq_pos)
    for pos, unit in sorted(units.items()):
        if len(unit["large"]) > 1:
            log.warning(
                "middle-seq unit %s (from line %s) straddles a large-seq "
                "boundary: its content falls in %d large-seq units; a "
                "large-seq milestone must coincide with a middle-seq one",
                unit["id"] or f"at position {pos}", unit["line"],
                len(unit["large"]),
            )


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
    # Entities declared in the file's own DTD are expanded; external ones --
    # `<!ENTITY x SYSTEM "file:///...">` -- are never loaded, and a file that
    # uses one is refused as a syntax error, so a TEI file from elsewhere
    # cannot pull a local file into the titles and names the dashboard
    # embeds.  lxml has defaulted to this since 5.0 (hence the floor in
    # requirements.txt); it is spelled out so it does not rest on the
    # installed version.
    xml_parser = etree.XMLParser(resolve_entities="internal", no_network=True)
    tree = etree.parse(file_path, xml_parser)
    root = tree.getroot()
    _extract_metadata(root, play, file_path)
    _extract_characters(root, play)
    _extract_relations(root, play)
    _walk_body(root, play)

    # Behavioural mute classification: a character is mute iff no <sp> in the
    # play names them in @who.  The test is the speech, not its length -- a
    # speech whose text is lost is still a speech -- so this is not a
    # word-count rule; see `_classify_mutes`.  Run AFTER `_walk_body`, so all
    # speeches are available.
    _classify_mutes(play)

    # Annotation-schema validation.  Every check only logs: a corpus with
    # errors still loads, exactly like the @ana / @subtype vocabulary checks.
    _validate_references(play)
    _validate_stage_states(play)
    _validate_speakers_on_stage(play)
    _validate_spine_coverage(play)
    _validate_spine_alignment(play)

    # Chorus status comes from the castList entry's #chorus / #semichorus and
    # from nowhere else.  An id-pattern fallback stood here, left over from
    # the heuristic that annotation replaced: it tested `chor` against the id
    # and against the Greek name -- where a Latin `chor` cannot occur -- and
    # then rescued only ids that were exactly `choros` / `chorus` or held
    # `semichor`.  On the corpus it rescued nobody, every chorus figure being
    # annotated; on an unannotated file it would have marked a chorus while
    # leaving its own halves unmarked, which is the failure the annotation
    # was introduced to end.
    return play


__all__ = [
    "Character", "Move", "Speech", "Div", "Relation", "PlayData", "parse_play",
    "apply_move",
]
