"""TEI parsing: cast extraction, speech counting, move vocabulary, validation."""

from __future__ import annotations

import logging

import pytest

from conftest import PARSER_LOGGER, milestone, move, sp, stage
from parser import Speech, apply_move


# ---------------------------------------------------------------------------
# Cast extraction
# ---------------------------------------------------------------------------

TITLES_BOTH = ('        <title xml:lang="grc">Νεφέλαι</title>\n'
               '        <title xml:lang="en">Clouds</title>')
AUTHORS_BOTH = ('        <author xml:lang="grc">Ἀριστοφάνης</author>\n'
                '        <author xml:lang="en">Aristophanes</author>')


def _textclass(genre: str, scheme: str = "#genre") -> str:
    return (f'      <textClass>\n'
            f'        <catRef scheme="{scheme}" target="#{genre}"/>\n'
            f'      </textClass>')


# ---------------------------------------------------------------------------
# teiHeader metadata: title, author, genre, play id
# ---------------------------------------------------------------------------

def test_title_is_split_by_language(tiny_play):
    play = tiny_play(["a"], sp("a", "x"), titles=TITLES_BOTH)
    assert play.title_grc == "Νεφέλαι"
    assert play.title_en == "Clouds"


def test_author_is_split_by_language(tiny_play):
    """Authors are given twice, once per language, so document order must not
    decide which one is read."""
    play = tiny_play(["a"], sp("a", "x"), authors=AUTHORS_BOTH)
    assert play.author_grc == "Ἀριστοφάνης"
    assert play.author_en == "Aristophanes"
    assert play.author == "Aristophanes"      # display form


def test_author_falls_back_to_greek_when_no_english(tiny_play):
    authors = '        <author xml:lang="grc">Ἀριστοφάνης</author>'
    play = tiny_play(["a"], sp("a", "x"), authors=authors)
    assert play.author == "Ἀριστοφάνης"


def _source_with(*idnos: str) -> str:
    """A <sourceDesc> carrying the given <idno> elements, as the corpus has."""
    inner = "\n".join(f"            {i}" for i in idnos)
    return (f"      <sourceDesc>\n        <bibl type=\"digitalSource\">\n"
            f"{inner}\n        </bibl>\n      </sourceDesc>")


def test_play_id_is_the_tlg_work_from_the_cts_urn(tiny_play):
    """The title does not identify a play -- Sophocles and Euripides both
    wrote an Electra -- the work number does.  The URN's edition names one
    digital text of the play, not the play, and is dropped."""
    urn = ('<idno type="CTS-URN">'
           'urn:cts:greekLit:tlg0019.tlg003.perseus-grc2</idno>')
    play = tiny_play(["a"], sp("a", "x"), titles=TITLES_BOTH,
                     file_extra=_source_with(urn))
    assert play.play_id == "tlg0019.tlg003"
    assert play.title_en == "Clouds"          # the title is still the title


def test_a_bare_tlg_number_is_brought_to_the_same_form(tiny_play):
    play = tiny_play(["a"], sp("a", "x"),
                     file_extra=_source_with('<idno type="TLG">0011.005</idno>'))
    assert play.play_id == "tlg0011.tlg005"


def test_the_cts_urn_wins_over_a_tlg_number(tiny_play):
    play = tiny_play(["a"], sp("a", "x"), file_extra=_source_with(
        '<idno type="TLG">0006.012</idno>',
        '<idno type="CTS-URN">urn:cts:greekLit:tlg0011.tlg005.perseus-grc2</idno>'))
    assert play.play_id == "tlg0011.tlg005"


def test_without_an_identifier_the_file_name_stands_in(tiny_play, caplog):
    """Unique within a corpus directory, and said so rather than assumed."""
    with caplog.at_level("WARNING", logger=PARSER_LOGGER):
        play = tiny_play(["a"], sp("a", "x"), titles=TITLES_BOTH)
    assert play.play_id.startswith("tiny_")
    assert play.play_id != "Clouds"
    assert "no work identifier" in caplog.text


