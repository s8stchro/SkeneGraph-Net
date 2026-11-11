# Changelog

All notable changes to SkeneGraph-Net are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); this project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [2.0.0] — 2026-11-11

A major version, because the command line and the exported files changed
incompatibly with 1.0.x: `--seg div2` / `div3` are now `large-seq` /
`middle-seq`, `--no-mutes` gave way to `--export-model`, `--weight verses` is
gone, and several fields of `metrics.json` were renamed or redefined (each
marked **Breaking** below). Several metric definitions were also corrected, so
numbers differ from 1.0.x output; every such change is recorded here with what
it moved. The entries that stood under a 1.0.2 heading were never released on
their own and ship in this version.

### Fixed

- **The segment-level speaking fold holds every boundary to its own rule.**
  A boundary is invisible to that model only if nobody crossing it speaks in
  the merged segment. The fold checked each boundary against the speakers
  gathered by the time it reached it, so a figure who entered in silence and
  spoke two beats later had the boundary they entered at folded away:
  Myrrhine's entrance in *Lysistrata* (line 951 of the example). Boundaries
  nobody in the node set crosses now fold first, and a merge is accepted only
  if every boundary inside the merged segment passes against all of its
  speakers. *Lysistrata*'s stage-direction spine under the segment-level
  model goes from 50 to 51 segments; no other comedy changes.

- **No edge joins a collective to its own part.** A textual unit that holds a
  split or a merge holds both the chorus and its halves, and its clique
  joined them, asserting an encounter between the chorus and itself: 40
  edges across the large-seq and middle-seq views of *Acharnians*, *Peace*,
  *Lysistrata* and *Ecclesiazusae*, every one raising the chorus's degree and
  triangle count. `Character.part_of` (transitive, from `partOf`) now keeps
  each part apart from every whole it belongs to, in the static, per-segment
  and spell graphs alike, and in the cliques the per-play dashboard draws
  for a single segment and counts beside its heatmap. Under stage
  co-presence *Lysistrata*'s middle-seq graph goes from 276 to 274 edges,
  its large-seq graph from 302 to 300. A segment's `numEdges` in
  `dynamic_metrics.csv` is accordingly *n*(*n* − 1)/2 less any such pair. The stage-direction spine never held one.

- **Crossings survive the fold.** Rebuilding each segment of a folded spine
  left out its crossings, so both speaking models reported `num_crossings`
  = 0 in every segment, in the dashboard's segment table and in
  `segments.csv`. Nine crossings in five comedies are back.

- **The dynamic GEXF places a character in exactly their segments.** Spells
  were written as `start=k end=k+1`; GEXF 1.3 has no open bound and Gephi
  reads an interval as closed, so every spell also claimed the next segment,
  and at each integer time the outgoing and the incoming cast stood together.
  Time is now the segment number, one `<spell timestamp="k"/>` per segment
  under `timerepresentation="timestamp"`. The `start` / `end` each node and
  edge carried beside its spells, spanning first to last appearance, are
  dropped: current Gephi ignores them when spells are present, but a reader
  that honours them sees a character on stage through every gap.

- **A sign standing alone is not a word.** The crux (†) and a dash set off by
  spaces were each credited to a character as a word spoken: 87 tokens across
  the corpus, eight of them in *Lysistrata*, whose total goes from 8,120 to
  8,112 words. A word is now a whitespace-separated token holding a letter or
  a digit; a crux attached to a word leaves the word.

- **`<speaker>` and `<stage>` inside a speech are never counted.** Where a
  speech has no verse lines, its word count read the whole `<sp>`, label and
  stage directions included. Prose is now read like verse, block by block
  (`<p>`, `<ab>`), so two paragraphs written without whitespace between them
  are not run together into one word. No speech in the corpus is affected.

- **A speaker is in the segment they speak in, on every spine.** The textual
  spines have always put a speaker in their unit; the stage-direction spine
  read its cast off the moves alone, so a speaker whose entrance was missing
  or misspelt was an isolate there and connected on the other two. The
  parser now warns about every speech attributed to someone the moves have
  not put on stage. No speech in the corpus is affected.

- **Moves outside a `<stage>` still cut beats.** The schema encloses every
  move in one; a move outside it was keyed on no cluster, so after the first
  such move none opened a segment and the spine collapsed without a word.
  Consecutive bare moves with no speech between them are now read as one
  beat, and the parser warns.

- **`segments.csv` carries the exported model's cast.** Its `characters`
  column is the stage cast whatever `--export-model` says, so under the
  speaking models a row listed bystanders the exported graph never joined
  and disagreed with `size` in `dynamic_metrics.csv`. Three columns are
  added at the end: `speakers`, `model_cast_size` and `model_cast`, the last
  being the characters the exported model joins in that segment.

- **The corpus "speaker / mute ratio" reads "—" where there are no mutes.**
  Both speaking models drop the mutes from every count, and the ratio divided
  by `max(1, 0)`, printing the corpus speaker total as if it were a ratio.
  The drama-change-rate range in the same panel no longer drops a play whose
  rate is 0.

- **`analyze` exits with status 1 when it produced nothing**, such as when
  `--seg large-seq` is asked of a file without large-seq milestones. It
  exited 0 with a warning, and a script read the run as a success.

- **A TEI file cannot pull a local file into the dashboard.** The parser asks
  lxml to expand only entities declared in the file itself; a file that uses
  an external entity (`<!ENTITY x SYSTEM "file:///…">`) is refused rather than
  read. lxml has defaulted to this since 5.0, which is now the floor in
  `requirements.txt` (was 4.9).

### Changed

- **The Methods tab is a procedural reference.** Each entry states what is
  computed, from which elements of the TEI, with which function and
  parameters, and what the controls change — about half the former length,
  with every formula kept and the section numbering unchanged. Added: how a
  segment's stage cast is formed on each segmentation, the boundary rules of
  the stage-direction segmentation, the merge rules of the two speaking
  models, the corpus scatters, the beat chart's axes and the heatmap's edge
  counts. Corrected: weighted degree, not only eigenvector centrality, reads
  the edge weights; the relations line shows "(none declared)" rather than
  hiding; all three composition ratios, not only `col/spk`, ignore the
  aggregation toggle; the *Ecclesiazusae* counts in §7 are those of the
  stage-direction segmentation.

### Added

- **A second sample play, *Acharnians*, ships under `examples/`.**
  `examples/Ar-01-Ach.xml` is a byte-for-byte copy of the corpus file, as the
  *Lysistrata* sample is, so `python app.py corpus examples/` builds a corpus
  dashboard without the corpus checked out. `tests/refresh_example.py` copies
  it in the same run, and
  `test_baseline.py::test_second_sample_still_matches_the_corpus` fails when
  it has fallen behind the corpus. The baseline remains a fingerprint of
  *Lysistrata* alone.

- **Two per-character measures: the local clustering coefficient and the
  triangle count.** `metrics.json` and `characters.csv` carry them beside
  the centralities; the per-play dashboard shows them in the character
  table.

  The clustering coefficient is the local form of §1's average — the mean of
  exactly these values — and the triangle count is its numerator, before the
  division by the pairs a character's degree makes available. Read together
  they say whether a character's partners also speak to one another, which
  is what a brokerage reading rests on. A character with fewer than two
  neighbours has no neighbour pair: the value is 0, as §1's mean already
  counts it, where igraph returns NaN and a table built there shows a gap.

  **No per-character speech count**, DraCor's `numOfSpeechActs`
  notwithstanding. This annotation cuts a character's speech into several
  `<sp>` wherever a move falls inside it or the addressee changes: 82 of the
  corpus's 6474 speeches are continuations of the speaker before them, 69 of
  them with a stage direction in between, and the share runs from 0.2% in
  *Wealth* to 3.3% in *Acharnians*. Counting `<sp>` per character would
  report where the annotation cut rather than how often a character speaks,
  and a comparison across plays would follow the density of the annotation.
  Words survive the cut and are reported instead; `num_speeches` stays per
  segment, where it counts events on stage rather than a character's share
  of them. Methods §4 says so and a test holds the absence.

  Methods §2 documents both measures, the conventions included. On
  *Acharnians* under stage co-presence, Dikaiopolis has a clustering
  coefficient of 0.153 with 132 triangles.

- **Density × order can colour its dots by average degree.** A header
  checkbox beside *show pair-lines* fills each dot by the play's average
  degree — how many others a character shares the stage with, on average —
  from light to dark. The chart holds that number only implicitly, since
  ⟨k⟩ = d (n − 1), which is why it once took the iso-degree curve to make a
  play like Lysistrata stand out. The tone states it outright, with no
  reference shape and no model: it is computed from the chart's own two
  coordinates. Off by default.

  One scale serves every view: the tone runs linearly over a fixed frame, a
  quarter to twice the median average degree across all plays, spines,
  models and aggregation states, rounded to a power of two — 2 to 16 for the
  comedies. The frame is deliberately not fitted to the active view, which
  would stretch any spread, however small, across the whole ramp and make an
  ordinary play look exceptional. On the default view Lysistrata is the one
  dark purple dot among ten greens and teals; under the segment-level
  speaking model every dot comes out a light green, within 10 levels of
  lightness of one another, and Lysistrata the same tone as
  Thesmophoriazusae. An exported figure's caption says when the dots are
  coloured this way.

  The colours are those of the viridis scale, reversed so that darker means
  more, in place of the single blue first used, which left the plays near
  the median hard to tell apart. Measured in CIEDE2000, the standard
  perceptual colour difference, the ten comedies below Lysistrata on the
  default view now span 20.6 units instead of 9.5, and Lysistrata stands
  43.1 from the next play instead of 25.6. Of the multi-hue scales tried
  (YlGnBu, cividis, viridis) viridis changes at the most even rate, 8.1 to
  12.4 per tenth of the frame, so equal differences in average degree look
  alike wherever they fall. Its yellowest tenth is left out, as too pale
  against the page.

  The legend is a continuous bar over the frame, marked at 2, 8 and 16. It
  was first three dots, toned for 4, 8 and 16, which read as three classes
  of play where the tone runs continuously. A dot beyond either end of the
  frame takes that end's tone, and the end is then marked ≤ or ≥; no view of
  the comedies needs this, their values running from 2.7 to 15.5.

  Size was tried first, on a separate chart, and dropped: an honest area
  ratio of 1.74 between Lysistrata and the next play reads as "slightly
  bigger", and a second density × order panel beside the first was one chart
  too many. `drawScatter` takes the tone as an option; without it every
  scatter draws exactly as before. The Methods panel describes the option in
  §6.

- **Figure export.** Every panel in both dashboards now carries **SVG** and
  **PNG** buttons in its header. Until now the only way to put a chart into an
  article or a talk was to photograph the screen.

  The SVG keeps text as text, so it rescales without blurring and can be
  retouched in Inkscape or Illustrator; the PNG is a 3× bitmap for slides.
  Both are captioned with the configuration that produced them — *Acharnians ·
  stage-direction segmentation · speaking cast on play level · aggregated:
  choros · edges weighted by segments · SkeneGraph-Net x.y.z* — drawn as a
  footer and written into the file's `<title>` and `<desc>`. That is the point
  of the feature rather than a decoration: the same panel shows different
  numbers under different segmentations and models, so a figure that cannot
  say which one it came from can be neither checked by a reader nor re-made by
  its author. The caption also names the segment where the dynamic graph is
  showing one, and the beat multiples' x-axis mode.

  Three things the naive implementation would have got wrong, and which the
  exporter handles: the charts paint themselves through CSS custom properties
  (`fill="var(--chorus)"`), which resolve only inside the dashboard, so
  computed values are frozen onto the clone and `var()` attributes stripped —
  without this every figure opens black; a panel is not always one `<svg>`, so
  the corpus small multiples are composed into one figure at their measured
  offsets, with the per-chart titles that live in HTML redrawn as SVG text;
  and colour keys are rebuilt from the page's own swatches, since they too are
  HTML beside the drawing rather than part of it.

  New module `figure_export.py`, injected into both dashboards by the same
  comment-and-replace the Methods panel uses. `version.py` now holds the
  version string, which the exporter stamps into each figure; `app.py`
  re-exports it, so `from app import __version__` still works.

- **Table and comparison export.** Alongside the figure buttons, every table
  panel now offers **CSV** and **COPY**, and the metrics panel of each
  dashboard offers **CSV × ALL**.

  CSV and COPY take the whole table rather than the visible part, which
  matters because these tables live in 360-pixel scroll boxes: a screenshot of
  the speech-concentration panel omits its two loudest speakers without
  saying so. Cells are read as text, so the role chips arrive as words and the
  segment table's cast list is quoted rather than split across columns. The
  file carries a byte-order mark, so Greek names open correctly in Excel;
  COPY uses tabs, which paste into a spreadsheet or a Word table with no
  import dialogue.

  **CSV × ALL** writes every combination the dashboard can display as one
  table — segmentation × network model × aggregation state, one row each,
  with the full metric set and the plot-dynamics indices. The corpus version
  spans every play too: 135 rows for the eleven comedies. Comparing
  configurations previously meant switching a control, reading, switching back
  and remembering, which is how a table of figures for an article gets built;
  it is now one file. An empty `aggregated` column means the collectives were
  left split, in both dashboards' exports.

