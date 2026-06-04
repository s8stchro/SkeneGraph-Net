# Example data

This directory holds a single sample play so that SkeneGraph-Net runs
out-of-the-box, without the full corpus checked out:

```sh
python app.py analyze examples/Ar-07-Lys.xml
```

## `Ar-07-Lys.xml` — Aristophanes, *Lysistrata* (Λυσιστράτη)

A TEI-encoded edition in the SkeneGraph schema. Its provenance and licensing,
recorded in full in the file's `<teiHeader>`, are:

* **Base Greek text** — Perseus Digital Library,
  `tlg0019.tlg007.perseus-grc2`
  (CTS-URN `urn:cts:greekLit:tlg0019.tlg007.perseus-grc2`), digitised under the
  supervision of Lisa Cerrato, William Merrill, Elli Mylonas, and David Smith;
  TEI P5 / EpiDoc conversion by Aurélien Berra; PI Gregory Crane, Perseus
  Project, Tufts University. Licensed **CC BY-SA 4.0**.
* **Editorial additions** — scene divisions, dramatic-structure annotations, and
  stage directions — prepared by Stylianos Chronopoulos (2025), released under
  the same **CC BY-SA 4.0** licence.

## Licensing note

This sample **data** is licensed **CC BY-SA 4.0**, *not* the Apache-2.0 licence
that covers the SkeneGraph-Net **software**. If you redistribute the file or
derivatives of it, attribute Perseus and the editor and keep the ShareAlike
terms.

The sample is drawn from the wider SkeneGraph corpus, published separately:
<https://zenodo.org/records/18505804>.