def test_the_latin_author_and_its_abbreviation_are_read(tiny_play):
    """The author's citation form is what separates two plays of one title
    on a chart: Soph. El., Eur. El."""
    authors = ('        <author xml:lang="en">Sophocles</author>\n'
               '        <author xml:lang="lat"><choice><expan>Sophocles</expan>'
               '<abbr>Soph.</abbr></choice></author>')
    play = tiny_play(["a"], sp("a", "x"), authors=authors)
    assert play.author == "Sophocles"
    assert (play.author_lat, play.author_lat_abbr) == ("Sophocles", "Soph.")


def test_genre_from_catref(tiny_play):
    play = tiny_play(["a"], sp("a", "x"), profile_extra=_textclass("comedy"))
    assert play.genre == "comedy"


def test_genre_from_classcode(tiny_play):
    extra = ('      <textClass>\n'
             '        <classCode scheme="#genre">tragedy</classCode>\n'
             '      </textClass>')
    play = tiny_play(["a"], sp("a", "x"), profile_extra=extra)
    assert play.genre == "tragedy"


def test_genre_ignores_other_schemes(tiny_play):
    play = tiny_play(["a"], sp("a", "x"),
                     profile_extra=_textclass("novel", scheme="#form"))
    assert play.genre == ""


def test_genre_is_empty_when_unclassified(tiny_play):
    play = tiny_play(["a"], sp("a", "x"))
    assert play.genre == ""


def test_demo_play_declares_its_genre(demo_play):
    assert demo_play.genre == "comedy"
    assert demo_play.author == "Aristophanes"
    assert demo_play.play_id == "tlg0019.tlg007"


def test_demo_cast_is_extracted(demo_play):
    assert demo_play.characters, "no characters parsed"
    assert demo_play.play_id
    assert all(c.id for c in demo_play.characters.values())


def test_chorus_status_is_annotated_never_guessed_from_the_id(tiny_play):
    """An id-pattern fallback stood here until it was found to rescue nobody.
    Guessing from the id marked a `choros` while leaving its own halves
    unmarked -- and missed a chorus named for what it is, like the frogs."""
    play = tiny_play(["choros:group", "batrachoi:group"],
                     sp("choros", "one") + "\n" + sp("batrachoi", "two"))
    assert play.characters["choros"].is_chorus is False
    assert play.characters["batrachoi"].is_chorus is False
    assert play.characters["choros"].is_collective is True


def test_the_demo_chorus_and_its_halves_are_all_flagged(demo_play):
    """The annotation path carries what the heuristic could not: the chorus
    and both semichoruses, whose ids the fallback's inner test excluded."""
    chorus = {c.id for c in demo_play.characters.values() if c.is_chorus}
    assert {"choros", "chorosGeronton", "chorosGynaikon"} <= chorus


def test_persongrp_is_collective(tiny_play):
    play = tiny_play(["hero", "crowd:group"], sp("hero", "a b"))
    assert play.characters["crowd"].is_collective is True
    assert play.characters["hero"].is_collective is False


@pytest.mark.parametrize("raw,expected", [
    ("male", "male"),
    ("female", "female"),
    ("MALE", "male"),              # the comparison is case-insensitive
    ("unknown", "unspecified"),
    ("irrelevant", "unspecified"),
    # `mixed` is a positive statement about a collective, not an absence of
    # information, and is counted apart from `unspecified`.
    ("mixed", "mixed"),
    (None, "unspecified"),
])
def test_sex_normalisation(tiny_play, raw, expected):
    spec = f"x::{raw}" if raw else "x"
    play = tiny_play([spec], sp("x", "a"))
    assert play.characters["x"].sex_class == expected


@pytest.mark.parametrize("raw,expected", [
    ("human", "human"),
    ("divine", "divine"),
    ("animal", "animal"),
    ("concept", "concept"),
    ("personified-concept", "concept"),
    ("abstraction", "concept"),
    ("gadget", "other"),
])
def test_nature_normalisation(tiny_play, raw, expected):
    play = tiny_play([f"x:::{raw}"], sp("x", "a"))
    assert play.characters["x"].nature_class == expected


# ---------------------------------------------------------------------------
# Speech quantity: words, never verse lines
# ---------------------------------------------------------------------------

def test_word_count_counts_words_not_lines(tiny_play):
    play = tiny_play(["a"], sp("a", "one two three", "four five"))
    assert len(play.speeches) == 1
    assert play.speeches[0].word_count == 5


