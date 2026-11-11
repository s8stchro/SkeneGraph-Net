# Example data

This directory holds two sample plays so that SkeneGraph-Net runs
out-of-the-box, without the full corpus checked out:

```sh
python app.py analyze examples/Ar-07-Lys.xml   # one play
python app.py corpus examples/                 # both, as a corpus
```

Both files are byte-for-byte copies of the plays as they stand in the
SkeneGraph corpus, which is the authoritative text and goes on being edited.
**Do not edit these files.** Refresh them instead:

```sh
python tests/refresh_example.py            # copy, then regenerate the baseline
python tests/refresh_example.py --dry-run  # report what has moved, change nothing
```

Where the corpus is checked out beside the app, `test_baseline.py` fails when
either copy has fallen behind it; where it is not, that check is skipped —
which is the case these bundled samples exist for.

## `Ar-07-Lys.xml` — Aristophanes, *Lysistrata* (Λυσιστράτη)

The demo play: the test suite's baseline, `tests/baseline_demo.json`, is a
fingerprint of this file. The refresh prints every fingerprint quantity that
changed, so an editorial change to the play is read once rather than turning
up later as an unexplained test failure.

## `Ar-01-Ach.xml` — Aristophanes, *Acharnians* (Ἀχαρνῆς)

A second play, so that the `corpus` command and the corpus dashboard can be
run on `examples/`. No baseline depends on it.

## Provenance

The provenance and licensing of each play, recorded in full in the file's
`<teiHeader>`, are:

* **Base Greek text** — Perseus Digital Library,
  `tlg0019.tlg007.perseus-grc2` (*Lysistrata*) and
  `tlg0019.tlg001.perseus-grc2` (*Acharnians*)
  (CTS-URNs `urn:cts:greekLit:tlg0019.tlg007.perseus-grc2` and
  `urn:cts:greekLit:tlg0019.tlg001.perseus-grc2`), digitised under the
  supervision of Lisa Cerrato, William Merrill, Elli Mylonas, and David Smith;
  TEI P5 / EpiDoc conversion by Aurélien Berra; PI Gregory Crane, Perseus
  Project, Tufts University. Licensed **CC BY-SA 4.0**.
* **Editorial additions** — scene divisions, dramatic-structure annotations, and
  stage directions — prepared by Stylianos Chronopoulos (2025), released under
  the same **CC BY-SA 4.0** licence.

## Licensing note

This sample **data** is licensed **CC BY-SA 4.0**, *not* the Apache-2.0 licence
that covers the SkeneGraph-Net **software**. If you redistribute the files or
derivatives of them, attribute Perseus and the editor and keep the ShareAlike
terms.

The samples are drawn from the wider SkeneGraph corpus, published separately:
<https://zenodo.org/records/18505804>.