- **`--export-model {full,p-speaking,s-speaking}`** names which of the three
  network models is written to the exported files — `full` (every character on
  stage, edges from co-presence), `p-speaking` (characters who speak somewhere
  in the **p**lay, edges from co-presence) or `s-speaking` (characters speaking
  in the **s**egment at hand, edges from co-occurrence of speech). Default
  `full`, which is what the exports have always contained, so existing
  pipelines are unaffected.

  The mutes-out graphs were previously viewable but not exportable: the
  dashboard carried all three models, while `metrics.json`, the CSVs and the
  GEXF/GraphML files were fixed to the stage view. Feeding either speaking
  graph to Gephi now needs no hand-editing. `characters.csv` keeps
  listing the whole roster whichever model is chosen, with `in_network`
  marking who that model admits, and `metrics.json` records the choice in its
  `mute_mode` / `segment_cast` fields.

### Changed

- **The dashboards work offline.** Both pages loaded D3 from d3js.org and
  KaTeX from jsDelivr; opened without a network they showed their frame and
  no numbers or charts, since the first d3 call throws before anything is
  drawn. D3 7.9.0 and KaTeX 0.16.9 (script, auto-render, stylesheet and its
  20 woff2 fonts as data URIs) are now pinned in `vendor/` with their
  licences and inlined by `vendor_assets.py`. A page grows by about 0.9 MB;
  in exchange it can be copied to a USB stick or a projector laptop and
  opened anywhere. `tests/test_offline.py` keeps every script, stylesheet
  and font inside the file.

### Removed

- **Four corpus scatters that repeated what others show; one new chart
  takes the place of two of them.** An assessment of what each corpus
  chart's axes carry, over the eleven comedies, found four that add nothing
  of their own.

  *Density × average degree*: density is fixed by order and average degree,
  d = k / (n − 1), so the chart was the same eleven points as *density ×
  order* and *average degree × order*, seen from a third angle. The
  redundancy is mathematical and holds for any corpus.

  *Top-speaker share × Gini*: both axes summarise one word distribution, and
  across the comedies they move together — rank correlation +0.70, +0.78 with
  cast size held constant.

  *Gini × average degree* and *top-speaker share × average degree* set that
  same distribution against average degree twice. **Effective speakers ×
  average degree** replaces them: how many voices carry the play against how
  many others a character meets. Effective speakers moves with the other two
  (against the top-speaker share, −0.84 to −0.88 over the eighteen spine ×
  model × aggregation views), but it reads the whole distribution where the
  share reads one character, and a finely cut tail of the cast list does not
  move it as it moves the Gini. The Gini also tracks order, +0.73 to +0.84
  in every view against −0.33 to −0.07 for effective speakers, and order is
  already the x-axis of two charts. The Gini and the top-speaker share stay
  in the plays table. The speech axis moves with neither the spine nor the
  model, only with the aggregation toggle, which merges speakers; the
  Methods article (§6) says so and keeps the note on chorus aggregation.

  The corpus dashboard now draws four scatters, in one row on a wide screen.
  Checked in a rebuilt dashboard: eleven labelled dots and no console
  errors; the model radio moves only the average-degree axis, and the
  aggregation toggle moves the effective-speakers axis for *Acharnians*
  (3.60 → 3.51), *Peace* (3.72 → 3.67) and *Lysistrata* (6.97 → 5.08). A
  test holds that none of the removed charts returns. §11's list of the
  panels the aggregation toggle reaches, and the layout sketch in
  `corpus_dashboard.py`, still named the density × average degree chart;
  both now name the charts that remain.

- **The anchor / display-only state of the play chips.** Each chip cycled
  three states — excluded, *anchor* (shown, and counted in the reference),
  *display-only* (shown, not counted) — so that a play could stand on a chart
  without setting the reference. It served the iso-degree curve, whose median
  it let one tune, and before that the wish to show variants of one play
  without counting them twice.

  With the curve gone, it no longer earned its place. Its one live effect was
  on the median crosshairs, and a median already ignores an outlier: taking
  any single play out of the reference moved a crosshair by at most 4.8% of an
  axis, typically about 2%, and the order median not at all. Taking out
  Lysistrata, the case it was built for, was not the largest shift on any
  axis; mid-ranked plays moved it more. A duplicate variant moves a median by
  the same half-gap. Its other documented effect was never there: the Methods
  panel and three code comments said the KPI ranges followed the anchor set,
  and the KPI panel read the displayed plays, with the `anchorPlays()` helper
  written for the purpose defined and never called.

  A chip now includes or excludes, and its colour dot still sets the play's
  colour. The crosshairs and the KPI ranges are computed over exactly the
  plays on screen, so a reference is never drawn from a play the reader
  cannot see. The ⚓ glyph, the italic and 0.55-opacity styling, the anchors
  chip in the filter strip, the "anchor + display-only" counter, the dead
  helper and the Methods article on tri-state chips are gone; the selector
  and crosshair articles now describe the single set. Checked in the rebuilt
  dashboard: one click excludes a play and moves the crosshair, a second
  restores it, the colour dot leaves inclusion alone, and the quick actions
  behave. A test holds that no second set returns.

- **The `density` column of `dynamic_metrics.csv`.** A segment's graph is its
  cast joined into a clique, so its density is 1 wherever two or more stand
  together and 0 otherwise: across the shipped exports, 783 rows at 1.0 and
  142 at 0.0, and nothing else in 925. A column of that shape reads as a
  finding — *fully connected* — when it restates the construction, and the
  dashboards never plotted it. `numEdges` stays: the same fact as a count,
  *n*(*n* − 1)/2, which a reader rebuilding a segment's graph needs and
  nobody mistakes for a result. Verified as exactly the clique count in all
  925 rows. `README.md` says why the density is absent, and a pipeline test
  holds both halves.

  Breaking for anything reading that column; the value is recoverable from
  `size`.

- **`--no-mutes`**, replaced by `--export-model`. The flag had been inert: it
  was accepted by both subcommands and passed to `analyze_one` as
  `include_mutes`, but the parameter was never read — every mute decision came
  from the hard-coded three-mode table, so the exports were the stage view
  whether or not the flag was given. It was a leftover from the binary
  mutes-in/out model that the three orthogonal modes replaced, and it could
  not be repaired under its own name: "mutes out" is now *two* models
  (`p-speaking`, `s-speaking`), which a boolean cannot distinguish.

### Added

- **Effective speakers**, a second concentration measure beside the Gini:
  1 / Σ sᵢ², the inverse Herfindahl index — the effective number of parties of
  Laakso & Taagepera (1979), the inverse Simpson index in ecology. It reads in
  speakers rather than on a 0–1 scale: *n* when every speaker says the same
  amount, 1 when one says everything, and on the corpus 3.60 for *Acharnians*,
  4.98 for *Birds*, 7.48 for *Ecclesiazusae* — how many voices the play
  actually rests on.

  It is here because of two properties of the Gini that came out of reviewing
  §4, both now documented there. The Gini's maximum is (n−1)/n, so plays are
  measured against ceilings that move with cast size — 0.75 for four speakers,
  0.96 for twenty-four. And because it weights by rank, it responds to how
  finely the cast list is cut: adding one character with a single word raises
  it by up to 0.098 (*Knights* 0.310 → 0.408), and the bias-corrected form
  n/(n−1) responds slightly *more*, so the correction fixes the ceiling and not
  this. Effective speakers weights by share instead, and moves by 0.03% on the
  same addition; the top-speaker share, already in the app, is likewise robust.

  Two things it is not. It is bounded by *n*, as the Gini is bounded by
  (n−1)/n — what differs is that a count means the same in a small cast as in
  a large one, where a position on a 0–1 scale does not. And its robustness is
  to the tail, not to the cast list at large: merging two principals moves it
  a long way, the partOf toggle taking *Lysistrata* from 6.97 to 5.08 when the
  semichoruses become one chorus. That is the behaviour to want — two large
  voices becoming one is a real change in how many voices carry the play.

  Neither measure replaces the other, and the pair is more informative than
  either: the Gini hears the tail, effective speakers hears the principals, and
  a gap between them is a long tail of small parts. The case for adding it now
  is the planned expansion to tragedy — small casts sit under low Gini
  ceilings, so a comedy-tragedy comparison would carry a systematic bias that
  looks exactly like a finding.

  New in the play headline, the corpus plays table (**eff spk**), both metrics
  CSVs, `speech_distribution.effective_speakers` in `metrics.json`, and the
  corpus chart *effective speakers × average degree* (see Removed).

### Added

- **Standing checks for the two things unit tests structurally cannot see.**
  An audit of the code — as against the Methods tab — ran three sweeps whose
  findings are now tests rather than one afternoon's scripts.

  `test_invariants.py` builds every configuration of a play (three spines ×
  three network models × with and without aggregation, eighteen in all) and
  asserts nine properties of each: speeches partitioned exactly once, segment
  word counts equal to their speeches' attributed sums, segment totals
  reconciling with the play total, casts naming only declared characters,
  graph nodes equal to the model's kept cast, edge bookkeeping self-consistent
  (`segments_shared`, `segment_ids` and `words_shared` agreeing), the metrics
  re-derivable from the graph, centralities in range, and an edgeless graph
  reporting no distances. It runs on the demo play always and over the whole
  corpus when one is present.

  `test_artefacts.py` runs the pipeline and checks what it wrote: every file
  present, `characters.csv` agreeing with the node list, no column declared
  and left empty, segment and edge counts matching, the hand-rolled GEXF and
  the GraphML parsing with the right node and edge counts, and the dynamic
  GEXF carrying spells. It also re-derives from the page payload the two
  numbers that exist only in the browser — the heatmap's threshold-passage
  count and the beat chart's word-position axis — and tests them as
  properties, since nothing else executes that code.

  Also new: `test_interactive.py` for the guided prompt, `test_app_paths.py`
  for corpus path resolution and the default title, and
  `test_degenerate_plays.py`, which runs the pipeline on plays with one
  character, with nobody who speaks, with every speech textless, and on an
  empty stage. The suite goes from 220 to 277; `-m "not slow"` runs 241 of
  them in about six seconds.

### Fixed