def test_speech_has_no_verse_count_field():
    """Regression guard for the verse->word migration."""
    assert not hasattr(Speech(), "verse_count")


def test_empty_placeholder_speech_has_zero_words(tiny_play):
    play = tiny_play(["a"], sp("a"))
    assert play.speeches[0].word_count == 0


def test_antilabe_fragments_are_apportioned_by_words(tiny_play):
    """A shared line credits each speaker only their own words.

    The reason word count replaced verse-line count: a line counter would
    give each speaker of a split line a whole line.
    """
    body = sp("a", "three words here") + "\n" + sp("b", "two words")
    play = tiny_play(["a", "b"], body)
    counts = {list(s.who)[0]: s.word_count for s in play.speeches}
    assert counts == {"a": 3, "b": 2}


def test_joint_speech_credits_full_count_to_each_speaker(tiny_play):
    """`<sp who="#a #b">` is one Speech carrying both ids."""
    play = tiny_play(["a", "b"], sp("a b", "one two"))
    assert len(play.speeches) == 1
    assert play.speeches[0].who == {"a", "b"}
    assert play.speeches[0].word_count == 2


# ---------------------------------------------------------------------------
# Speech quantity: what inside the verse is spoken
# ---------------------------------------------------------------------------

def test_editorial_note_inside_a_line_is_not_spoken(tiny_play):
    """<note> is the editor speaking, so its words are not the character's.

    The verse resuming after the note is: two of the corpus's four in-line
    notes are followed by real text.
    """
    play = tiny_play(["a"], sp("a", "one <note>a scholarly remark</note> two three"))
    assert play.speeches[0].word_count == 3


def test_gap_is_not_spoken_and_the_line_resumes_after_it(tiny_play):
    """<gap> marks text that is not there; its tail is text that is."""
    play = tiny_play(["a"], sp("a", '<gap reason="not-transmitted"/> one two'))
    assert play.speeches[0].word_count == 2


def test_deleted_text_is_still_spoken(tiny_play):
    """<del> records an athetesis -- an editorial judgement about the line,
    not a claim that its words are absent from the edition."""
    play = tiny_play(["a"], sp("a", "one <del>two three</del> four"))
    assert play.speeches[0].word_count == 4


def test_xml_comment_inside_a_line_is_not_spoken(tiny_play):
    """lxml's itertext() yields comment bodies; the counter must not."""
    play = tiny_play(["a"], sp("a", "one <!-- two three --> four"))
    assert play.speeches[0].word_count == 2


def test_note_is_not_spoken_in_a_speech_without_verse_lines(tiny_play):
    """The no-<l> fallback counts the whole <sp>, editorial matter aside."""
    play = tiny_play(["a"], '<sp who="#a"><note>editorial</note>one two</sp>')
    assert play.speeches[0].word_count == 2


def test_content_before_the_first_milestone_is_reported(tiny_play, caplog):
    """A speech ahead of the first milestone has no unit to belong to, so the
    milestone spines drop it -- words, speaker and all -- while the play
    total keeps it.  The parser parses on, as it does with every other schema
    violation, but it no longer does so in silence."""
    body = "\n".join([
        stage(move("entrance", "a b")),
        sp("a", "one two three"),
        milestone("large-seq", "A1"),
        milestone("middle-seq", "S1"),
        sp("b", "four five"),
    ])
    with caplog.at_level("WARNING", logger=PARSER_LOGGER):
        play = tiny_play(["a", "b"], body)
    assert "before the first large-seq milestone" in caplog.text
    assert "before the first middle-seq milestone" in caplog.text
    assert "3 words" in caplog.text
    # parsed through, not refused
    assert sum(s.attributed_words for s in play.speeches) == 5


def test_a_play_with_no_milestones_is_not_reported(tiny_play, caplog):
    """Nothing to fall outside: a play may carry the stage-direction spine
    alone, and the two textual spines then do not exist."""
    with caplog.at_level("WARNING", logger=PARSER_LOGGER):
        tiny_play(["a"], stage(move("entrance", "a")) + "\n" + sp("a", "one"))
    assert "milestone" not in caplog.text


