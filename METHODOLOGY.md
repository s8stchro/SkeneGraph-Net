# SkeneGraph-Net: Methodological premises and decisions

## Definition

SkeneGraph-Net is a Python application that takes as input one or several
dramatic texts annotated according to the TEI-compatible SkeneGraph schema and
produces undirected graphs and network metrics. Given a single file it reports
on one play; given several, it reports network metrics and charts across a
corpus.

SkeneGraph-Net is largely inspired by and based on the [DraCor](https://dracor.org)
platform, departing from it on four points:

1. It offers **three segmentation methods** and computes graphs and metrics for
   each of them.
2. It offers **three network models** spanning two orthogonal axes — whether
   non-speaking (mute) characters are admitted as nodes, and whether an edge
   means co-presence on stage or co-speech within a segment.
3. It can treat **collective figures** — the chorus and its subdivisions, which
   may appear as distinct collective persons in parts of a play — either as one
   node or as distinct nodes.
4. It produces a **dynamic graph** alongside the static one.

What follows sets out the premises behind these decisions. The full formal
reference — every metric, formula, and encoding — lives in the in-app *Methods*
panel of each dashboard (`methods_content.py`).

## A constructivist premise

SkeneGraph-Net is conceived as *data-assisted*, supporting the scholar in
controlling the data and the methods that produce them, and in transparently
producing different datasets by applying different methods. As Miguel Escobar
Varela argues in *Theater as Data* (2021), data in computational theatre
research are never neutral: they are constructed through decisions about what to
count, how to segment, and what relations to model. Transparency about these
decisions is essential. SkeneGraph-Net therefore exposes its methodological
options — segmentation method, cast filter and edge rule, collective-figure
handling — explicitly, so that scholars can examine how different assumptions
shape their understanding of dramatic structure rather than receiving a single
graph as given.

## Segmentation methods

A segmentation fixes what counts as a unit of co-presence. SkeneGraph-Net offers
three, computed in parallel:

* **`sd` (stage directions)** — a new segment opens after every `<move>`. This
  is the finest grain: it tracks who is on stage as entrances and exits unfold.
* **`div3` (scene)** — one segment per `<div3>`, the scene level.
* **`div2` (act)** — one segment per `<div2>`, the macro-structural / act level.

DraCor uses a single scene-based segmentation. Reading the same play under all
three makes segmentation *sensitivity* visible: a finer segmentation generally
lowers density and raises the number of segments, and the comparison is itself a
finding rather than noise to be smoothed away.

## Network models — two orthogonal axes

The central methodological choice in the app. Each model is a different decision
about what counts as a node and what counts as an edge, decomposed along two
independent axes:

1. **Cast filter** (play-level). Are play-level mute characters — those who
   never utter a verse line anywhere in the play — admitted as nodes?
2. **Edge rule** (segment-level). Does an edge mean *co-present on stage in the
   same segment*, or *speaking in the same segment*?

Three combinations are useful (the fourth — mutes admitted but edges by
co-speech — is incoherent, since mutes would be isolated nodes, and is not
generated):

| model | node set | edge `(u, v)` iff |
|---|---|---|
| **stage co-presence** *(default)* | all characters, including play-level mutes | both on stage in some segment |
| **dialogic cast, play level** | speakers only | both on stage in some segment |
| **dialogic cast, segment level** | speakers only | both *speak* in some segment |

Read together, the three models decompose a single comparative finding into two
independent contributions: how much of a network's shape is owed to silent
attendants admitted as nodes, and how much to silent co-presence among the
speakers themselves. DraCor offers a single speakers-only co-occurrence model;
SkeneGraph-Net makes the choice — and its consequences — legible.

## Collective figures

The chorus, and choral subdivisions that surface as distinct collective persons
in parts of a play (e.g. `chorosAndron` and `chorosGynaikon`, encoded `partOf`
`choros`), can be either aggregated to a single node or kept distinct. The
aggregation rewrites the cast so that members are absorbed into the group and the
chorus never visibly splits; keeping them distinct preserves moments where the
halves act — and co-occur — separately. Neither is the "correct" view; the choice
belongs to the reading.

## Dynamic graph

Alongside the static aggregate, SkeneGraph-Net builds a per-segment dynamic
graph, exported as a Gephi-renderable GEXF in which each node and edge carries
`<spells>` — the intervals during which it is active in the edge rule's sense.
This makes the temporal unfolding of co-presence available to inspection and
playback, where DraCor publishes the static aggregate only.
