"""A numeric fingerprint of the demo play, shared by the baseline test and
the regeneration script.

The fingerprint is a flat dict of scalars so that a failing comparison
names exactly which quantity moved.  Floats are rounded to keep the
comparison free of platform noise.
"""

from __future__ import annotations

from typing import Dict

from metrics import (compute_demographics, compute_metrics,
                     compute_segment_indices, compute_speech_distribution,
                     compute_temporal_gini)
from network import build_static
from segmentation import SEGMENTERS, fold_for_model

MODELS = {
    "full":    dict(include_mutes=True,  segment_cast="stage"),
    "p-speaking": dict(include_mutes=False, segment_cast="stage"),
    "s-speaking": dict(include_mutes=False, segment_cast="speaking"),
}

ROUND = 6


def compute_fingerprint(play) -> Dict[str, object]:
    fp: Dict[str, object] = {}

    # -- play level ---------------------------------------------------------
    fp["play.characters"] = len(play.characters)
    fp["play.moves"] = len(play.moves)
    fp["play.speeches"] = len(play.speeches)
    # Attributed, like every other word figure in the app: a joint <sp>
    # counts once per speaker, so this agrees with the per-spine totals below
    # and with speech.total_words_spoken.
    fp["play.words"] = sum(s.attributed_words for s in play.speeches)
    fp["play.large_seqs"] = len(play.large_seqs)
    fp["play.middle_seqs"] = len(play.middle_seqs)
    fp["play.partof_relations"] = sum(1 for r in play.relations
                                      if r.name == "partOf")

    dem = compute_demographics(play)
    for key in ("speakers", "mutes", "individuals", "collectives",
                "collective_speakers"):
        fp[f"demographics.{key}"] = dem[key]
    for key, value in sorted(dem["sex"].items()):
        fp[f"demographics.sex.{key}"] = value
    for key, value in sorted(dem["nature"].items()):
        fp[f"demographics.nature.{key}"] = value

    sd = compute_speech_distribution(play)
    fp["speech.total_words_spoken"] = sd["total_words_spoken"]
    fp["speech.top_speaker_id"] = sd["top_speaker_id"]
    fp["speech.top_speaker_ids"] = "|".join(sd["top_speaker_ids"])
    fp["speech.top_speaker_word_share"] = round(sd["top_speaker_word_share"], ROUND)
    fp["speech.gini_words"] = round(sd["gini_words"], ROUND)
    fp["speech.effective_speakers"] = round(sd["effective_speakers"], ROUND)

    # -- per spine ----------------------------------------------------------
    for spine, segmenter in sorted(SEGMENTERS.items()):
        segs = segmenter(play)
        fp[f"{spine}.segments"] = len(segs)
        fp[f"{spine}.words"] = sum(s.word_count for s in segs)

        idx = compute_segment_indices(segs)
        fp[f"{spine}.all_in_segment"] = idx["all_in_segment"]
        fp[f"{spine}.all_in_index"] = round(idx["all_in_index"], ROUND)
        fp[f"{spine}.final_segment_cast_share"] = round(idx["final_segment_cast_share"], ROUND)
        fp[f"{spine}.max_simultaneous_speakers"] = idx["max_simultaneous_speakers"]

        tg = compute_temporal_gini(segs)
        fp[f"{spine}.tgini_characters"] = len(tg)
        # A value, not just a count: the fingerprint held no tGini number at
        # all, so the span change from the whole play to each character's own
        # presence moved nothing here.  The top speaker's is the one the
        # corpus table prints.
        if tg:
            top = max(tg, key=lambda c: tg[c]["total_words"])
            fp[f"{spine}.tgini_top"] = round(tg[top]["temporal_gini"], ROUND)
            fp[f"{spine}.tgini_top_onstage_segments"] = \
                tg[top]["n_onstage_segments"]

        for model, kwargs in sorted(MODELS.items()):
            G = build_static(segs, play.characters, **kwargs)
            m = compute_metrics(G)
            prefix = f"{spine}.{model}"
            fp[f"{prefix}.order"] = m["size"]
            fp[f"{prefix}.edges"] = m["numEdges"]
            fp[f"{prefix}.density"] = round(m["density"], ROUND)
            fp[f"{prefix}.average_degree"] = round(m["averageDegree"], ROUND)
            fp[f"{prefix}.max_degree"] = m["maxDegree"]
            fp[f"{prefix}.components"] = m["numConnectedComponents"]

            if spine == "sd":
                # Fold through the app's own routine, not a copy of it: this
                # line used to re-implement the rule and had drifted (it
                # folded s-speaking on `speakers & kept`, which the app has
                # never done), so the baseline was guarding a spine that did
                # not exist.
                fp[f"{prefix}.folded_segments"] = len(
                    fold_for_model(segs, set(G.nodes()), kwargs["segment_cast"]))

    return fp