def test_a_well_formed_spine_is_not_reported(tiny_play, caplog):
    body = "\n".join([
        milestone("large-seq", "A1"),
        milestone("middle-seq", "S1"),
        stage(move("entrance", "a")),
        sp("a", "one two"),
    ])
    with caplog.at_level("WARNING", logger=PARSER_LOGGER):
        tiny_play(["a"], body)
    assert "stand before the first" not in caplog.text


def test_verse_quoted_inside_a_note_is_not_spoken(tiny_play):
    """The exclusion has to hold for a line inside a note, not only for a
    note inside a line: an editor quoting verse is still the editor."""
    play = tiny_play(["a"], '<sp who="#a"><l>one two</l>'
                            '<note><quote><l>editorial quoted verse</l>'
                            '</quote></note></sp>')
    assert play.speeches[0].word_count == 2


def test_verse_inside_a_gap_is_not_spoken(tiny_play):
    """Same rule, the other excluded element."""
    play = tiny_play(["a"], '<sp who="#a"><l>one two</l>'
                            '<gap reason="lost"><l>three four five</l>'
                            '</gap></sp>')
    assert play.speeches[0].word_count == 2


def test_a_speech_whose_only_verse_is_in_a_note_falls_back_to_its_text(tiny_play):
    """With the quoted line excluded the speech has no verse left, so the
    no-<l> fallback counts the <sp> -- itself minus the note."""
    play = tiny_play(["a"], '<sp who="#a">direct text here'
                            '<note><l>quoted verse</l></note></sp>')
    assert play.speeches[0].word_count == 3


def test_an_element_boundary_inside_a_word_does_not_split_it(tiny_play):
    """<supplied> and its like fall where the editor needed them, which is
    not where the words end."""
    play = tiny_play(["a"], sp("a", "hel<supplied>lo</supplied> world"))
    assert play.speeches[0].word_count == 2


def test_punctuation_left_in_a_tail_is_not_a_word(tiny_play):
    """A quotation or addition closing before the comma leaves the comma in
    the tail; it belongs to the word before it, not beside it.  Counting the
    fragments with a space between them made 30 such tokens in the corpus."""
    play = tiny_play(["a"], sp("a", "one <q>two three</q>, four"))
    assert play.speeches[0].word_count == 4


def test_a_missing_space_in_the_source_is_reported_not_repaired(tiny_play):
    """The counter says what the file says.  A verse encoded without the
    space before an element joins two words into one, and that is a defect
    to fix in the TEI rather than to paper over here."""
    play = tiny_play(["a"], sp("a", "one two<del>three</del> four"))
    assert play.speeches[0].word_count == 3


# ---------------------------------------------------------------------------
# Behavioural mute classification
# ---------------------------------------------------------------------------

def test_mute_is_sp_based_not_word_based(tiny_play):
    """A textless <sp> is still a speech, so its speaker is not a mute; muteness
    means the play never attributes an utterance at all (see the next test).
    Keeps `_classify_mutes` in step with `Segment.speakers`."""
    body = sp("lost_song") + "\n" + sp("talker", "a word")
    play = tiny_play(["lost_song", "talker"], body)
    assert play.characters["lost_song"].is_mute is False
    assert play.characters["talker"].is_mute is False


def test_character_never_in_who_is_mute(tiny_play):
    play = tiny_play(["a", "extra"], sp("a", "x"))
    assert play.characters["extra"].is_mute is True


def test_demo_has_both_speakers_and_mutes(demo_play):
    mutes = [c for c in demo_play.characters.values() if c.is_mute]
    speakers = [c for c in demo_play.characters.values() if not c.is_mute]
    assert mutes and speakers


# ---------------------------------------------------------------------------
# Milestones
# ---------------------------------------------------------------------------

def test_milestones_populate_both_spines(tiny_play):
    body = "\n".join([
        milestone("large-seq", "L01"),
        milestone("middle-seq", "s001"),
        sp("a", "x"),
        milestone("middle-seq", "s002"),
        sp("a", "y"),
        milestone("large-seq", "L02"),
        milestone("middle-seq", "s003"),
        sp("a", "z"),
    ])
    play = tiny_play(["a"], body)
    assert len(play.large_seqs) == 2
    assert len(play.middle_seqs) == 3
    assert [d.xml_id for d in play.large_seqs] == ["L01", "L02"]