- **An exported heatmap lost the key that says what its cells mean.** The
  exporter rebuilt a figure's key from `.legend > span` and a background
  colour. The chorus chart keeps its key in `.legend-inline`, and two of its
  three swatches are a hatch and a ramp, which are no colour at all, so
  none of the three entries reached the figure. The per-play heatmap had no
  key in the page: it said what its cells mean in the heading's hint, which
  the exporter strips from the title. Exported, both charts therefore left
  a reader to guess which cells are a silent presence, which a performance
  whose text is not transmitted, and which the words spoken.
  
  Swatches now declare how they are painted (`data-swatch="solid|hatch|
  ramp"`, with `data-colors`), the exporter reads both kinds of key
  container, and it gives the figure a pattern or a gradient of its own,
  drawn as the charts draw theirs. The per-play heatmap gains the key as a
  legend under the chart — the same three entries the corpus chorus chart
  carries — so the page and the figure say the same thing; its hint keeps
  what is about the page rather than the chart ("click a cell to jump to
  its segment").

  Checked on the exported SVGs: the chorus figure and the per-play heatmap
  each carry the three entries with a grey square, a hatched square and a
  50 px ramp, with the pattern and gradient defined in the file; the
  network's four-colour key is unchanged.

- **An exported figure's caption ran off the edge of the image.** The
  caption was drawn from the left margin as a single line, while the
  figure's width was set by the art and the heading alone. Beside a
  dashboard panel some 360 px wide, the ordinary corpus caption — plays,
  segmentation, model, aggregation state, the tone, a highlighted play, the
  version — measures about 700 px, so half of it stood outside the SVG, and
  outside the PNG for good. The caption is the point of the export: a
  figure that cannot say which configuration produced it can be neither
  checked by a reader nor re-made by its author.

  The exporter now measures text with the browser rather than counting
  characters, and wraps the caption to the figure's width, adding a line's
  height for each further line. The heading is measured the same way, in
  place of the 7.5 px a character it was allowed. Checked on a 379 px
  corpus figure (three caption lines, nothing past the canvas, height 418 →
  444, and a PNG of 1137 × 1332) and on a 497 px per-play figure (two
  lines); a full-screen figure keeps its single line as before.

  `wrapText` takes its measurer as an argument, so the suite runs it in
  node against a fixed one: a caption that fits stays on one line, a long
  one wraps without losing a word, and a word too wide for the line keeps a
  line of its own. The node helpers the label-placement tests use now live
  in `tests/jsrun.py`, and pass UTF-8 in both directions — the system code
  page mangled the caption's middots on the way back.

- **The segment-level speaking fold could erase a character's return.**
  Folding the stage-direction spine for that model asks whether anyone who
  crosses a boundary speaks on either side of it. It read *who crosses*
  against the union of everyone the accumulated run had held, rather than
  against the stage as it stood at the boundary, so a character who had left
  earlier in the run never appeared to enter when they came back. The
  boundary folded away, the return went with it, and the merged segment
  credited that character with speaking beside characters they never shared
  a segment with. Three beats are enough: A speaks with A, B and C present;
  B leaves in silence and C speaks; B returns and speaks. The fold gave one
  segment and the triangle A–B–C where the rule it documents requires two
  segments and A–C alone.

  Across the eleven comedies the only play affected is *Peace*, whose
  stage-direction spine under segment-level speaking now holds 53 segments
  instead of 52, and 51 instead of 50 with the chorus halves aggregated. Its
  graph is untouched — order 19, 30 edges, density 0.175, average degree
  3.16 — but the figures read off the spine move: the DCR from 0.6088 to
  0.6100, σ from 0.2316 to 0.2195 and the all-in index from 0.9608 to
  0.9615 (0.6028 → 0.6042, 0.2346 → 0.2221, 0.9592 → 0.9600 aggregated),
  and the chorus beat row gains a cell. Nothing else in the corpus payload
  differs. A regression covers the silent exit and the speaking return, and
  fails against the old fold.

- **The heatmap drew its cells at a negative width where its container had
  none.** The character × segment heatmap sizes its cells from the element
  it draws into. Where a page is rendered without layout — a hidden window,
  a pane that is not on screen — the plot area came out negative, every cell
  was given a negative width, and the browser refused each one: for
  *Acharnians* some 4,000 console errors, and an empty heatmap. It now draws
  nothing until the element has room, and watches it, so the chart appears
  by itself the moment it does.

  Checked in a hidden browser pane: no errors, no cells, the observer
  waiting; giving the pane a width drew all 3,956 cells at 13.2 px each,
  with no negative width anywhere. On an ordinary load the heatmap draws at
  once, as before. The console noise mattered beyond tidiness: it buried the
  real errors when a page was being checked.

- **The README's `metrics.json` example held numbers from an older state of
  the corpus.** It showed *Acharnians* with 31 nodes and 92 edges, a
  diameter of 3 and Dikaiopolis at degree 24, which matches no model the app
  now produces: the stage view gives 43 and 174, a diameter of 2 and degree
  42. The example is regenerated from a real run and carries the new
  per-character fields.

- **Scatter labels lay on one another and beside the wrong dot.** Every
  label was set right of its dot, whatever stood there. Over the four corpus
  scatters and the eighteen spine × model × aggregation views, at 1600 px,
  89 pairs of labels overlapped and 110 labels stood on or nearer another
  play's dot than their own. *Clouds* and *Wasps*, 2.5 px apart on
  *effective speakers × average degree*, printed their labels one over the
  other.

  A label now stays right of its dot unless it would cover another label,
  come nearer another play's dot than its own, or run off the plot. It then
  takes the first clear spot of seven others round the same dot: above
  right, below right, left, above left, below left, above, below. A
  highlight's ring counts as part of the play's mark, highlighted labels are
  placed first, and the tone legend on *density × order* counts as a label.
  Where no spot is clear, a label takes one that covers no text if any
  does, since text on text cannot be read, and then the one that comes least
  near other dots. No label leaves its own dot, so none needs a leader line.
  Methods §6 states the rule.

  Checked in a rebuilt dashboard over all eighteen views, at 1600, 1200 and
  760 px and in full screen: no label overlaps another, stands on or nearer
  another play's dot, or runs off a chart. At 1600 px, 134 of 792 labels
  move; in full screen, 15. With three plays highlighted and the tone on, no
  labels overlap. Six stand nearer another mark, in each case because their
  own dot lies inside another play's highlight ring, where no spot round the
  dot can be nearer to it. The placement is plain geometry, so eight tests
  run it in node where node is installed (they skip otherwise). Removing
  any one of its rules makes at least one test fail. They hand node a
  script file rather than `node -e`: where `node` on the PATH is a .CMD
  shim, a multi-line `-e` script is cut at the first newline and the shim
  exits 0 having printed nothing, which failed the tests on a machine whose
  code was sound. A run that prints nothing now says so instead of failing
  on the empty output.

- **Every exported figure was titled with its fullscreen button.** Both
  dashboards keep the fullscreen toggle inside the panel heading, and the
  exporter named a figure by the heading's text less its hint and export
  buttons, so the toggle's label ran into the figure's `<title>` and file
  name: *Density × order ⛶ fullscreen*, `density-order-fullscreen.svg`. Every
  control in the heading is now left out. Checked on an exported corpus
  scatter and a per-play heatmap.

- **An exported figure drew its panel's heading, hint and controls
  included.** The exporter carries into a figure the HTML text standing
  beside a chart, which is meant for the titles of the small multiples.
  Where a panel's chart sits in the panel itself — the corpus scatters and
  cast-composition bars, the per-play order and words charts — the panel
  heading counted as such text and was drawn whole, the words of separate
  elements run together: *Density × order red lines = pairs with Δn ≤ 5 …
  colour by average degree ✕ exit fullscreenSVGPNG*. In fullscreen, where
  the segmentation and play controls move into the panel, they were drawn
  too. Only the small multiples' titles now travel with their charts, and
  every exported figure is headed by its panel's title alone, set above the
  drawing: *Density × order*. Figures that carried no heading before, the
  small multiples among them, now carry one too. Checked on corpus and
  per-play exports, in and out of fullscreen.

- **§1's ⟨d⟩ = 2 − d identity was stated across two different vertex sets.**
  Diameter and average path length are computed on the largest component,
  following DraCor; the density in the panel is the whole graph's. Where those
  differ the identity is false, and the corpus has a case: **Birds ·
  stage directions · speaking cast on segment level**, 2 components, D = 2,
  ⟨d⟩ = 1.8735177866 against 2 − d = 1.8840579710.

  The note now states the identity against *d′*, the density of the largest
  component, and says that on a connected graph *d′* = *d* so it can be read
  against the density shown, while on a disconnected one the panel's density
  does not enter it. Over the 150 corpus blocks with 0 < D ≤ 2 the identity
  holds against whole-graph density in 148 and against component density in
  all 150.

- **§5's all-in formula mixed two indexing conventions.** It enumerated casts
  from *S₁* to *S_N*, defined *j* on that sequence, and then divided *j+1* by
  *N* — so arrival in the last segment reads (N+1)/N, above the stated range
  of (0, 1]. The implementation is right: it enumerates the scanned sequence
  from zero and divides by the scanned count. Two further slips came with it.
  *N* was the panel-wide symbol for the segmentation's whole output, where
  this quotient needs the scanned count, after the leading marker is dropped;
  and the note below said `all_in_segment` stores *j*, which it does not — it
  stores the 0-based index.

  The article now defines *N′* as the scanned count, keeps the panel's 1-based
  indexing, gives the index as *j/N′*, and says `metrics.json` stores *j − 1*.
  Checked against all 99 blocks of the corpus: *j/N′* reproduces the stored
  index exactly in every one, always lands in (0, 1], and *S_j* is the segment
  whose label the dashboard prints.

- **§2's eigenvector formula dropped the weights it says it reads.** The
  article gave the matrix equation over the weighted adjacency matrix and then
  expanded it as *x_v ∝ Σ_{u∈N(v)} x_u*, without *w(u,v)* — the unweighted
  reading, contradicting both the equation beside it and the prose two lines
  below, which calls this "the one measure here that reads the edge weights".
  `metrics.py` passes `weight="weight"` to both solvers, so the printed
  expansion described a calculation the app never performs.

  Not a cosmetic omission: on a triangle weighted 10, 1, 1 the app returns
  0.700 / 0.700 / 0.137 where the unweighted reading returns 0.577 for every
  node. The expansion now reads *λ x_v = Σ_{u∈N(v)} w(u,v) x_u*, which is the
  row-wise form of the matrix equation and matches NetworkX's weight
  semantics; the per-component normalisation is explained in its own note, as
  before.

  The other three centralities were checked against their calls and are
  accurate: weighted degree states *Σ w(u,v)*, and betweenness and closeness
  both say the edge weights play no part, matching `weight=None` in each.

- **§9 claimed the play-level fold leaves the graph identical.** It does not.
  The fold preserves the vertex set and the unweighted edge set, and that is
  all: the default weight counts the segments a pair shares, so merging two
  segments in which both stood drops that count by one. **Clouds · stage
  directions** has 48 edges before the fold and 48 after, while
  *choros–strepsiades* falls from 27 shared segments to 25.

  Across the eleven comedies the node set and the unweighted edge set are
  identical in every play; shared-segment weights move in every play, on 3 to
  52 edges; weighted degree moves for 3 to 17 characters; eigenvector
  centrality — which normalises over the whole weight vector — moves for every
  node of every play. Under `--weight words` nothing moves at all, in any
  play: a merged segment's word total is the sum of its parts, so that
  weighting is invariant under the fold by construction.

  The article now states the preservation as vertex set and unweighted edge
  set, names shared-segment weights and the two metrics built on them, and
  gives the word weighting as the exception. The audit that had accepted the
  old claim compared order, edges, density, average degree, clustering,
  diameter, path length and components — every unweighted quantity, and no
  weighted one.

- **§10 said aggregating a chorus raises the density.** It can lower it. The
  merge moves both terms of *d* = 2*m* / (*n*(*n*−1)): parallel edges from the
  group's members to the same outsider collapse into one, and edges inside the
  group disappear, so *m* can fall faster than *n*. **Lysistrata · middle
  sequences · speaking cast on play level** goes from 0.438735 to 0.428571 when
  the chorus is aggregated, *n* 23 → 21 against *m* 111 → 90; the
  large-sequence and stage-direction spines of that play fall too, as does the
  stage model in two further blocks.

  Of the 36 aggregated/unaggregated pairs in the shipped dashboards the density
  rises in 24, falls in 6 and is unchanged in 6. The parenthetical's "one fewer
  node" was wrong as well: the merge removes two nodes in 27 blocks, three in
  3, and none in 6 — where the group's members are outside the active model's
  node set the toggle moves nothing at all. The article now says aggregation
  changes order, edge count and density alike, with the direction depending on
  how the group was connected.

- **§1 described disconnection as individual isolation.** It said a
  stage-presence graph "splits only where a character shares the stage with
  nobody". A component boundary is the absence of any chain of shared segments
  between two groups; a lone character is one case of that, not the only one.
  Two segments with casts {A, B} and {C, D} and no cast in common give two
  connected pairs and no isolate at all.

  The corpus holds that shape: under **speaking cast on segment level**,
  **Ecclesiazusae** splits into components of 11 and 5 on the large sequences,
  and 10, 5 and 1 on the middle sequences and the stage-direction spine. A
  five-character component is not an isolate, and the panel offered no reading
  for it.

  The note now defines the component by the chain and gives both the solitary
  character and the non-overlapping group as cases of its absence. Of the 198
  corpus blocks 8 split, every one of them under the segment-level model: six
  are the Ecclesiazusae graphs above (three spines, aggregated or not, the
  merge being a no-op there), and two are **Birds · stage directions**, which
  does shed a single isolate. The stage-presence graphs are connected
  throughout, which is why the claim had gone unchallenged.

- **§2's betweenness sum did not say which pairs it ranges over.** The
  subscript was the traditional shorthand *s ≠ v ≠ t*, which states neither
  that pairs are unordered nor that *s* ≠ *t*. Read as an ordered sum it
  doubles every value: a three-node path returns 2 at its middle vertex where
  NetworkX returns 1, and the whole range [0, 1] the article claims collapses.

  The sum now runs over {*s*, *t*} ⊆ *V* \ {*v*} with *s* ≠ *t*, and the prose
  says each unordered pair is counted once, there being (|*V*|−1)(|*V*|−2)/2 of
  them to the prefactor's reciprocal. Two conventions the article had left
  unstated are now given: a pair in two different components has σ_st = 0 and
  contributes a term of 0 while the divisor still counts it, and below three
  vertices there is no pair at all and every *B(v)* is 0. Checked against
  NetworkX: the middle of a three-node path is 1.0 normalised and unnormalised
  alike, a two-node and a one-node graph give 0.0, and two disjoint three-node
  paths give each middle vertex exactly the prefactor 2/((6−1)(6−2)) = 0.1.

- **The anchor glyph in §6 shipped as red error text.** The panel wrote it as
  `$\unicode{x2693}$`, and KaTeX has no `\unicode` macro — with the dashboards'
  `throwOnError: false` the reader got a red `\unicode` and an italic *x2693*
  where the chart draws ⚓. It is now the HTML entity, which is what the chip
  itself uses.

  Found by rendering all 237 maths spans of the panel through the same KaTeX
  0.16.9 build the dashboards load, rather than by reading them. That was the
  only failure; the other 236 parse.

- **§5 promised an ordering of the all-in index across the three models.** It
  called the segment-level speaking model "the latest of the three" and the
  play-level one "generally earlier" than stage co-presence. Neither holds. The
  index is *j*/*N′*, and both terms are model-specific: the models count
  different casts, and on the stage-direction spine each speaking model folds
  the spine to its own length (§9), so the quotients are not commensurable.

  **Clouds · stage directions** goes the other way throughout — stage
  co-presence 0.957447, speaking cast on play level 0.955556, speaking cast on
  segment level 0.948718. Across the 33 play × spine blocks of the corpus the
  segment-level model is *not* the latest in 18, a majority. The play-level
  claim fails in one block, and instructively: **Lysistrata · stage
  directions** goes all-in at scanned segment 44 of 52 under the play-level
  model against 52 of 63 under stage co-presence — sooner in segments, later as
  a fraction, 0.862745 against 0.838710.

  What survives is the semantic distinction, which the note now gives alone:
  the three models wait for every body to appear, for the speaking company to
  appear, and for that company to have been heard. Per character a first
  utterance cannot precede a first presence, the speaker being on stage to
  speak; that constrains one character's two events, not three normalised
  aggregates over different casts and different spines.

- **§1's ⟨d⟩ = 2 − d′ identity still lacked its lower bound.** Correcting the
  vertex set left the range open at the bottom: "wherever *D* ≤ 2" takes in
  *D* = 0, which is a largest component of one vertex. There the app returns
  ⟨d⟩ = 0 — `compute_metrics` computes distances only for a component of two
  or more — while 2 − *d*′ gives 2, NetworkX's density of a single vertex
  being 0. The identity now carries |*V*′| ≥ 2, and the app's convention for a
  graph with no edge at all, *D* = ⟨d⟩ = 0, is stated as standing outside it.

  No shipped dashboard is affected: all 198 corpus blocks have at least one
  edge. It is reachable from outside the corpus, though — a one-character
  fragment, or any block where no segment holds two co-active characters — and
  `test_degenerate_plays.py` builds such plays.

  The identity is now checked rather than asserted in prose. A new invariant
  in `test_invariants.py` verifies it on every configuration meeting the two
  stated conditions: 150 of the 198 corpus blocks, the other 48 skipped as
  out of range. It discriminates — read against whole-graph density instead of
  the component's it fails on 2 of the 150.

- **Two plays could write into one output directory, and the second won.**
  `analyze_one` named the play directory after the sanitised English title and
  opened it with `exist_ok=True`. Any two titles that sanitise alike therefore
  shared a directory: `Electra?` and `Electra!` both give `Electra`, as do the
  same play edited by two hands, or one title used by two authors. The second
  run overwrote the first's dashboard, CSVs, GEXF and GraphML, while the
  corpus dashboard carried both summaries with both links pointing at the
  survivor — two rows of numbers describing one play. This is lost output, not
  a mislabelled one: reproduced with two two-character plays, after which the
  single `Electra/sd/characters.csv` listed only the second play's cast.

  `exporter.allocate_play_dir` now hands out the directories. A name held by
  another source is refused and the source's own file name disambiguates it
  (`Electra-soph-el`), with a warning naming both. Re-running the same source
  is not a collision — it reuses its directory, which is what a re-run is for.
  Sources are told apart by path within a run and by file name across runs,
  through a new `source.json` written into each play directory; so a corpus
  moved to another folder re-runs into its own directories rather than beside
  them. Where neither title nor file name separates two sources, the second
  takes the fallback name; where that too is held, the run raises rather than
  overwrite, naming what stands in the way. A directory written before this
  marker existed carries none, cannot be told from a re-run, and is reused —
  so no existing output tree is renamed by the fix. Verified on the corpus:
  the eleven comedies land in the eleven directories they already occupy.

  The corpus dashboard keyed its chips, anchors, colours and dot state off
  `title_en`, so two plays of one title were one chip controlling both dots.
  `_playKey` now uses the drill-down href, which the allocator guarantees
  distinct — the same identity for the controls as for the links.

  `tests/test_output_collisions.py` covers the allocator and the pipeline: two
  colliding titles keep two directories and two casts, a re-run and a
  relocation keep one, the dead end raises.

- **The word counter invented words at every element boundary.** `_spoken_text`
  walked the verse and joined the fragments with a space. An element boundary
  is not a word boundary: a `<q>` or `<add>` closing before the comma leaves
  that comma in the tail, where the inserted space made it a word of its own,
  and a `<supplied>` splitting a word in two had it counted twice. Acharnians
  35 came out as `πρίω ,` for the source's `πρίω,`.

  **30 phantom tokens across nine plays** — Frogs 8, Wasps 6, Peace 5, Clouds
  4, Birds 2, Lysistrata 2, Acharnians 1, Knights 1, Ecclesiazusae 1;
  Thesmophoriazusae and Wealth were clean. The fragments are now concatenated
  as the source has them. Every word figure in the app is a sum of attributed
  speech words, so all of them move a little: play totals, per-character
  totals, the speech Gini, top-speaker share, effective speakers, the temporal
  Gini, and the edge weights of a `--weight words` build. No structural metric
  moves — order, edges and density are untouched.

  The Methods panel was already right: it defines a word as "a whitespace-
  separated token" of the verse. It was the code that did not match, inserting
  whitespace the file did not have.

  `tests/baseline_demo.json` regenerated deliberately. Eleven keys changed,
  every one of them word-derived — Lysistrata's total falls from 8122 to 8120,
  its Gini from 0.649679 to 0.649604, its effective speakers rises from 6.9701
  to 6.9739 — and nothing structural moved, which is the signature to expect.
  Three parser tests cover the rule and were checked against the old
  behaviour: all three fail under it.

  One consequence is a finding about the corpus rather than the app. **Peace
  346** is encoded `...τὴν ἡμέραν<del>ποτέ</del>.` with no space before the
  deletion, so a faithful counter reads `ἡμέρανποτέ.` — one word where the
  edition prints two. The old counter hid the missing space while inventing a
  token from the full stop, reporting 10 words for a verse of 9; it now
  reports 8, and will report 9 once the space is added. It is the only such
  verse in the eleven comedies, and it wants an editorial fix in the TEI
  rather than a repair in the parser, whose business is to report what the
  file says.

- **An aggregated group left the stage with its first departing part.**
  `aggregate_play` rewrote every member id to the group id, moves included.
  That is right for what a move adds — the stage state is a set, so putting a
  group there twice is putting it there once — and wrong for what it removes.
  Two parts enter, one leaves, the other stays: the rewritten exit took the
  whole group off stage, and every later segment lost the group, its edges,
  its heatmap row and its share of the temporal measures. With A and B parts
  of G, both entering, B leaving, then C arriving to speak beside A, the casts
  came out `{G}`, `{}`, `{C}` where they should read `{G}`, `{G}`, `{G, C}`,
  the G–C edge missing altogether.

  Removals are now read off the members' own occupancy: `_rewrite_moves`
  replays the raw moves and takes out exactly those group ids left with no
  present member, so a group leaves when its last part does. Additions keep
  the plain projection, which is idempotent — and `onStage` in particular
  keeps a non-empty `@who`, an empty one being the marker for an empty stage.
  A member exit that moves nobody still opens its segment: the spine is cut by
  the annotation, not by the cast that results from it, so segment counts under
  aggregation are unchanged.

  No shipped number moves. The eleven comedies have no staggered departure:
  393 segment casts, over all three spines and every subset of each play's
  partOf groups, agree exactly with the projection of their raw casts. This
  was a supported encoding that no file in the corpus happened to use.

  One documented behaviour changed with it. A `split` of a group into parts
  that aggregation has already merged used to rewrite to `@who={g}`,
  `@corresp={g}` — a no-op only because the addition followed the removal.
  It now reads `@who={}`, `@corresp={g}`: nobody leaves, and the group stays.

  Five tests in `tests/test_aggregation.py` cover the staggered case and its
  mirror, the mixed exit of a part beside an outsider, the preserved boundary,
  and the general property that aggregated presence is the projection of raw
  presence. Four of them fail under the old rewrite.

- **A closing script tag in the TEI broke the dashboard in half.** The payload
  was written straight into `<script>const DATA = …</script>`. JSON quoting
  does not defend that boundary: the HTML parser scans for the literal
  characters `</script` before any JavaScript runs. The TEI tab carries the
  whole source file, comments included, and a comment may legally hold one —
  so a play that parses without a murmur produced a dashboard whose main
  script ended inside the comment. Reproduced: the script closed after 9,109
  characters with `const DATA` inside it and `const STATE` and every render
  function outside, as page text. The page loaded and did nothing.

  Both writers now serialise through `_json_for_script`, which escapes `<`,
  `>` and `&` as `\uXXXX`, along with U+2028 and U+2029 — legal in a JSON
  string, and line terminators in JavaScript before ES2019. The payload is
  unchanged as a value: the TEI tab still shows the file as it was written,
  closing tag and all.

  The subtitles carried the same exposure in HTML text: the play dashboard
  prints the author and the Greek title from the TEI header, the corpus one
  the author list, and none of the three was escaped, though the page title
  beside them was. All are now escaped, the separators staying markup. A
  stray `&middot;` in the play subtitle's literal went with them; it had been
  printing a doubled separator before "segmentations:".

  `corpus_dashboard` had its own copy of `_html_escape`; it now imports both
  helpers, since an escape applied in one writer and not the other is no
  escape. `tests/test_html_embedding.py` parses the generated HTML with
  `html.parser` and checks, for both dashboards, that the script element still
  contains the code after the data, that the payload round-trips, and that
  hostile metadata reaches the subtitle escaped. Four of the six fail without
  the fix.

  The reproduction used an inert comment; no code was executed.

- **A quotation mark in a name produced an unparseable `dynamic.gexf`.** The
  file is written by hand — NetworkX emits no `<spells>`, which is the whole
  point of it — and every value lands inside a double-quoted attribute, run
  through `saxutils.escape`. That function is for character data and leaves
  the quotation mark alone, so a character named `A "quoted" role` closed the
  attribute early. The export reported success and wrote a file no XML parser
  would read: `not well-formed (invalid token)` at the node's `label`, with
  the same text written a second time as an `attvalue`.

  One helper, `_attr`, now escapes every attribute the writer emits — ids,
  labels, values and both ends of each edge — because an escape that has to be
  remembered at each call site is one that will be forgotten at some of them.
  The apostrophe is deliberately left alone: it is legal inside a double-quoted
  attribute, and the corpus is full of it — `Men's Chorus`, `Μαθητής α'`, ten
  fields in all, every one of which would otherwise have churned to `&apos;`.

  Nothing shipped changes: re-exporting the eleven comedies gives 33
  `dynamic.gexf` files byte-identical to the ones in the output tree, no name
  in the corpus carrying a quotation mark. `tests/test_gexf_escaping.py`
  parses the written file and reads the label back, over five hostile names
  plus a quoted id; 5 of its 12 cases fail with `saxutils`' default escape.

- **Verse quoted inside a note was counted as speech.** The editorial
  exclusion ran one line at a time: the speech parser took every descendant
  `<l>` with `findall(".//tei:l")` and handed each to `_spoken_text`, which
  strips a `<note>` *inside* a line but cannot see a note *above* one. A
  speech holding `<l>one two</l>` beside
  `<note><quote><l>editorial quoted verse</l></quote></note>` was credited
  with five words where the stated rule gives two — an editor quoting verse
  counted as the character speaking it.

  Selection is now a single context-aware walk, `_spoken_lines`, which does
  not enter an excluded subtree at all; `_NOT_SPOKEN` stays the one list of
  what counts as editorial. A speech whose only verse sits inside a note now
  has no verse left and falls to the no-`<l>` branch, which counts the `<sp>`
  minus the note — the right answer by the same rule.

  Nothing shipped changes: across the corpus's 6,474 speeches, not one holds
  verse inside a note or a gap. Three parser tests cover the shape, all three
  failing under the old selection.

- **A checkbox with no block behind it changed the network model.** The
  toolbar offers one box per declared `partOf` parent, but `aggregate_play`
  resolved every member to its *topmost* ancestor and only then filtered by
  the selected groups. With A partOf B partOf C, selecting B matched nothing,
  the writer generated no variant for it, and `currentSegData()` fell through
  to the unaggregated stage-presence block — while the radio, the chips and
  the figure captions went on reading "speaking cast". On a play with a
  speaking A and a mute X, ticking B showed X, a character the speaking model
  excludes by definition.

  Two changes, because the mismatch had two halves. `build_partof_map` now
  takes the selected groups and resolves each member to its highest
  *selected* ancestor, so selecting B means what it says: A folds into B and
  C is left standing. And both the writer's variant enumeration and the
  dashboard's checkboxes are drawn from one list, `aggregatable_groups`,
  carried in the payload — the boxes can no longer name a combination that
  was never built.

  The fallback is fixed too, since a guard that lies is worse than none.
  Where a combination really is absent it now drops the aggregation first and
  the model only as a last resort, clearing the checkboxes and the radio as
  it goes, so what the controls say is what is on screen.

  Nothing shipped changes: no play in the corpus nests its groups, and the
  132 exported CSVs come back byte-identical. `tests/test_variant_coverage.py`
  runs a nested-chain play through the app and checks that every offered group
  has a block in every model, that the intermediate group collapses only what
  it holds, that no speaking-model block holds the mute, and that the
  checkbox list comes from the writer rather than from the relations. Three
  tests fail under the old resolution — two there and one in
  `tests/test_aggregation.py`. The mute check is not among them: under the old
  code the offending block was not wrong but absent, the substitution
  happening in the view. It stands as a guard on the payload.

- **NumPy and SciPy were undeclared, and the app is not indifferent to them.**
  NetworkX names them only under its `default` extra, so `pip install -r
  requirements.txt` brought neither. `tests/test_metrics.py` calls
  `eigenvector_centrality_numpy` directly and would fail outright on a clean
  install — but the worse half is silent: `metrics.py` calls the same solver
  inside a `try`, and an `ImportError` drops it to power iteration without a
  word. The two disagree in the sixth decimal, for 2 to 25 characters per play
  across the corpus (largest difference 6 × 10⁻⁶), and `eigenvector` is a
  published column of `characters.csv` and a field of `metrics.json`. A
  dashboard built on a machine without NumPy therefore carried different
  numbers, with nothing on the page to say so.

  Both are now runtime dependencies rather than test ones, at the floors
  NetworkX 3.5 asks for, with the reason recorded beside them. `README.md`
  names them too.

  The fallback also says so now. `_eigenvector_on` caught `ImportError`
  alongside every other failure, which made a missing install look like an
  intractable matrix; it is now caught on its own and reported once per run —
  once, not once per component of every graph in a corpus sweep — naming the
  divergence and what to install. A genuine solver failure keeps its own
  message, which names the component and who is being scored 0.

- **Pair-lines between plays of equal order hid one another.** Every pair
  within Δn ≤ 5 was drawn, but as a straight segment — and plays of equal
  order stand on one vertical. Wasps, Frogs and Ecclesiazusae all have n = 23
  on the stage-direction spine, so the Ecclesiazusae–Wasps line ran straight
  up through Frogs' marker, lay exactly on top of the Ecclesiazusae–Frogs
  line, and lost its only distinguishing stretch under the two dots at the
  top: it read as a link to Frogs alone. Wasps–Frogs, seventeen pixels long in
  fullscreen, vanished entirely under its own endpoints. Six lines were drawn
  in that neighbourhood; four could be seen.

  A line that would run under a third play's dot, or be covered by its own
  two, is now drawn as an arc, sized to clear what hid it where that
  obstruction actually lies, and bowed left, away from the labels. Every
  other line stays straight: on the shipped view exactly two of eleven bow,
  the two that were lost. The Methods panel says what an arc means, and that
  its curvature carries no value.

  One related fault went with it. The background shapes were drawn before
  the coincident-dot offsets were computed, so where two plays coincide
  exactly and their dots are pushed apart, their pair-lines still ended on
  the shared original centre. The offsets now come first, and the lines end
  on the dots as drawn.

- **Two corpus hints described shapes that are not drawn.** "Density × average
  degree" promised "the curve = order", and no curve has been drawn on that
  chart in any release, 1.0.1 included. The "Plays included" hint said
  reference curves recompute with the selection, though none has existed
  since the iso-degree curve was removed. The second now names the median
  crosshairs, which are what recomputes; the first went with its chart, which
  was later removed as redundant (see **Removed**). `tests/test_corpus_charts.py`
  fails on the released hints and checks that every scatter panel has a render
  call and a height rule.

- **Content before the first milestone was dropped without a word.** A speech
  standing ahead of the first `<milestone unit="large-seq"/>` has no unit to
  belong to, and the milestone segmenters emit one segment per declared unit,
  so the unkeyed content is never emitted. Its words and its speaker leave
  that spine's segment table while staying in the play total, and §4 says the
  two reconcile. On a two-speaker test play with one speech before the
  milestones, both textual spines reported 3 of the play's 6 words. The
  stage-direction spine, which does not read milestones, was unaffected.

  The parser's policy is permissive: every schema violation it meets —
  undeclared `@who` ids, a `state-change` aimed at an absent character, a
  middle-seq straddling a large-seq boundary, legacy `@subtype` — is logged
  and parsed through. This was the one case that was silent, and the only one
  whose cost was a wrong number rather than a cosmetic slip.
  `_validate_spine_coverage` now reports it per spine, with the count of
  speeches, the words at stake and the first line, and the run continues as
  before. It stays quiet on the eleven comedies and the bundled example, and
  on a play that carries no milestones at all — a stage-direction-only
  annotation is not a violation.

- **Removed the chorus id-pattern fallback, which rescued nobody.** It was
  the heuristic the castList annotation replaced, still standing behind it
  and claiming in its comment to catch what `@ana` missed. It could not: one
  half of its test looked for a Latin "chor" in the Greek name, where none
  can occur — no character in the corpus matches it — and the other rescued
  only ids that were exactly `choros` / `chorus` or contained `semichor`, so
  `chorosGeronton`, `merosChorouA` and `batrachoi` all fell through. Those
  are precisely the figures whose omission prompted the annotation in the
  first place.

  On the corpus it changed nothing, all 21 chorus figures across the eleven
  plays being annotated, and the re-exported `characters.csv` files come back
  byte-identical. What it could do was mark a chorus on an unannotated file
  while leaving its own halves unmarked — a half-marked chorus in the beat
  chart and the aggregation toggle. Chorus status now comes from the castList
  entry and nowhere else, as the Methods panel already described it; the
  panel now adds that nothing is inferred from the id. Two parser tests hold
  the contract, and the first fails if the fallback returns.

- **"Shared words" said nothing about whose words they are.** The panel
  offered `--weight words` as weighting edges "by shared words", which reads
  as the words the pair exchanged. The weight is the total attributed words
  of every speech in the segments they share, third parties included:
  `build_static` adds the whole `seg.word_count` to each pair in the segment.
  In Clouds the edge between the two silent pupils `mathetesD` and
  `mathetesE` carries 105 words, and neither of them ever speaks — under the
  misreading that edge would have to be 0. Of 65 edges sampled in that play,
  none equals the pair's own words.

  The definition in §0 now says it: all the words spoken in those segments,
  whoever spoke them, not the pair's own. The three later mentions refer back
  to it and are left alone.

- **The README sent readers to a chart that is not there.** It offered "click
  on the density chart to jump to a segment"; the per-play dashboard has no
  density chart, and the two progression charts that stand where it did —
  order over segments, words over segments — are not clickable. Jumping to a
  segment is done from the beat chart, the segment timeline, a heatmap cell
  or a table row, which is what the line now says.

  `renderProgressionChart`'s own comment claimed the same thing, and one more
  besides: that the two panels share "large_seq backdrops, click-to-jump, and
  curve style". They share the x-axis and the curve style. The only
  occurrences of "backdrops" and "click-to-jump" in that function were in the
  comment promising them.

- **`all_in_segment` reads oddly in raw `metrics.json`.** It is a 0-based
  position in the *scanned* sequence, and an empty leading marker is not
  scanned, so it is not the segment's number: Lysistrata's stage-direction
  spine stores 51 beside the label `sd-53`. §5 defines it, but a reader of
  the JSON has no §5 to hand, so the README's `metrics.json` section now says
  it, points at `all_in_segment_label` as the referent, and gives the
  arithmetic — *j* = 52 over 62 scanned segments, 0.8387. The field is
  unchanged: renaming it would break every consumer for a cosmetic gain.

- **A choral song whose text is not transmitted was drawn as silence.** The
  corpus chorus chart and the per-play heatmap decided between "speaking" and
  "present, silent" by the word count, so a chorus `<sp>` whose text is not
  transmitted — the ΧΟΡΟΥ interludes, encoded as
  `<sp who="#choros"><l><gap reason="not-transmitted"/></l>…</sp>` — came out
  grey, as silence. Everywhere else the app follows the `<sp>`: such a speech
  credits its speaker (`Segment.speakers`), keeps the segment's cast, and
  makes no one mute. The heatmap's own Methods article even defined grey as
  "given no ⟨sp⟩", the rule its code did not apply; the chorus chart's
  article admitted the gap in a note.

  Both charts now draw a fourth state, a red hatch on a pale ground:
  *performs, text not transmitted*. It is exactly ten cells in the corpus —
  seven in *Wealth*, two in *Ecclesiazusae*, one at the *Clouds* lacuna — and
  in *Wealth* it outnumbers the segments where the chorus speaks transmitted
  words, six. The chorus data gain a `speaks` series beside `words` and
  `present`; the legend, hints, tooltips and both Methods articles name the
  state; the note that called the interludes silence is gone. Checked in a
  rebuilt corpus: the ten cells, and only those, hatched in both charts; the
  pattern survives SVG export.

  The chart was not missing a speech layer, as an assessment of the corpus
  charts had first claimed: it already shaded cells by words, so the late
  plays' mostly grey chorus rows were visible. What it could not show was
  that the chorus still performs there — only that no text survives.

- **`speech_distribution` lost a field when nobody speaks.** `effective_speakers`
  was added to the populated branch of `compute_speech_distribution` and not to
  the one that answers for a play with no surviving words, so a silent play
  wrote a `metrics.json` without the key. The dashboards tolerate it — the JS
  reads `|| 0` — but anything reading the file programmatically meets a
  `KeyError`. Both branches now return the same six fields, and the key-set
  test covers the empty one, which it did not.

- **Interactive mode ended in a traceback with no terminal attached.**
  `python -m app` with no subcommand launches the guided prompt; with stdin
  closed or on Ctrl-C it raised `EOFError` out of `input()`. It now prints
  "Cancelled." and exits 0. There is nobody to ask, which is not an error.

- **A pasted path kept its quotes in the single-play prompt.** Windows'
  "Copy as path" yields `"C:\…\play.xml"`, and `input()` keeps the quotes
  where argv would not. The corpus prompt stripped them; the single-play
  prompt, the commoner of the two, did not. The stripping now lives in the
  shared text prompt, so both get it.

- **"Custom corpus (1 plays)"** when a single file was analysed as a corpus.

### Changed

- **Density × order opens as the plain plot.** The pair-lines were drawn by
  default; they are now off, like the colouring by average degree, and
  either is a checkbox away in the chart's header. Methods §6 gives the new
  default.

- **The order axis says what it counts.** *Density × order* and *average
  degree × order* labelled their x-axis "order (kept characters)", the word
  of the code (`_kept_characters`) rather than of the reader. It now reads
  "order (number of nodes/characters)": the characters the active network
  model makes nodes, which is what the model radio changes.

- **A play chip highlights its play instead of recolouring it.** Each chip's
  dot used to cycle the play through a seven-colour palette on the scatters.
  Nothing else read the colour — not the figure captions, not the bars,
  heatmap or tables — and it was forgotten on reload. On the current corpus
  it identified nothing, every dot being labelled; used to group plays, it
  made a colour code with no legend, which an exported figure carried without
  a word of explanation. The palette also paired a coral with an orange and a
  red with a green that are hard to tell apart.

  The dot now toggles a single **highlight**: an orange ring around the play's
  dot on all seven scatters, and a bold label. A ring rather than a fill, so it
  stays visible over the average-degree colouring and leaves the fill to data
  or to the one accent colour. Scatter labels are drawn only up to twenty
  plays; above that, highlighted plays keep theirs, since a larger corpus —
  the tragedians bring the extant Greek plays to about forty-four — is where
  the highlight becomes the one way, short of hovering, to find a play on
  every chart. An exported scatter names its highlighted plays in the caption
  ("highlighted: Lys."), so the ring needs no legend. *reset colours* becomes
  *clear highlights*. Checked in the rebuilt dashboard: one click rings
  Lysistrata on all seven scatters, leaves it included, names it in the
  density chart's caption and not in the composition chart's, and survives the
  degree colouring.

- **A play is identified by its TLG work number, not its title.** Sophocles
  and Euripides each wrote an *Electra*, and both cite as *El.* With the English
  title as the play's id, a corpus holding both kept them apart only where the
  output-collision fix had forced it — the folders and the dashboard's internal
  keys. Everything a reader or a script sees still merged them: both
  `metrics.json` files carried `"id": "Electra"`, every chart and chip read
  *El.* twice, the scatter hover read "Electra" twice, and the composition chart,
  which keys its bands on the id, drew both plays' bars into one band.

  The id now comes from the header. The corpus already carries a CTS URN for
  every play (`urn:cts:greekLit:tlg0019.tlg003.perseus-grc2`); the parser keeps
  text group and work, `tlg0019.tlg003`, and drops the edition, which names one
  digital text of the play rather than the play. A bare
  `<idno type="TLG">0019.003</idno>` is accepted too. A header with neither
  falls back to the file name, with a warning. All eleven comedies resolve to
  `tlg0019.tlg001` … `tlg0019.tlg011` with no edit to the corpus. The output
  folders stay named for the English title, so the published tree does not
  move; `source.json` now records the id beside the source file.

  Where two plays of a corpus would share a label, the author's citation form
  is added to both — *Soph. El.*, *Eur. El.* on charts and chips, "Electra
  (Sophocles)" on the beat multiples — read from
  `<author xml:lang="lat"><choice><expan>…</expan><abbr>Soph.</abbr></choice></author>`
  and falling back to the author's name. Collisions are counted over the whole
  corpus, so a play keeps one label whatever is selected, and a corpus without
  a shared title is labelled exactly as before. Hover text now always names the
  author. Both CSV × ALL exports gain an `id` column, first, which joins a row
  to its `metrics.json`.

  Breaking for anything reading `metrics.json`'s `id` (every value changes, e.g.
  `"Clouds"` → `"tlg0019.tlg003"`) or the CSV × ALL columns by position.
  Verified end to end on the eleven comedies plus synthetic Sophoclean and
  Euripidean *Electras* carrying their real URNs — `tlg0011.tlg005` and
  `tlg0006.tlg012`, checked against the Perseus catalogue — in a rendered
  corpus dashboard: distinct labels, hover text, beat titles, composition bands
  and CSV ids, with the comedies' labels unchanged. `tests/test_play_identity.py`
  runs the two *Electras* through the corpus command; parser tests cover the
  URN, the bare number, their precedence, the fallback and the author
  abbreviation.

- **The bundled sample play is a copy of the corpus text, not a second edition
  of it.** `examples/Ar-07-Lys.xml` had drifted: 46 of the baseline's 111
  quantities differed from the authoritative corpus file — 40 characters
  against 39, 329 edges against 302 on the large-seq spine — so the suite was
  pinned to an annotation that no longer existed. The sample is now
  byte-identical to the corpus copy.

  It cannot simply *be* that file: the corpus is a separate repository and a
  separately published dataset, the app promises to run without it checked
  out, and a symlink is not portable to a checkout with `core.symlinks` off.
  So the copy stays, but stops being maintained by hand.
  `tests/refresh_example.py` copies it and regenerates the baseline in one
  step, printing every quantity that moved; `--dry-run` reports without
  writing. `test_baseline.py::test_example_still_matches_the_corpus` compares
  the two by fingerprint rather than by bytes — reformatting is not drift, a
  changed cast is — and fails when a refresh is due, skipping where no corpus
  is checked out, which is the case the bundled sample exists for.

  **Demo-baseline figures quoted in entries above this one** — the six words
  of the joint-speech rule, the single bucket of the `mixed` split — describe
  the sample as it stood before this refresh. The corpus facts in those
  entries are unaffected; they were measured against the corpus all along.

- **One definition of the play's active span.** The bookend trim — leading and
  trailing segments with nobody on stage — was written out twice, identically,
  in `metrics.py` for the temporal Gini and in `corpus_dashboard.py` for the
  chorus beat chart. §5 and §11 are read against each other and the docstring
  asserted the two trims matched; they did, in all 33 comparisons, but nothing
  would have caught it if they had drifted. Now `segmentation.active_span`,
  called from both.

- **Eigenvector centrality says so when both solvers fail.** The fallback
  returned zeros for the whole component in silence, and a zero there is
  indistinguishable from an isolate's legitimate zero. It now logs a warning
  naming the component.

### Removed

- **The iso-degree curve on the corpus density × order chart.** It plotted
  d = k/(n−1) at the corpus median average degree, so that plays above it were
  denser than median for their size. But that relation is an identity, not a
  model: d = 2|E| / (|V|(|V|−1)) and k = 2|E|/|V| give d = k/(n−1) exactly for
  every undirected graph. It follows that "above the curve" and "average degree
  above the corpus median" are the same statement — verified on the eleven
  plays, where the two agree 11 times out of 11 — and the dashboard already
  plots order × average degree as its own scatter, where the same reference is
  a horizontal line needing no formula.

  What the curve cost, by contrast, was specific: a median-relative hyperbola
  that moves when plays are deselected, a domain restriction, a hollow-ring
  convention for points outside it, and a boundary case that the code stated
  three different ways — the article said the curve was undefined at n ≤ k+1
  "(would require d > 1)", the predicate tested n ≤ k+1, and the comment beside
  it said n ≤ k. At n = k+1 density is exactly 1, a complete graph, so only the
  comment was right about where d > 1.

  Gone with it: the drawing code and its k_median, the out-of-domain predicate
  and the hollow-ring rendering, the chart hint, and the two `drawScatter`
  parameters that existed only to serve it. The **median crosshair stays**, and
  density × order now carries it like every other scatter — it had been
  suppressed there because the curve was the reference. The **pair-lines stay**
  too, with their own rationale: they compare each play with its nearest-order
  neighbours and assume nothing. §6 loses one article; §1's density note now
  points at order × average degree.

### Changed

- **Pair-line tooltips carry the average-degree excess beside the density
  one.** A line's height is not the connectivity gap: d = k/(n−1) means
  d_hi/d_lo = (k_hi/k_lo) × ((n_lo−1)/(n_hi−1)), so the residual size
  difference inside the Δn ≤ 5 window is still in it. Two of the corpus's
  eleven lines are *entirely* that residue — Thesmophoriazusae against Wealth
  reads a density excess of 14.2% where the average-degree excess is 0.1%
  (k = 6.93 against 6.94, the same connectivity, 16/14 of the height), and
  Peace against Wasps reads 14.0% against 0.4%. With both numbers in the
  tooltip a reader can see which of the two a line is showing.

  §6 now also records that a play with no other within Δn ≤ 5 is joined to
  nothing — Knights, the most distinctive point on that chart at density
  0.821, has no neighbour and therefore no line, which a reader would
  otherwise read as a statement about the play.

- **The temporal Gini is computed over a character's own stage time, not the
  whole play.** It padded each character's word vector across every active
  segment, including those they are nowhere near, so absence dominated it. On
  the corpus it correlated **+0.971** with the share of segments a character
  does not speak in — a quantity the app already prints in the next column.
  Praxagora's 0.924 was not a statement that her speech comes in bursts; it
  said she speaks in 18% of the play's beats.

  The vector now runs over the segments the character is on stage for. A zero
  is a silence while present; a segment before the entrance or after the exit
  is not in the span at all. The question it answers is how much of a
  character's stage time passes without them speaking — the one question here
  that an encoding with no presence layer cannot pose.

  Re-run on the same 140 characters, the absence correlation falls to −0.666
  (the sign reverses: a short presence has a lower ceiling), and against the
  share of their own stage time spent silent it stands at +0.735 — related, as
  it should be, but r² = 0.54, so it carries distributional information the
  ratio does not. One consequence to expect: the protagonists now cluster,
  0.596 to 0.713 where they used to spread 0.665 to 0.924. That spread was
  absence. All eleven leads speak in 80–96% of their own on-stage segments.

  The span is presence *union* speech, so a speech attributed to a character
  never annotated as entering is still counted and per-character totals still
  reconcile with §4. Ceilings are now per character — (m−1)/m for a span of m
  segments — so Praxagora at 8 segments is measured against 0.875 where
  Dikaiopolis at 74 is measured against 0.986; §5 says so.

  **For readers of `metrics.json` and `characters.csv`:** a new field,
  `n_onstage_segments`, the metric's divisor. The play dashboard's table
  column beside tGini now reads *speaks / on stage* against that denominator
  rather than against the play's span, which would no longer match the metric
  next to it. The baseline held no tGini value at all, only a character count,
  so it now fingerprints the top speaker's tGini and span.

- **"Dialogic cast" is now "speaking cast", everywhere.** The two non-stage
  models were labelled *dialogic cast on play level* and *dialogic cast on
  segment level*. Dialogic claims an exchange between characters, which is
  precisely what the construction article denies of these graphs: an edge
  records that two characters were in the same segment's cast, never that
  either addressed the other. Under the play-level model it is looser still —
  two characters share an edge by standing on stage together in a segment
  where neither speaks.

  The internal keys were already `p-speaking` and `s-speaking`, and the
  definitions already read "speaking is tested once, for the play" and
  "speaking is tested segment by segment", so the label, the key and the
  definition now use one word. `metrics.json` is unchanged — its stored values
  were never the display labels.

  43 occurrences across nine files: the radio labels in both dashboards, 24
  passages of the Methods tab, and the docstrings, comments and test names.
  Two things a reader should know: every dashboard needs regenerating, and
  figures exported before this change carry *dialogic* in their provenance
  caption, so a talk mixing old and new figures will show both. One use of the
  word survives in sense but not in letter — a comment in `segmentation.py`
  about voice-only interjections staying "with the surrounding exchange", where
  the word had its ordinary literary meaning rather than naming a model.

  Three stale comments were corrected in passing, all in `dashboard.py`: the
  mute-mode table still described the modes as `"stage"` and `"dialogic"` with
  a `presence` axis, and the variant-key example listed `"stage:choros"` and
  `"dialogic:choros"` where the keys are `"full:choros"` and
  `"p-speaking:choros"`.

- **§5's DCR article no longer claims two bracket transitions or a direction.**
  It said the mean runs over "every consecutive pair except the two bracket
  artefacts". Across the 99 blocks of the corpus, 66 exclude none, 8 exclude
  one and 25 exclude two — the milestone spines mostly have no empty bookends
  at all. The accompanying note claimed the dialogic models fold boundaries
  away (true only on the stage-direction spine) and that their DCR is
  "generally higher" (true of the segment-level model, false of the play-level
  one, which is *lower* in all 22 milestone blocks). The note is gone rather
  than corrected: the direction is a finding about this corpus, not a property
  of the method, and would need rechecking against every play added.

- **Every character tied for top speaker is now reported.** The top speaker
  came from `max()` over a dict, which returns the first key reaching the
  maximum in insertion order — so a tie was decided by which of the tied
  characters spoke first. That rule was nowhere stated, and in one case it was
  not even a rule: `per_char` was filled by iterating `<sp>/@who`, a *set*, so
  when two characters both first spoke in the same joint speech the winner
  followed Python's per-process string hashing. The same build reported a
  different top speaker from one run to the next (`a` under hash seeds 0, 1
  and 5; `b` under 2, 3 and 4).

  `speech_distribution` now carries **`top_speaker_ids`**, every character
  holding the largest total, sorted by id; the play headline, the corpus
  *top spk* column and both metrics CSVs print the whole list. The share needs
  no change — tied characters share it by definition. `top_speaker_id` stays,
  as the first of that list, for the one field that needs a single referent:
  the top speaker's temporal Gini, which is a different number for each of
  them and has one column. §4 and §5 say so.

  No play in the corpus ties — the leading role leads by thousands of words,
  the closest being Philokleon over Bdelykleon in *Wasps*, 0.299 to 0.285 —
  so nothing in the published output changes and the demo baseline only gains
  the new key. This is insurance for a two-hander, where a tie is where the
  old behaviour would have shown.

  **For readers of `metrics.json`:** `speech_distribution` gains
  `top_speaker_ids`, a list. `top_speaker_id` keeps its meaning where there is
  no tie and is the first of the list where there is.

- **Editorial matter inside a verse no longer counts as spoken words.** The
  word counter read the text of everything nested in an `<l>`, so an editor's
  remark standing inside a line was credited to the character as Greek. Two
  kinds are now skipped wherever they stand: `<note>`, which is the editor
  speaking, and `<gap>`, which marks text that is not there. XML comments go
  with them — lxml's `itertext()` yields their bodies, which the counter had
  been taking as words.

  What is skipped is the element, not the line. The verse resuming after it is
  still counted, and this matters more than the exclusion: 22 words follow a
  `<gap>` in the corpus and 7 follow a `<note>`, and a fix that dropped the
  tails with the elements would have lost them.

  `<del>` keeps counting. An athetesis is a judgement about the line, not a
  claim that its words are absent from the edition, and treating it as a
  deletion would silently take an editor's side.

  Two plays move. *Acharnians* 7,221 → 7,219, both words from Dikaiopolis,
  whose lines carry two gesture glosses — *(ἀνανεύει.)*, *(ἐπινεύει.)* — as
  in-line notes; his share of the play falls 0.4613 → 0.4611. *Thesmophoriazusae*
  7,295 → 7,275: two notes on Perseus line numbering, in English, inside a
  choral line and a line of the Scythian archer (choros 1,566 → 1,556,
  toxotes 343 → 333); the play's Gini moves 0.5404 → 0.5407. The other nine
  plays and the demo baseline are untouched. *Acharnians* now reads 7,219,
  the same figure its segment table showed before the joint-speech change
  above — the two corrections happen to cancel there, and the number means
  something different.

- **One rule for the words of a joint speech.** A speech is credited in full to
  every id in its `@who`, and now every word figure in the app is a sum of
  those credits. The per-character totals, the Gini, the shares and the beat
  chart already worked this way; the per-segment total did not, summing each
  `<sp>` once instead. A dashboard therefore carried two totals that a reader
  could not reconcile: the metrics panel reported 8,122 words for *Lysistrata*
  and its segment table added up to 8,116. The gap was the four-speaker νὴ Δία
  at *Lys.* 237, counted once by one surface and four times by the other.

  Seven joint speeches occur in the eleven comedies, so the segment totals of
  four plays rise to meet the panel figure, which does not move: *Acharnians*
  7,219 → 7,221, *Knights* 8,937 → 8,944, *Lysistrata* 8,116 → 8,122, *Frogs*
  9,204 → 9,208. The affected numbers are the segment table's
  `words` column and `segments.csv`, the word-progression and cumulative
  charts, and `words_shared` on an edge (hence the weight itself under
  `--weight words`). No graph, and no unweighted metric, is touched. The demo
  baseline moves in four keys, all of them word totals, all by the same six
  words.

  The rule is stated once, on `Speech.attributed_words`, and §4 of the Methods
  tab is rewritten around it; §9 now points there instead of restating it. The
  price is worth naming: no figure in the app is the number of words standing
  in the text. *Lysistrata* reads 8,122 everywhere, where the text holds
  8,116. This is an app for measuring speech attributed to characters, and a
  unison really is spoken by each speaker; what it is not is a word count of
  the play.

  **For readers of `metrics.json` and `segments.csv`:** `word_count` on a
  segment is now attributed, so segment totals sum to
  `speech_distribution.total_words_spoken`. Regenerate to pick this up —
  output written by an earlier version mixes the two conventions.

- **`mixed` is counted apart from `unspecified` in the sex composition.** The
  two were bucketed together, which discarded a distinction the encoding takes
  trouble to make: `mixed` is a positive statement about a collective — this
  group comprises both — where `irrelevant`, or no trait at all, says the
  question does not arise or was not recorded. §7 already treats a group's own
  annotation as authoritative, declining to majority-vote traits across its
  parts; the composition counts were contradicting that.

  One character in the corpus carries it, Lysistrata's united chorus, so the
  demo baseline moves by exactly one: `sex.unspecified` 2 → 1, `sex.mixed`
  added at 1, nothing else in the fingerprint touched. `f/(f+m)` is unaffected,
  since it divides female by female plus male and never read the third bucket.

  **For readers of `metrics.json`:** `demographics.sex` gains a `mixed` key.
  The play dashboard's composition row shows it only where the encoding uses
  it, so a play without a mixed collective still reads *male · female ·
  unspec.*

- **Diameter, average path length, clustering and component count are no
  longer greyed out.** They were rendered in grey inside the Headline panel,
  under a footnote calling them low-resolution and "reported for
  completeness". The claim was right and the presentation was not: greying is
  the visual vocabulary of *provisional, do not lean on this*, and these are
  exact values for the graph on screen. There is no sampling here and nothing
  being estimated — the graph is the whole of what the encoding asserts — so
  there is no sense in which they are less true than density or average
  degree standing beside them. A dashboard that appears to disclaim four of
  its own outputs invites a reader to discount the rest.

  What was worth saying is now said as a measured fact instead of a hedge.
  The footnote reports that across the eleven comedies and all 135 model ×
  segmentation combinations the diameter takes three values in all — 2 in 97
  cases, 3 in 33, 4 in 5 — and the cast is connected in 128 of them, so those
  two separate little at this scale; average path length does vary, but its
  spread relative to its mean is 0.13 against density's 0.45, and on graphs
  this dense it largely restates density.

  The Methods panel gains the caveat that was actually missing, which is not
  about cast size at all: clustering is raised **by construction**, since a
  co-occurrence network joins each segment's cast into a clique and so closes
  every triple inside it. That holds for any scene-based co-occurrence
  network, DraCor's included, and it is why high values are expected rather
  than notable. The components article now records that all seven
  disconnected blocks in the corpus occur under the segment-level dialogic
  model, where a character never given an utterance alongside anyone else has
  no edge to draw however much stage time is shared.

### Fixed

- **Eigenvector centrality is computed one connected component at a time.**
  On a disconnected graph the measure was reporting the residue of a
  numerical method rather than a centrality. `eigenvector_centrality_numpy`
  refuses such a graph outright — `AmbiguousSolution`, since the principal
  eigenvector of a disconnected matrix belongs to whichever component has the
  larger spectral radius and says nothing about the rest — so the code fell
  through to power iteration, which does not refuse. It converged on the
  dominant component and left the others decaying towards zero: in
  *Ecclesiazusae* under `s-speaking` the five characters of the hag scene came
  out around 2×10⁻⁶ and the Heraldess at 10⁻²⁰, printed in the character table
  beside real values and sorting as though those figures were peripheral.

  Each component is now scored on its own and normalised to unit length, as
  NetworkX normalises a whole graph. The hag scene's five read 0.304–0.596
  instead of 10⁻⁶, and a character alone in a component is given 0 rather than
  a denormal. Connected graphs take the same path as before and not one
  published value moves — verified node by node against the shipped
  dashboards across all 99 play × model × segmentation blocks.

  Values are comparable within a component and not across them, which is a
  property of the measure rather than of this implementation: where the graph
  splits, the column can rank a small tightly connected component above the
  main action. The Methods panel says so.

- **Table columns sort on their value, not on their rendered text.** Both
  dashboards ordered rows by the string in the cell. The corpus plays table's
  **top spk** column therefore sorted by the speaker's id — *allantopoles*,
  *chremylos*, *dikaiopolis* — when the quantity it reports is the share of
  the play's words that speaker carries, and the ids are in no useful order.
  It now sorts by the share: 28.4% (Dionysos) to 46.1% (Dikaiopolis).

  The same defect made every formatted number sort by its digits. Values
  bounded by 1 and printed to a fixed width were accidentally safe, since
  "0.209" and "0.424" compare the same either way, but anything that can
  reach two digits was not: **avg deg** would have put 12.74 before 3.67, the
  character table's **weighted** degree put 58 before 8, and the
  speech-concentration table's **speak. segs**, printed as "9 / 38 (24%)",
  put 9 after 1 and 2.

  A column may now carry a fourth element, the value to order by, which
  `drawTable` uses in place of the display accessor. Four columns declare
  one; the rest are unaffected.

- **The plot-dynamics indices are read for the active model's own segment
  cast.** `compute_segment_indices` always took each segment's cast to be the
  characters *standing* in it, intersected with the model's node set. That is
  right for the two models whose edges come from co-presence, and wrong for
  the segment-level dialogic model, whose edges come from who speaks: the
  all-in index reported when the speakers had all been *seen*, and the final
  share counted speakers who were merely standing in the closing segment. The
  page then held two notions of "this segment's cast" at once, since the beat
  chart in both dashboards has always followed the model.

  This was a documentation mismatch as much as a bug — the Methods panel
  already specified the behaviour now implemented ("the cast of segment $i$ as
  the active network model sees it"; "under the dialogic models only those who
  speak") — and the direction of the repair was forced: with the edges drawn
  from `Segment.speakers`, a presence-based index describes a graph that is
  nowhere on the page. `compute_segment_indices` now takes the model's
  `segment_cast` alongside its node set, defaulting to `stage`, which leaves
  the raw-spine reading untouched.

  Only `s-speaking` moves: 20 of the 99 play × segmentation × model blocks in
  the Aristophanic corpus, `full` and `p-speaking` bit-identical. Final shares
  fall or hold and all-in indices rise or hold, as they must, speakers being a
  subset of those present. Corpus mean final share under `s-speaking`: `sd`
  0.293 → 0.181, `large-seq` 0.396 → 0.303, `middle-seq` 0.352 → 0.219. The
  sharpest single reading is *Lysistrata*, 0.478 → 0.130 — its finale is sung
  by three of the twenty-three speakers, the rest of the company on stage and
  silent. The denominator never changes: the union of a model's segment casts
  is its node set either way. *Acharnians*, the article's running example, does
  not move under any model or spine.

  Two things that could have made the change unsafe were checked and hold. The
  walk-back to the last segment carrying speech stays, and still lands on an
  acted segment in every block; without it a play closing on silent business
  would read 0.000. And the divisor is not diluted by beats the model cannot
  see: after the fold only 2 of 836 `s-speaking` segments hold characters on
  stage without a speaker, both of them opening beats, so the empty-leading-
  segment rule fires once in the corpus (*Peace*, `sd`, all-in 0.962 → 0.961).

  `max_simultaneous_speakers` is unchanged: it is an actor-rule diagnostic,
  deliberately word-based and model-independent. The temporal Gini keeps its
  presence-based trim in all three models — its span is "first to last
  appearance", when a character was available to speak, which is what makes
  the zero-padding meaningful, and so a different question from who is in a
  segment's cast.

- **A speaking figure's silent parts are no longer dropped from the
  play-level dialogic model.** A `partOf` member that carries no `<sp>` was
  classified as a play-level mute and removed from the `p-speaking` node set,
  even where the figure it is part of speaks at length. Its presence went with
  it, so the figure disappeared from every segment it attended part by part.

  *Ecclesiazusae* is the only affected play, and the effect there is large:
  the chorus arrives in three silent parts (`merosChorouA`, `B`, `C` enter at
  vv. 30, 43, 54 and are merged into `choros` at v. 285, where the parodos
  begins), none of which sings, because the chorus does not sing until it is
  whole. Judged token by token the parts look like mutes; judged as a figure
  they are the chorus. The model therefore showed no chorus at all in the
  prologue, though it stands on stage from v. 30 — three segments of it,
  where the arriving parts share the stage with Praxagora and the three women.
  Such members are now rewritten to their figure before the node set
  is taken, provided the figure itself speaks; the node set stays exactly
  "the characters who speak", and the chorus is present wherever any part of
  it is. *Ecclesiazusae* `p-speaking` goes from 32 to 35 edges (16 nodes,
  unchanged); `full` and `s-speaking` are untouched, as is every other play.

  This also restores the aggregation toggle's monotonicity. Collapsing a group
  can only merge nodes, so it can never raise the edge count — but checking
  `choros` in *Ecclesiazusae* used to *add* edges, because the collapse handed
  the parts' presence to a node that had none of it. The toggle now lowers or
  preserves the edge count in every play and every model. Members that speak
  in their own right — the semichoruses of *Acharnians*, *Peace* and
  *Lysistrata* — are untouched: collapsing those is what the toggle is for.

  The rule is a special provision for a singular case, and it is not free: it
  puts `choros` on stage from v. 30, part by part, before those parts have
  merged into the chorus they are going to become. The encoding keeps those
  two facts apart — `partOf` says the bodies belong to the chorus, `<move
  type="merge">` says when they become one — and the models now read
  different ones, so the stricter reading is relocated rather than lost:
  under `s-speaking` the chorus enters only where it speaks, at v. 285 with
  the parodos. What is not available is a model in which the parts are nobody
  while the aggregation toggle turns them into the chorus.

- **The segment-level dialogic model no longer depends on what a silent
  character does elsewhere in the play.** Two characters speaking on either
  side of a third character's silent entrance were joined by an edge only if
  that third character was a play-level mute. If they spoke in some later,
  unrelated scene they became a node, the adjacent casts then differed, the
  boundary survived the fold, and the two speakers lost their edge — the same
  dramaturgical situation yielding two different graphs.

  The cause was that both mutes-out models folded on the same criterion, the
  kept cast present in each segment. That is right for the play-level model,
  where presence *is* the content, but wrong for the segment-level one, where
  only who speaks in each segment counts. A boundary is now invisible to the
  segment-level model when the characters entering or leaving at it are
  silent on both sides of it, whatever they do elsewhere. An empty stage
  stays a real caesura and is never folded into an occupied segment.

  Across the eleven comedies **no edge changed**: the new rule is a
  coarsening of the old (equal casts imply an empty difference, so anything
  the old fold merged the new one merges too), and every pair it newly brings
  together was already joined elsewhere. Only the segment-level spine moves,
  and it moves towards fewer, truer segments — *Acharnians* 83 → 65, *Clouds*
  45 → 39, *Wasps* 44 → 38 — which shifts the DCR, the segment indices and
  the beat / heatmap binning for that model. Dashboards should be regenerated.

  Two related defects fixed with it. The fold's documented invariant
  ("topology-preserving … order, size, density … unchanged") was false for
  the segment-level model — folding could *create* an edge, and did, once in
  the corpus; it is now stated for the play-level fold only, with the
  segment-level exception spelled out in `fold_for_model` and the Methods
  panel. And `test_fold_is_topology_preserving` only ever ran the play-level
  cast, so it never tested the case where the claim failed; the baseline
  helper meanwhile folded the segment-level spine on `speakers & kept`, a
  rule the app has never used, so that fixture was guarding a spine that did
  not exist. Both now call one shared routine, `segmentation.fold_for_model`.

- **Exported files are now reproducible run to run.** `dynamic.gexf` differed
  between two runs of the same command. `build_dynamic_spell_graph` seeded its
  per-node spell dict by iterating the kept-character *set*, so node insertion
  order followed Python's per-process hash randomisation — and that reached the
  GEXF twice: as the order of the `<node>` elements, and, because networkx
  reports an edge from whichever endpoint it stored first, as the source/target
  orientation of every `<edge>`. The graphs were never wrong (identical node
  sets, identical spells, identical edges as an undirected multiset), but the
  bytes moved, which defeats diffing two output trees to see whether a change
  altered any result. `build_static` and `build_dynamic` already sorted; the
  spell graph now does too. Verified byte-identical across `PYTHONHASHSEED=0`
  and `12345` for all eight artefacts.

- **Corpus dashboard showed the wrong temporal Gini for the mutes-out models.**
  The corpus summary reused the *stage* view's `speech_distribution` for every
  non-aggregated mode block. That is correct for the four play-level word
  metrics it was written for — `gini_words`, `top_speaker_id`,
  `top_speaker_word_share`, `total_words_spoken` are identical in every variant
  — but two segment-axis-dependent fields were later added to the same dict:
  `top_speaker_temporal_gini` and `n_active_segments`, both derived from
  `compute_temporal_gini(segments)`. Under the `sd` spine the mutes-out
  segments are folded (`fold_segments`), so those two genuinely differ per
  mute mode, and the block ended up reporting its own folded `num_segments`
  beside the unfolded spine's tGini.

  Visible as the corpus plays-table **"top spk tGini"** column disagreeing with
  the per-play dashboard for every play under *p-speaking* and *s-speaking* on
  the `sd` spine — 22 of 135 (play × segmentation × model) combinations, by up to
  0.036 (*Peace* 0.731 vs 0.767). `large-seq` and `middle-seq` were unaffected,
  their segments being identical across models; `stage` and all aggregated
  blocks were already correct. The per-play dashboards were right throughout.

  Mode blocks now always take their own variant's `speech_distribution`. A
  regression test (`test_corpus_and_play_dashboards_agree_on_temporal_gini`)
  asserts the two dashboards agree on both fields, and that a block's
  `num_segments` and speech fields come from one and the same variant, across
  every segmentation × model × aggregation combination.

### Changed

- **`edge_rule` renamed to `segment_cast`; its values `presence` / `co_speech`
  to `stage` / `speaking`.** The old names described the axis wrongly. All
  three models build the *same* relation — an undirected co-occurrence
  network, joining the segment's cast into a clique and taking the union over
  segments. In the code the whole difference between them is one line
  (`network.py`): whether a segment's cast is `characters_present` or
  `speakers`. What varies is thus the criterion of presence, not the meaning
  of the edge, and "edge rule" presented two kinds of relation where there is
  one.

  "co-speech" was the damaging half. It reads as a claim about speech
  *interaction* — that the pair spoke to each other — which no graph here
  makes: the graphs are undirected, and `@toWhom` is parsed but never builds
  an edge (addressee information belongs to the perception app). Two
  characters are joined merely by both having spoken in the same segment,
  though each may be addressing a third party or the audience, and one may be
  annotated `#unaware` of the other. In a project whose argument is that
  DraCor measures speech co-occurrence while calling it co-presence, a model
  advertising "co-speech edges" blurred the distinction it exists to draw.

  **Breaking for readers of `metrics.json`:** the field `edge_rule` is now
  `segment_cast`, with `presence` → `stage` and `co_speech` → `speaking`.
  The keyword argument of `build_static`, `build_dynamic` and
  `build_dynamic_spell_graph` is renamed to match. Prose throughout the
  Methods panel, the dashboards, the README and the module docstrings now
  describes all three models as undirected co-occurrence networks and names
  the axis "segment cast".

- **The three models are now named alike everywhere: `full`, `p-speaking`,
  `s-speaking`.** The internal identifiers (`mute_mode`, the dashboard's
  radio values and variant keys, the corpus blocks) were `stage` /
  `dialogic` / `cospeech`, so the CLI names introduced in this release had
  to be translated into them and `cospeech` survived in every exported
  `metrics.json`. One vocabulary now runs from the command line through the
  exports to the dashboard, and the word "co-speech" is gone from the app.
  `p-` and `s-` mark the scope at which a character counts as a speaker —
  the whole play, or the segment at hand.

  **Breaking for readers of `metrics.json`:** `mute_mode` now reports
  `full` / `p-speaking` / `s-speaking`. Dashboards must be regenerated;
  a dashboard built before this release carries the old keys and its model
  switch will not match a newly built corpus page.

- **A middle sequence now knows which large sequence it belongs to.** Before
  segmentation moved to milestones a unit's identity lived in `<div2 n="…">`,
  and the parser read `@n`. A milestone carries no `@n` — the encoding schema
  requires `@xml:id` instead, as "its unit identifier" — so `large_seq_n` and
  `middle_seq_n` had been `None` for every segment of every spine: 0 of 927
  measured across the corpus. Two things depended on them silently. A middle or
  stage-direction segment could not name the large unit containing it, and the
  dashboard's act bands, which group the timeline by that field, collapsed into
  one unlabeled band spanning the whole play.

  `large_seq_n` is replaced by **`large_seq_id`**, filled from the milestone's
  `xml:id` (`L01`, `L02` …) and, on a middle or sd segment, from the large unit
  in force at that point — so *Acharnians* `s030` now reports `L09`, and the
  play's timeline resolves into its 11 act bands. `middle_seq_n` is removed:
  `middle_seq_id` already carries that identity, and `@n` can never supply it.

  **Breaking for downstream readers of `segments.csv`.** The column
  `large_seq_n` is renamed `large_seq_id`; `middle_seq_n` is dropped. The header
  is now `segment_id, label, large_seq_id, large_seq_type, middle_seq_id, …`.

- **A speech whose text is lost now credits its speaker.** `Segment.speakers`
  and the behavioural mute classification (`parser._classify_mutes`,
  `aggregation.aggregate_play`) previously tested `word_count > 0`, so a
  textless `<sp>` counted as silence. Ten speeches in the corpus are textless —
  the seven ΧΟΡΟΥ interludes of *Wealth*, the two of the *Ecclesiazusae*, and
  the lacuna at *Clouds* 888a — and all ten are choral. The effect was that
  *Wealth*'s seven act-dividing songs and the *Ecclesiazusae*'s two registered
  an **empty stage**: no speaker, no node, no edge, in both the large-seq and
  middle-seq spines. The test is now the `<sp>`, not the word count. Per-segment
  `num_speeches` follows the same rule, so a lost interlude reads "1 speech,
  0 words". Word quantities are untouched: `word_count`, per-character totals,
  the speech Gini and every share still measure surviving text only, so a lost
  song is credited as a performance while contributing nothing to any total.
  No character's muteness changes anywhere in the corpus — each of those
  choruses speaks at length elsewhere — and no edge is added, since the
  affected segments hold the chorus alone.

  **One deliberate exception:** `max_simultaneous_speakers` stays word-based.
  It is an actor-rule diagnostic and must count voices attested with surviving
  text; applying the `<sp>` rule there would take *Clouds* from 3 to 4 on the
  strength of the gap at 888a alone. The divergence is commented at the call
  site and stated in the Methods tab.

### Added

- **Primary-segmentation guard.** The parser now ignores segmentation
  milestones carrying `@source` (or `@resp`): those belong to parallel
  scholarly segmentation streams, which the encoding schema admits but the app
  does not yet read. Files containing such streams are processed correctly —
  all views are computed from the primary (unattributed) stream; previously a
  parallel stream would have silently interleaved with the primary and
  corrupted the large-seq/middle-seq views. Reading parallel streams is a
  potential future feature (see README, *Parallel scholarly annotation*).

- **Beat chart: verse-position x-axis (opt-in).** A checkbox on the beat chart —
  on both the per-play dashboard and the corpus small-multiples — re-indexes the
  segment-change-rate line by *stage-time* instead of segment number. Each
  transition is placed at the cumulative verse position where the cast actually
  changes, so a flurry of low-verse doorway segments collapses into a tight
  cluster and turnover between long scenes stands alone in open space. Off by
  default; the segment-index view is unchanged. It surfaces, for instance, that
  *Wealth* spends its first fifth (≈ 285 of 1396 verses) in a single
  entrance-free prologue before the parodos — invisible when every segment is
  drawn at the same width. Computed in the dashboard JavaScript from the
  per-segment `verse_count` series already present in the payload; the empty
  pre-play transition is skipped consistently with the change-rate series. No
  API, data-format, or metric change. The order- and verses-over-segments charts
  keep the segment-index axis (verse re-indexing is meaningful only for the
  transition series).

### Changed

- **Corpus beat-chart small multiples: larger, and every transition marked.**
  Each small multiple is now wider and taller (grid cells from 220 to 300 px
  wide, sparkline from 80 to 110 px tall) and carries a dot at every segment
  transition, so individual beats stay locatable when the verse-position view
  packs them tightly. In fullscreen the cells enlarge substantially (≈ 520 px
  wide, 170 px tall) for close reading, with thicker line and larger dots.
  Display-only; no data change.

- **Chorus detection follows the castList performer annotation.** The parser now
  reads chorus membership from each role's `<actor ana="#chorus">` in the
  `<castList>`, falling back to a legacy `castItem/@ana` for un-migrated files.
  Previously chorus status came from `castItem/@ana` plus an `xml:id`-substring
  heuristic, which silently missed choral entities whose id did not contain
  "chor" — e.g. the frog-chorus (`batrachoi`) of *Frogs* and the various
  semichoria, which were rendered as ordinary collectives. Collective status
  continues to derive from `<personGrp>`, and muteness stays behavioural, so the
  performer categories `#actor` / `#extra` deliberately do not touch it (a silent
  role cast to an actor remains behaviourally mute). Affects only what `is_chorus`
  governs — node colour, the chorus chip, the corpus chorus-beat heatmap, and the
  exported node attribute; network topology and metrics are unchanged.

### Added

- **Heatmap row order: "most stage entrances/exits."** A fourth sort mode for
  the per-play character × segment heatmap, ordering characters by how many
  times they cross the stage threshold (entrances plus exits) under the active
  segmentation and network model. It surfaces the figures that shuttle on and
  off — running slaves, messengers, the errand-runner of a teasing scene —
  which the default "loudest first" order pushes to the bottom because they
  speak little. A character on stage throughout scores the minimum; a rapid
  in/out sequence of a single character scores high, so such a sequence becomes
  legible as one striped row rather than only as aggregate teeth on the beat
  chart. Documented in the in-app Methods panel, §10. Computed in the dashboard
  JavaScript from the per-segment `characters_present` sequence; no API,
  data-format, or metric change.

- **Beat chart: interactive nodes.** Hovering any marker on the per-play beat
  chart shows the segment transition it represents (e.g. "segment 7 → 8") and its
  change-rate value, so a spike can be read back to an exact segment instead of
  estimated against the axis; **clicking** a marker scrubs the dynamic graph to
  that segment, matching the click-to-jump of the segments table and heatmap.
  Each marker carries a larger transparent hit target. (The corpus
  small-multiples remain node-less sparklines by design.)

### Changed

- The per-play **segment table** now shows the **full cast present** in each
  segment. The cast column previously truncated to the first 8 names (and, under
  the co-speech model, the first 5 present-but-silent names) with an ellipsis;
  crowd segments — the assembly of *Acharnians*, the `all_in` scenes — now list
  every character on stage. Display-only change; the embedded segment data and
  the CSV/GEXF exports already carried the full cast.

## [1.0.1] — 2026-06-05

### Removed

- The paper-figure scripts (`figures/`) and the one-off corpus-migration
  utility (`scripts/`) are no longer shipped — they are auxiliary to the tool
  and not imported by it. They remain available in the `v1.0.0` git tag. No
  API change.

## [1.0.0] — 2026-06-05

First public release.

### Features

- **TEI parser** (`parser.py`) — reads SkeneGraph-schema (TEI-compatible) drama
  into a `PlayData` model: characters, `<move>` stage directions, speeches, and
  the `div2` / `div3` hierarchy.
- **Three segmentation methods** (`segmentation.py`) — `sd` (stage directions),
  `div3` (scene), `div2` (act).
- **Three network models** over two orthogonal axes — cast filter (mutes in /
  out) × edge rule (co-presence / co-speech): `stage`, `dialogic`, `cospeech`.
- **Collective-figure aggregation** (`aggregation.py`) — the chorus and its
  subdivisions optionally collapsed to one node or kept distinct (`partOf`).
- **Static and dynamic graphs** (`network.py`) — static co-presence aggregate
  plus a per-segment dynamic graph carrying `<spells>`.
- **DraCor-compatible metrics** (`metrics.py`) — network-, character-, and
  segment-level measures.
- **Exporters** (`exporter.py`) — `metrics.json`, `characters.csv`,
  `segments.csv`, `networkdata.csv`, GEXF (static + dynamic), GraphML.
- **Self-contained dashboards** (`dashboard.py`, `corpus_dashboard.py`) — one
  HTML file per play / corpus, with an in-app methods panel.
- **CLI** (`app.py`) — `analyze` (one play) and `corpus` (many) subcommands.

[Unreleased]: https://github.com/s8stchro/SkeneGraph-Net/compare/v2.0.0...HEAD
[2.0.0]: https://github.com/s8stchro/SkeneGraph-Net/releases/tag/v2.0.0
[1.0.1]: https://github.com/s8stchro/SkeneGraph-Net/releases/tag/v1.0.1
[1.0.0]: https://github.com/s8stchro/SkeneGraph-Net/releases/tag/v1.0.0