def test_large_seq_type_is_read(tiny_play):
    """`@type` on a large-seq milestone reaches the Div (drives the choral
    divider marking); an untyped milestone carries no claim."""
    body = (milestone("large-seq", "L01") + "\n"
            + milestone("large-seq", "L02", type_="parabasis") + "\n"
            + sp("a", "x"))
    play = tiny_play(["a"], body)
    assert play.large_seqs[0].type is None
    assert play.large_seqs[1].type == "parabasis"


def test_parallel_stream_milestones_are_ignored(tiny_play):
    """A milestone carrying @source belongs to a parallel scholarly
    segmentation and must not disturb the primary spine."""
    body = (milestone("large-seq", "L01") + "\n"
            + '        <milestone unit="large-seq" xml:id="G01" source="#gelzer1960"/>\n'
            + sp("a", "x"))
    play = tiny_play(["a"], body)
    assert [d.xml_id for d in play.large_seqs] == ["L01"]


def test_demo_has_both_milestone_spines(demo_play):
    assert demo_play.large_seqs, "no large-seq milestones parsed"
    assert demo_play.middle_seqs, "no middle-seq milestones parsed"


# ---------------------------------------------------------------------------
# Move vocabulary
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("mtype,structural", [
    ("entrance", True),
    ("exit", True),
    ("onStage", True),
    ("merge", True),
    ("split", True),
    ("state-change", False),
])
def test_is_structural_vocabulary(tiny_play, mtype, structural):
    play = tiny_play(["a"], stage(move(mtype, "a", ana="#asleep"
                                      if mtype == "state-change" else "")))
    assert play.moves[0].is_structural is structural


def test_ana_tokens_are_parsed(tiny_play):
    play = tiny_play(["a"], stage(move("entrance", "a", ana="#hidden #asleep")))
    assert play.moves[0].subtype == {"hidden", "asleep"}


def test_legacy_subtype_still_read_with_warning(tiny_play, caplog):
    caplog.set_level(logging.WARNING, logger=PARSER_LOGGER)
    body = '        <stage><move type="entrance" who="#a" subtype="hidden"/></stage>'
    play = tiny_play(["a"], body)
    assert play.moves[0].subtype == {"hidden"}
    assert any("legacy @subtype" in r.getMessage() for r in caplog.records)


def test_unknown_ana_token_warns_but_is_kept(tiny_play, caplog):
    caplog.set_level(logging.WARNING, logger=PARSER_LOGGER)
    play = tiny_play(["a"], stage(move("entrance", "a", ana="#levitating")))
    assert "levitating" in play.moves[0].subtype
    assert any("unknown state token" in r.getMessage() for r in caplog.records)


def test_state_change_without_tokens_warns(tiny_play, caplog):
    caplog.set_level(logging.WARNING, logger=PARSER_LOGGER)
    body = stage(move("entrance", "a")) + "\n" + stage(move("state-change", "a"))
    tiny_play(["a"], body)
    assert any("lacks @ana tokens" in r.getMessage() for r in caplog.records)


# ---------------------------------------------------------------------------
# apply_move: stage-state transitions
# ---------------------------------------------------------------------------

def test_apply_move_transitions(tiny_play):
    play = tiny_play(
        ["a", "b", "g", "p1", "p2"],
        stage(move("entrance", "a b"))
        + "\n" + stage(move("exit", "b"))
        + "\n" + stage(move("split", "g", corresp="p1 p2"))
        + "\n" + stage(move("merge", "p1 p2", corresp="g"))
        + "\n" + stage(move("onStage", "")),
    )
    state = set()
    seen = []
    for mv in play.moves:
        apply_move(state, mv)
        seen.append(sorted(state))
    assert seen[0] == ["a", "b"]
    assert seen[1] == ["a"]
    assert seen[2] == ["a", "p1", "p2"]      # split: origin out, parts in
    assert seen[3] == ["a", "g"]             # merge: parts out, whole in
    assert seen[4] == []                     # bare onStage clears the stage


def test_state_change_does_not_alter_stage_set(tiny_play):
    play = tiny_play(
        ["a"],
        stage(move("entrance", "a")) + "\n"
        + stage(move("state-change", "a", ana="#asleep")),
    )
    state = set()
    apply_move(state, play.moves[0])
    before = set(state)
    apply_move(state, play.moves[1])
    assert state == before


# ---------------------------------------------------------------------------
# Schema validation warnings
# ---------------------------------------------------------------------------

def test_undeclared_id_in_move_warns(tiny_play, caplog):
    """The Wasps `#bedelykleon` class of typo."""
    caplog.set_level(logging.WARNING, logger=PARSER_LOGGER)
    tiny_play(["a"], stage(move("entrance", "a typo")))
    msgs = [r.getMessage() for r in caplog.records]
    assert any("undeclared id #typo" in m for m in msgs), msgs


def test_undeclared_id_in_speech_warns(tiny_play, caplog):
    caplog.set_level(logging.WARNING, logger=PARSER_LOGGER)
    tiny_play(["a"], sp("ghost", "a word"))
    assert any("undeclared id #ghost" in r.getMessage() for r in caplog.records)


def test_state_change_on_absent_character_warns(tiny_play, caplog):
    """Exactly the Wasps failure: exit, then a state-change that silently
    no-ops because the intended entrance never landed."""
    caplog.set_level(logging.WARNING, logger=PARSER_LOGGER)
    body = "\n".join([
        stage(move("entrance", "a")),
        stage(move("exit", "a")),
        stage(move("state-change", "a", ana="#asleep")),
    ])
    tiny_play(["a"], body)
    msgs = [r.getMessage() for r in caplog.records]
    assert any("not on stage at that point" in m for m in msgs), msgs


def test_state_change_on_present_character_is_silent(tiny_play, caplog):
    caplog.set_level(logging.WARNING, logger=PARSER_LOGGER)
    body = "\n".join([
        stage(move("entrance", "a")),
        stage(move("state-change", "a", ana="#asleep")),
    ])
    tiny_play(["a"], body)
    assert not [r for r in caplog.records if "not on stage" in r.getMessage()]


def _two_spine_body(aligned: bool) -> str:
    """A play with both spines; the second large-seq either coincides with a
    middle-seq boundary (aligned) or falls inside a middle-seq unit."""
    opening = [
        milestone("large-seq", "L01"),
        milestone("middle-seq", "s001"),
        stage(move("entrance", "a")),
        sp("a", "one"),
    ]
    if aligned:
        rest = [milestone("large-seq", "L02"),
                milestone("middle-seq", "s002"),
                sp("a", "two")]
    else:
        rest = [milestone("large-seq", "L02"),
                sp("a", "two"),
                milestone("middle-seq", "s002"),
                sp("a", "three")]
    return "\n".join(opening + rest)


def test_middle_seq_straddling_a_large_seq_boundary_warns(tiny_play, caplog):
    caplog.set_level(logging.WARNING, logger=PARSER_LOGGER)
    tiny_play(["a"], _two_spine_body(aligned=False))
    msgs = [r.getMessage() for r in caplog.records]
    assert any("straddles a large-seq boundary" in m for m in msgs), msgs


def test_aligned_spines_are_silent(tiny_play, caplog):
    caplog.set_level(logging.WARNING, logger=PARSER_LOGGER)
    tiny_play(["a"], _two_spine_body(aligned=True))
    assert not [r for r in caplog.records if "straddles" in r.getMessage()]


def test_spine_check_skipped_when_a_spine_is_absent(tiny_play, caplog):
    """A partially annotated play (large-seq only, as in Frogs) must not be
    reported for annotation it has not received yet."""
    caplog.set_level(logging.WARNING, logger=PARSER_LOGGER)
    body = "\n".join([
        milestone("large-seq", "L01"),
        stage(move("entrance", "a")),
        sp("a", "one"),
        milestone("large-seq", "L02"),
        sp("a", "two"),
    ])
    play = tiny_play(["a"], body)
    assert play.middle_seqs == []
    assert not [r for r in caplog.records if "straddles" in r.getMessage()]


def test_demo_play_is_schema_clean(demo_path, caplog):
    """The shipped demo must parse without schema warnings -- it is the
    reference encoding."""
    from parser import parse_play
    caplog.set_level(logging.WARNING, logger=PARSER_LOGGER)
    parse_play(demo_path)
    msgs = [r.getMessage() for r in caplog.records]
    assert msgs == [], "demo play emits parser warnings:\n" + "\n".join(msgs)


# ---------------------------------------------------------------------------
# Relations
# ---------------------------------------------------------------------------

def test_partof_relations_are_read(demo_play):
    partof = [r for r in demo_play.relations if r.name == "partOf"]
    assert partof, "demo play should declare partOf relations (split chorus)"
    for rel in partof:
        assert rel.active in demo_play.characters
        assert rel.passive in demo_play.characters


def test_part_of_is_transitive(tiny_play):
    """A semichorus is part of the chorus and of whatever the chorus is part
    of; the graph builders keep a part apart from every whole it belongs to."""
    rels = ('      <listRelation>\n'
            '        <relation name="partOf" active="#p" passive="#g"/>\n'
            '        <relation name="partOf" active="#g" passive="#top"/>\n'
            '      </listRelation>')
    play = tiny_play(["p:group", "g:group", "top:group"], sp("p", "x"),
                     profile_extra=rels)
    assert play.characters["p"].part_of == {"g", "top"}
    assert play.characters["g"].part_of == {"top"}
    assert play.characters["top"].part_of == set()


# ---------------------------------------------------------------------------
# What counts as a word
# ---------------------------------------------------------------------------

def test_editorial_signs_are_not_words(tiny_play):
    """A crux or a dash set off by spaces marks the text, it is not spoken;
    one attached to a word leaves the word to count."""
    play = tiny_play(["a"], stage(move("entrance", "a"))
                     + sp("a", "† καὶ — λόγος", "†ἔπεσε ."))
    assert play.speeches[0].word_count == 3


def test_prose_speech_counts_neither_label_nor_direction(tiny_play):
    """Without verse lines the speech's own text is read; its <speaker> label
    and a <stage> inside it are not speech, and two paragraphs written
    without whitespace between them are two runs of words, not one."""
    body = (stage(move("entrance", "a"))
            + '<sp who="#a"><speaker>LYSISTRATA</speaker>'
              '<stage>weeping loudly</stage><p>one two</p><p>three</p></sp>'
            + '<sp who="#a"><speaker>LYSISTRATA</speaker>four five</sp>')
    play = tiny_play(["a"], body)
    assert [s.word_count for s in play.speeches] == [3, 2]


def test_an_external_entity_is_not_read(tiny_path, tmp_path):
    """A file from elsewhere must not pull a local file into the dashboard."""
    from parser import parse_play
    secret = tmp_path / "secret.txt"
    secret.write_text("SECRET-CONTENT", encoding="utf-8")
    path = tiny_path(["a"], stage(move("entrance", "a")) + sp("a", "&leak; x"))
    text = path.read_text(encoding="utf-8")
    doctype = (f'<!DOCTYPE TEI [<!ENTITY leak SYSTEM "{secret.as_uri()}">]>\n')
    path.write_text(text.replace("<TEI ", doctype + "<TEI ", 1),
                    encoding="utf-8")
    from lxml import etree
    try:
        play = parse_play(path)
    except etree.XMLSyntaxError:
        return                  # refused outright: nothing was read
    assert "SECRET" not in repr(play.speeches[0]) + play.title_en


# ---------------------------------------------------------------------------
# Annotation gaps that change numbers are reported
# ---------------------------------------------------------------------------

def test_a_speaker_off_the_stage_state_is_reported(tiny_play, caplog):
    caplog.set_level(logging.WARNING, logger=PARSER_LOGGER)
    tiny_play(["a", "c"], stage(move("entrance", "a")) + sp("a", "one")
              + sp("c", "two"))
    msgs = [r.getMessage() for r in caplog.records]
    assert any("#c" in m and "not on stage" in m for m in msgs), msgs


def test_bare_moves_are_reported_and_grouped(tiny_play, caplog):
    caplog.set_level(logging.WARNING, logger=PARSER_LOGGER)
    body = "\n".join([move("entrance", "a"), sp("a", "one"),
                      move("exit", "a"), move("entrance", "b"), sp("b", "two")])
    play = tiny_play(["a", "b"], body)
    assert any("outside any <stage>" in r.getMessage() for r in caplog.records)
    clusters = [m.stage_pos for m in play.moves]
    assert clusters[0] is not None
    assert clusters[1] == clusters[2] != clusters[0]
