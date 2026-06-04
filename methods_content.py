"""Methods reference panel shared by the per-play and corpus dashboards.

Returns a self-contained HTML fragment with the formulas for every metric
the app computes, rendered via KaTeX, with explicit notes on the
relationship to DraCor's published definitions.

The fragment uses KaTeX delimiters:
    $...$       inline math
    $$...$$     display math
Auto-render runs the first time the Methods tab is shown.

The fragment is inserted into both dashboards via a literal placeholder
(`<!--METHODS_HTML-->`) and `str.replace`, so its curly braces don't have to
be escaped for `str.format`.
"""

from __future__ import annotations


def methods_panel_html() -> str:
    """Returns the HTML content of the Methods view tab."""
    return _HTML


_HTML = r"""<div class="methods-content">
  <p class="methods-intro">
    Reference for every metric the dashboard computes, with formulas and
    notes on how each relates to DraCor's published definitions.  Formulas
    refer to an undirected graph $G = (V, E)$.  $N$ is the number of
    segments produced by the chosen segmentation; $S_i$ is the cast of
    segment $i$ in the sense fixed by the active edge rule (see below).
  </p>

  <article class="metric" style="background: #fbf8ec; border-left: 3px solid #d6c87a; padding: 8px 12px; margin-bottom: 18px;">
    <h4>Edge semantics &mdash; three network models, two orthogonal axes</h4>
    <p>The dashboard offers <i>three</i> network models, chosen by the
    <b>"Network model"</b> radio group.  This is the central
    methodological choice in the app: each model is a different
    decision about what counts as a node and what counts as an edge.
    Two orthogonal axes underlie the three options:</p>
    <ol>
      <li><b>Cast filter</b> (play-level).  Are play-level mute
      characters &mdash; those who never utter a single verse line
      anywhere in the play &mdash; included as nodes?</li>
      <li><b>Edge rule</b> (segment-level).  Does an edge mean
      "co-present on stage in the same segment", or "speak in the
      same segment"?</li>
    </ol>
    <p>The three useful combinations:</p>
    <table style="font-size: 12.5px; border-collapse: collapse; margin: 8px 0;">
      <tr><th style="text-align: left; padding-right: 16px;">model</th>
          <th style="text-align: left; padding-right: 16px;">node set</th>
          <th style="text-align: left;">edge $(u,v)$ iff</th></tr>
      <tr><td><b>stage co-presence</b> (default)</td>
          <td>all characters who appear in <i>any</i>
          <code>characters_present</code> set, including play-level mutes</td>
          <td>$u, v$ both in <code>characters_present</code>$(S_i)$ for some $i$</td></tr>
      <tr><td><b>dialogic cast on play level</b></td>
          <td>characters with $\geq 1$ non-empty <code>&lt;l&gt;</code>
          anywhere in the play (play-level mutes excluded)</td>
          <td>$u, v$ both in <code>characters_present</code>$(S_i)$ for some $i$
          &mdash; same edge rule as stage, but over the smaller node set</td></tr>
      <tr><td><b>dialogic cast on segment level</b></td>
          <td>same as above (play-level mutes excluded)</td>
          <td>$u, v$ both in <code>speakers</code>$(S_i)$ for some $i$
          &mdash; edge requires they each have a verse line <em>in that
          segment</em></td></tr>
    </table>
    <p>The fourth combination (include play-level mutes as nodes but
    define edges by co-speech) is incoherent &mdash; mute characters
    would become isolated nodes &mdash; and is not generated.</p>
    <p><b>What the three options separate.</b>  Read together, the
    three models decompose a single comparative finding into
    two independent contributions.  Take Lysistrata: under
    <i>stage co-presence</i>, $\langle k \rangle = 14.65$ &mdash; far
    above the corpus norm.  Switching to <i>dialogic cast on play
    level</i> (same edges, smaller node set) yields
    $\langle k \rangle = 9.83$: the $4.82$-unit drop attributes that
    much of the original $14.65$ to <em>silent attendants, archers,
    and other pure-mute characters</em>.  Switching further to
    <i>dialogic cast on segment level</i> (same node set, stricter
    edge rule) yields $\langle k \rangle = 4.61$: a further $5.22$-unit
    drop, attributable to <em>silent stage co-presence among speakers
    themselves</em> &mdash; moments where a dialogic character is on
    stage but not speaking.  The decomposition tells us that
    <em>roughly half</em> of Lysistrata's network-density anomaly is
    not driven by mute characters at all but by the women's collective
    stage occupation and the chorus halves' co-presence as silent
    witnesses to each other's scenes.</p>
    <p>Edge weight $w(u, v)$ counts the number of segments where the
    pair is jointly in the operative segment-cast (under each model's
    own definition).  Switching the radio invalidates the cached
    layout and resets the dynamic-graph slider.  The active model is
    shown as a chip in the dashboard header, so any screenshot
    documents the methodological configuration that produced it.</p>
  </article>

  <section class="methods-section">
    <h3>1. Network-level metrics</h3>

    <article class="metric">
      <h4>order</h4>
      <p>$|V|$ &mdash; the number of vertices in the network.  Under
      <i>stage co-presence</i>, $V$ is the full appearing cast
      (categories 1+2+3); under the two <i>dialogic-cast</i> models,
      $V$ collapses to characters who speak at least once in the play
      (categories 1+3).</p>
      <p class="note"><b>Terminology.</b>  The strict graph-theoretic
      convention (Diestel; Bondy &amp; Murty; West) is
      <em>order</em> $= |V|$ and <em>size</em> $= |E|$.  In the
      applied network-science literature &mdash; and in
      <a href="https://dracor.org/doc/api">DraCor's <code>/metrics</code>
      schema</a> &mdash; "size" is routinely used for $|V|$ instead.
      SkeneGraph-Net adopts the graph-theoretic convention in its
      dashboard labels and methods text (this entry, the chart axes,
      etc.) for terminological discipline, while retaining
      <code>size</code> as the JSON field name in <code>metrics.json</code>
      for DraCor-API parity.  In short: every "order" you see in a
      label or chart axis maps to the field DraCor calls "size".</p>
      <p class="ref"><b>DraCor:</b> <code>size</code> (the same
      quantity, under DraCor's label).  Equivalent to
      <i>dialogic cast on segment level</i> applied at the scene level
      (DraCor's single segmentation).</p>
    </article>

    <article class="metric">
      <h4>numEdges</h4>
      <p>$|E|$ &mdash; unordered character pairs $\{u, v\}$ such that
      $u, v \in S_i$ for at least one segment $i$, with $S_i$ defined by
      the active edge rule above.</p>
      <p class="ref"><b>DraCor:</b> <code>numEdges</code>.  Same shape;
      absolute values diverge through (a) edge rule (presence vs
      co-speech), (b) segmentation granularity (one vs three).</p>
    </article>

    <article class="metric">
      <h4>density</h4>
      <p>$$d = \frac{2 \, |E|}{|V| \, (|V| - 1)}$$</p>
      <p>The fraction of all possible undirected edges that exist.
      $0 \le d \le 1$.</p>
      <p class="ref"><b>DraCor:</b> <code>density</code>.  Identical formula
      (this is an identity for undirected graphs).</p>
    </article>

    <article class="metric">
      <h4>average degree</h4>
      <p>$$\langle k \rangle = \frac{2 \, |E|}{|V|} = d \cdot (|V| - 1)$$</p>
      <p>The mean number of co-present neighbours per character.</p>
      <p class="ref"><b>DraCor:</b> <code>averageDegree</code>.  Same.</p>
    </article>

    <article class="metric">
      <h4>max degree, max-degree ids</h4>
      <p>$$k_{\max} = \max_{v \in V} \deg(v)$$</p>
      <p>The highest degree found in $V$.  The dashboard also reports
      the character(s) attaining $k_{\max}$.</p>
      <p class="ref"><b>DraCor:</b> <code>maxDegree</code>,
      <code>maxDegreeIds</code>.  Same.</p>
    </article>

    <article class="metric">
      <h4>diameter, average path length</h4>
      <p>$$D = \max_{u, v \in V'} d(u, v), \qquad
         \langle d \rangle = \frac{1}{|V'| (|V'| - 1)} \sum_{u \neq v \in V'} d(u, v)$$</p>
      <p>where $d(u, v)$ is the shortest-path distance and $V'$ is the
      largest connected component (the DraCor convention &mdash; otherwise the
      diameter is infinite for disconnected graphs).</p>
      <p class="ref"><b>DraCor:</b> <code>diameter</code>,
      <code>averagePathLength</code>.  Same.  <em>Caveat: these have very
      low resolution on small ancient-drama networks &mdash; typically
      $D \in \{2, 3\}$ and $\langle d \rangle \in [1.5, 2.0]$ across the
      whole Greek corpus.</em></p>
    </article>

    <article class="metric">
      <h4>average clustering coefficient</h4>
      <p>$$\langle C \rangle = \frac{1}{|V|} \sum_{v \in V}
         \frac{2 \, |\{e_{ij} : v_i, v_j \in N(v),\; e_{ij} \in E\}|}
              {\deg(v) (\deg(v) - 1)}$$</p>
      <p>The mean over all nodes of the local clustering coefficient
      &mdash; the fraction of $v$'s neighbour pairs that are themselves
      connected.</p>
      <p class="ref"><b>DraCor:</b> <code>averageClustering</code>.  Same.
      <em>Caveat: dominated in ancient drama by the chorus's near-universal
      connectivity (typical range 0.7&ndash;0.95 across genres).</em></p>
    </article>

    <article class="metric">
      <h4>number of connected components</h4>
      <p>$c(G)$ &mdash; the number of maximal connected subgraphs of $G$.
      Usually $1$ in any reasonably annotated ancient play.</p>
      <p class="ref"><b>DraCor:</b> <code>numConnectedComponents</code>.  Same.</p>
    </article>
  </section>

  <section class="methods-section">
    <h3>2. Per-character (centrality) metrics</h3>

    <article class="metric">
      <h4>degree, weighted degree</h4>
      <p>$$\deg(v) = |N(v)|, \qquad
         \deg_w(v) = \sum_{u \in N(v)} w(u, v)$$</p>
      <p>Unweighted = number of co-present partners.  Weighted = total
      number of segments in which $v$ is co-present with anyone.</p>
      <p class="ref"><b>DraCor:</b> <code>degree</code>,
      <code>weightedDegree</code>.  Same.</p>
    </article>

    <article class="metric">
      <h4>betweenness centrality</h4>
      <p>$$B(v) = \sum_{s \neq v \neq t}
         \frac{\sigma_{st}(v)}{\sigma_{st}}$$</p>
      <p>The fraction of shortest paths between all other-pair nodes that
      pass through $v$ (normalised to $[0, 1]$).</p>
      <p class="ref"><b>DraCor:</b> <code>betweenness</code>.  Same
      (NetworkX <code>betweenness_centrality</code> in both apps).</p>
    </article>

    <article class="metric">
      <h4>closeness centrality</h4>
      <p>$$C(v) = \frac{|V'| - 1}
         {\sum_{u \in V' \setminus \{v\}} d(v, u)}$$</p>
      <p>The inverse of $v$'s mean distance to every other node in its
      connected component.  Larger = more central.</p>
      <p class="ref"><b>DraCor:</b> <code>closeness</code>.  Same.</p>
    </article>

    <article class="metric">
      <h4>eigenvector centrality</h4>
      <p>$$A \mathbf{x} = \lambda \mathbf{x}, \qquad
         x_v \propto \sum_{u \in N(v)} x_u$$</p>
      <p>The principal eigenvector of the adjacency matrix $A$ (weighted
      by $w$).  A character is central if their neighbours are central.</p>
      <p class="note"><b>Note:</b> eigenvector centrality is the only
      weighted centrality in the dashboard; betweenness, closeness, and
      the clustering coefficient are all computed on the unweighted graph.
      The weighted call follows the NetworkX default
      (<code>eigenvector_centrality_numpy(G, weight="weight")</code>),
      where each edge's weight is the number of segments in which its
      endpoints are co-present.</p>
      <p class="ref"><b>DraCor:</b> <code>eigenvector</code>.  Same
      (NetworkX <code>eigenvector_centrality_numpy</code>).</p>
    </article>
  </section>

  <section class="methods-section">
    <h3>3. Cast composition</h3>

    <article class="metric">
      <h4>speakers / mutes</h4>
      <p>A character is <b>mute</b> iff the sum of $\mathrm{word\_count}$
      across speeches with that character in @who is exactly zero.</p>
      <p class="ref"><b>DraCor:</b> exposes the TEI <code>#mute</code>
      annotation directly but does not include mutes in its
      co-presence network.  Our app classifies muteness
      <em>behaviourally</em>, because the <code>#mute</code> annotation
      is often omitted on minor mute roles (in our <em>Acharnians</em>
      annotation only $1$ of $18$ mute characters had been tagged).</p>
    </article>

    <article class="metric">
      <h4>individuals / collectives</h4>
      <p>Distinguished by TEI element:
      $\langle\mathrm{person}\rangle$ = individual,
      $\langle\mathrm{personGrp}\rangle$ = collective.</p>
      <p class="ref"><b>DraCor:</b> exposes <code>isGroup</code> on each
      character.  Equivalent.</p>
    </article>

    <article class="metric">
      <h4>male / female / unspecified</h4>
      <p>From <code>&lt;trait type="sex"&gt;</code>.  Values
      <code>male</code> and <code>female</code> count as themselves;
      everything else (<code>undefined</code>, <code>unknown</code>,
      <code>mixed</code>, <code>indeterminate</code>,
      <code>indifferent</code>, or missing) is <em>unspecified</em>.</p>
      <p class="ref"><b>DraCor:</b> exposes <code>sex</code> with values
      <code>MALE</code> / <code>FEMALE</code> / <code>UNKNOWN</code>.
      Same source data, different normalisation.</p>
    </article>

    <article class="metric">
      <h4>human / divine / animal / concept</h4>
      <p>From <code>&lt;trait type="nature"&gt;</code>.
      <code>concept</code>, <code>personified-concept</code> and
      <code>abstraction</code> are merged into <em>concept</em>; values
      not in the four canonical categories collapse to
      <em>other</em>.</p>
      <p class="ref"><b>DraCor:</b> does not surface this trait in its
      API.  Specific to SkeneGraph-Net and the SkeneGraph corpus
      annotation.</p>
    </article>

    <article class="metric">
      <h4>composition ratios (corpus plays table only)</h4>
      <p>The corpus-dashboard plays table reports three composition
      ratios that surface signals harder to read from the raw counts:</p>
      <p>$$\text{spk/cast} = \frac{|\text{speakers}|}{|\text{speakers}|+|\text{mutes}|}$$</p>
      <p>The fraction of the cast that actually speaks somewhere in the
      play.  Low values signal a play with a heavy silent presence
      (procession crowds, mute attendants); high values signal a play
      whose cast is almost entirely dialogic.</p>
      <p>$$\text{col/spk} = \frac{|\text{collective speakers}|}{|\text{speakers}|}$$</p>
      <p>The fraction of speaking characters that are collectives
      (chorus, semichoruses, groups).  High values indicate
      chorus-driven dramaturgy; low values, individual-driven.</p>
      <p>$$\text{f}/(\text{f}+\text{m}) = \frac{|\text{female}|}{|\text{female}|+|\text{male}|}$$</p>
      <p>The fraction of sexed cast that is female (characters with
      <em>unspecified</em> sex are excluded from both numerator and
      denominator).  Bounded $[0, 1]$; near $0$ for most Aristophanic
      comedies, around $0.5$ for the women's plays
      (<em>Lysistrata</em>, <em>Thesmophoriazusae</em>,
      <em>Ecclesiazusae</em>).</p>
      <p class="ref"><b>Aggregation convention.</b>  All three ratios
      are computed from the <em>fully-aggregated</em> demographics
      &mdash; <code>&lt;relation name="partOf"&gt;</code> groups are
      collapsed so that <em>e.g.</em> the split chorus of
      <em>Lysistrata</em> (<code>chorosAndron</code> +
      <code>chorosGynaikon</code>) is counted as a single chorus.  The
      per-play dashboard's cast-composition pane shows the raw counts;
      the corpus table reports the structurally-equivalent number.</p>
      <p class="ref"><b>Network-model response.</b>  The ratios are
      pre-computed under all three modes and swap with the corpus
      dashboard's "Network model" radio.  Under <em>stage co-presence</em>
      the denominators are the full cast and the female share counts
      all sexed characters.  Under either of the two <em>dialogic-cast</em>
      models, the demographics excludes play-level mute characters:
      <code>spk/cast</code> becomes trivially $1.0$ (every visible
      character speaks somewhere), <code>f/(f+m)</code> shifts to the
      female share <em>among speakers only</em> (revealing how much of
      a play's female presence is silent), and <code>col/spk</code>
      stays the same (mutes never contribute to the speaker count
      under any of the three modes).  The two dialogic-cast modes
      produce identical composition ratios because the play-level cast
      filter is the same; they differ only in the edge rule, which
      affects the network metrics, not the demographic counts.</p>
    </article>
  </section>

  <section class="methods-section">
    <h3>4. Speech distribution</h3>

    <article class="metric">
      <h4>total verses spoken, per-segment "num_speeches"</h4>
      <p>$\sum$ verse_count over every non-empty
      $\langle\mathrm{sp}\rangle$.  A speech is "empty" iff its
      $\mathrm{word\_count} = 0$, which is the case for
      $\langle\mathrm{sp}\rangle\langle\mathrm{l/}\rangle\langle/\mathrm{sp}\rangle$
      placeholders (lost choral interludes, sound cues, annotator
      bookkeeping).  Such placeholders are excluded from every metric
      consistently: from this total, from per-character verse totals,
      from the speech-distribution Gini, from "max simultaneous
      speakers", and from the per-segment <code>num_speeches</code>
      reported in the segments table.</p>
      <p class="ref"><b>DraCor:</b> total verses not in
      <code>/metrics</code> but available via the spoken-text
      endpoints; DraCor's <code>/spoken-text-by-character</code> also
      counts only utterances with text.</p>
    </article>

    <article class="metric">
      <h4>top speaker, top-speaker verse share</h4>
      <p>The character with the largest verse total, and the share
      $\frac{\mathrm{top\_verses}}{\mathrm{total\_verses}}$ of the play's
      verses they speak.</p>
      <p class="ref"><b>DraCor:</b> not surfaced as a single number in
      <code>/metrics</code>; computable from
      <code>/spoken-text-by-character</code>.  Standard "protagonist
      dominance" indicator.</p>
    </article>

    <article class="metric">
      <h4>Gini coefficient (verses)</h4>
      <p>$$G = \frac{2 \sum_{i=1}^{n} i \cdot v_{(i)}}
              {n \sum_{i=1}^{n} v_{(i)}} - \frac{n + 1}{n}$$</p>
      <p>where $v_{(1)} \le v_{(2)} \le \ldots \le v_{(n)}$ are the
      sorted per-character verse totals.  $G = 0$: perfectly equal;
      $G \to 1$: one character speaks everything.</p>
      <p class="ref"><b>DraCor:</b> not in <code>/metrics</code>.
      Following the DH convention (Jockers,
      <em>Macroanalysis</em>, 2013).  Specific to SkeneGraph-Net.</p>
    </article>
  </section>

  <section class="methods-section">
    <h3>5. Plot dynamics &mdash; Trilcke / Fischer 2017</h3>

    <article class="metric">
      <h4>segment-change rate</h4>
      <p>$$r_i = \frac{|S_i \mathbin{\triangle} S_{i+1}|}
                       {|S_i \cup S_{i+1}|}$$</p>
      <p>The Jaccard distance between the casts of consecutive
      segments &mdash; equivalent to the add+delete-only Levenshtein
      distance normalised by union (Fischer/Trilcke 2017, Fig. 3).</p>
      <p class="ref"><b>DraCor:</b> not surfaced in <code>/metrics</code>
      directly, but rendered in the front-end's beat charts
      (dracor-frontend issue #65, following Trilcke et al.).  We
      recompute in-browser so the value responds to the dashboard's
      network-model radio.</p>
    </article>

    <article class="metric">
      <h4>drama-change rate (DCR)</h4>
      <p>$$\mathrm{DCR} = \frac{1}{N - 1} \sum_{i=1}^{N - 1} r_i$$</p>
      <p>The mean segment-change rate over all $N - 1$ transitions.
      Range $[0, 1]$.  Low = "low-dynamic" play (uniform transitions);
      high = continuous churn.</p>
      <p class="note">Computed over the active model's spine (&sect;9):
      under the mutes-out models the $N - 1$ transitions exclude the
      boundaries folded away as invisible to the model, so DCR there
      measures turnover of the <em>dialogic</em> constellation rather than
      of stage traffic, and is generally higher than a count over the
      stage spine would give.</p>
      <p class="ref"><b>DraCor:</b> implemented in the front-end
      (Fischer/Trilcke 2017, "Progression-based measures").</p>
    </article>

    <article class="metric">
      <h4>$\sigma$ (change-rate standard deviation)</h4>
      <p>$$\sigma = \sqrt{\frac{1}{N - 1} \sum_{i=1}^{N - 1}
            \left( r_i - \mathrm{DCR} \right)^2}$$</p>
      <p>The variability of $r_i$ around its mean.  High $\sigma$ =
      "high-dynamic" play (extensive cast changes alternate with small
      ones); low $\sigma$ = same rhythm throughout
      (Fischer/Trilcke 2017, Figs. 8&ndash;9).</p>
      <p class="ref"><b>DraCor:</b> a derived measure in the original
      paper, also rendered as a typological axis there.</p>
    </article>

    <article class="metric">
      <h4>all-in segment, all-in index</h4>
      <p>Let $S_{\mathrm{tot}} = \bigcup_{i = 1}^{N} S_i$.  Let $j$ be the
      smallest index with $\bigcup_{i \le j} S_i = S_{\mathrm{tot}}$
      &mdash; the segment by which the entire appearing cast has appeared.
      Then:</p>
      <p>$$\text{all-in segment} = j, \qquad
         \text{all-in index} = \frac{j + 1}{N}$$</p>
      <p>The index sits in $(0, 1]$.  Close to $1$ = the cast keeps
      growing until the end (often tragedies); well below $1$ = the play
      introduces its whole cast early (often comedies).
      Fischer/Trilcke 2017, "Event-based measures", Fig. 1.</p>
      <p class="ref"><b>DraCor:</b> <code>allInIndex</code>,
      <code>allInSegment</code>.  Published on Greek plays.  Identical
      formula, but our value differs because we (a) use a finer (sd)
      segmentation by default and (b) include mutes by default.</p>
    </article>

    <article class="metric">
      <h4>final-scene size</h4>
      <p>$$\text{final-scene size} =
         \frac{|S_{\mathrm{last\ non\text{-}empty}}|}{|S_{\mathrm{tot}}|}$$</p>
      <p>The fraction of the all-appearing cast that is on stage in the
      last segment containing speech.  Trilcke/Fischer 2017, Fig. 2
      (comedy mean $\approx 0.49$, tragedy $\approx 0.27$).  We pick the
      last <em>non-empty</em> segment because stage-direction
      segmentation appends an empty terminal marker.</p>
      <p class="ref"><b>DraCor:</b> derived measure in
      Trilcke/Fischer 2017; not in <code>/metrics</code> directly.</p>
    </article>

    <article class="metric">
      <h4>max simultaneous speakers</h4>
      <p>$$\max_{1 \le i \le N}
         |\{c \in S_i : \exists\,\mathrm{sp\ in}\ S_i\ \text{with}\
              \mathrm{verse\_count} > 0\ \text{and}\ c \in \mathrm{@who}\}|$$</p>
      <p>The largest number of distinct speakers uttering at least one
      word in a single segment.  A diagnostic for the classical
      three-actor rule in tragedy (typically $\le 3$; Old Comedy
      regularly breaks it).</p>
      <p class="ref"><b>DraCor:</b> not in <code>/metrics</code>.
      Specific to SkeneGraph-Net and to ancient-drama studies.</p>
    </article>

    <article class="metric">
      <h4>per-character temporal Gini (tGini)</h4>
      <p>For each character $c$, build the per-segment verse vector
      $\mathbf{v}^{(c)} = (v^{(c)}_1, v^{(c)}_2, \ldots, v^{(c)}_N)$
      over the dramaturgically-active span (segmenter bookend markers
      stripped), with $v^{(c)}_i$ counting only verses in segment $i$
      attributed to $c$ in non-empty <code>&lt;sp&gt;</code> elements.
      Then:</p>
      <p>$$\mathrm{tGini}(c) = \frac{2 \sum_{i=1}^{N} i \cdot v^{(c)}_{(i)}}
            {N \sum_{i=1}^{N} v^{(c)}_{(i)}} - \frac{N + 1}{N}$$</p>
      <p>where $v^{(c)}_{(i)}$ is the $i$-th order statistic of
      $\mathbf{v}^{(c)}$ (sorted ascending, <em>zeros kept</em>).
      Range $[0, 1)$: $0$ = perfectly even across all $N$ active
      segments; values near $1$ = the entire verse total in a single
      segment.</p>
      <p>The measure is perpendicular to the play-level
      <code>gini_verses</code> (&sect;4).  That metric collapses the
      segment axis and asks "is speech concentrated on one character?";
      tGini holds the segment axis open and asks, for one character at
      a time, "is that character's speech concentrated in a few scenes
      or spread across the play?"  The two operate on the same
      character &times; segment matrix but along orthogonal axes.</p>
      <p><b>Operationalisation: zeros kept.</b>  Three operationalisations
      were considered &mdash; (1) all $N$ active segments (zero-padded
      for silent and absent segments); (2) only segments where the
      character is on stage (silent presence counts as zero, absence
      excluded); (3) only segments where the character actually speaks
      (zeros excluded entirely).  Operationalisation (1) is the
      default.  Probing on the Aristophanic corpus (sd segmenter)
      shows that (3) collapses to a flat $0.51$&ndash;$0.64$ range
      across all 11 plays &mdash; once a character is speaking, the
      unevenness <em>within their speaking turns</em> is roughly the
      same everywhere.  The dramaturgically informative variation
      lives in the presence/absence pattern that (1) catches: under
      (1) the corpus spreads $0.66$&ndash;$0.93$.</p>
      <p><b>Reading: steady vs burst protagonists.</b>  Under (1) the
      Aristophanic corpus separates into two protagonist types.
      <em>Steady</em> leads (low tGini, ~$0.66$&ndash;$0.73$:
      Mnesilochos, Strepsiades, Dikaiopolis, Pisthetairos, Trygaios)
      are onstage continuously and accumulate verses by sustained
      participation.  <em>Burst</em> leads (high tGini,
      ~$0.85$&ndash;$0.93$: Lysistrate, Chremylos, Praxagora) deliver
      concentrated speech in specific scenes and recede; Praxagora
      speaks in only $7 / 40$ active segments (18%), Lysistrate in
      $26 / 67$ (39%).  Both types can produce comparable top-speaker
      shares (&sect;4), so tGini decomposes the share metric:
      <em>how</em> the lead built their share, not only how much.</p>
      <p class="note"><b>partOf sensitivity.</b>  The metric is
      computed on the (possibly partOf-aggregated) character set: under
      aggregation, the merged collective's vector is the sum of the
      members' per-segment vectors, and tGini is recomputed on the
      sum.  The aggregated chorus's tGini is therefore not a weighted
      average of the halves' &mdash; it can move in either direction,
      and the per-play dashboard's partOf toggle drives a full
      recompute of the speech-concentration table.</p>
      <p class="note"><b>Segmentation sensitivity.</b>  Finer
      segmentation produces longer vectors with more interleaved
      zeros, which generally raises tGini; coarser segmentation lumps
      speech together, which generally lowers it.  The metric is
      meaningful only within a chosen segmentation tab; cross-tab
      comparison is not sound.</p>
      <p class="note"><b>Display threshold (cosmetic, not
      methodological).</b>  The Speech-concentration table filters to
      characters with $\geq 5$ total verses to keep the long tail of
      bit parts from crowding the view.  The threshold is a
      visualisation filter only: each character's tGini is computed
      independently of every other character's, so changing the
      threshold cannot change any number in the table &mdash; only
      which rows are displayed.  The full per-character vector is
      always emitted to the JSON metrics file and to
      <code>characters.csv</code>.</p>
      <p class="ref"><b>DraCor:</b> not in <code>/metrics</code>.
      Original to this dashboard.  No external reference;
      mathematically a standard Gini on a different distribution
      vector.</p>
    </article>
  </section>

  <section class="methods-section">
    <h3>6. Reference shapes on the corpus charts</h3>

    <article class="metric">
      <h4>the "Plays included" selector &mdash; reference quantities are subset-relative</h4>
      <p>The corpus dashboard offers a chip-grid selector above the
      summary KPIs that includes / excludes individual plays from
      every panel at once.  Toggling a chip cascades through the KPI
      block, every scatter chart, the cast-composition bars, the beat
      multiples, the chorus beat chart, and the plays table.  Default
      state: all plays included.</p>
      <p>Methodologically the key point is that the chart's
      <em>reference shapes</em> &mdash; the iso-degree curve and every
      median crosshair &mdash; are <strong>corpus-aggregate quantities
      defined relative to the active selection</strong>, not absolute
      properties of "the corpus" in some objective sense.  When you
      deselect plays, the iso-curve recomputes against the new
      $k_{\mathrm{median}}$, the median crosshairs shift to the new
      $(x, y)$ medians, and the KPI ranges update.  A play that sits
      "above the iso-curve" in the full-corpus view may sit on or
      below it in a sub-corpus view, depending on which plays anchor
      the median.</p>
      <p>This is not a bug; it is the right behaviour.  A constructivist
      reading of corpus-aggregate quantities (Drucker; Escobar Varela)
      treats them as artefacts of the corpus boundary, not as discoveries
      about an independent reality.  The selector makes the boundary
      manipulable and therefore visible: the user sees Lysistrata's
      position shift as the reference corpus shifts under their hand.</p>
      <p class="ref"><b>Documentation in screenshots.</b>  When the
      selection is non-full, a chip in the header's active-filters
      strip displays <code>subset N / M plays</code>.  Any screenshot
      with that chip is self-documenting as to which subset produced
      it; without the chip, the screenshot is the full-corpus view.</p>
      <p class="note">Selection state is in-memory only and resets on
      page reload.  If you want a permanent sub-corpus, regenerate the
      dashboard with the corresponding paths
      (<code>python app.py corpus path1 path2 ...</code>) and use the
      <code>--name</code> option for a custom title.</p>
    </article>

    <article class="metric">
      <h4>tri-state chips: <em>anchor</em> vs <em>display-only</em></h4>
      <p>Clicking a chip cycles it through three states:</p>
      <ul>
        <li><b>off</b> &mdash; deselected.  The play is not visible on
        any chart and contributes nothing to the corpus aggregates.</li>
        <li><b>anchor</b> (anchor glyph $\unicode{x2693}$ shown on the
        chip).  The play is visible on every chart <em>and</em>
        contributes to the iso-curve $k_{\mathrm{median}}$, the median
        crosshairs, and the KPI ranges.  This is the default state for
        all chips on page load.</li>
        <li><b>display-only</b> (chip in italics, lighter background,
        anchor glyph hidden).  The play is visible on every chart but
        is <em>excluded</em> from the corpus aggregates.  Its scatter
        dot renders with reduced opacity ($0.55$) so the eye can
        distinguish display-only dots from anchor dots at a glance.</li>
      </ul>
      <p>The methodological motive: experimentally-rigged variants of
      one play (e.g.~<code>partOf</code>-collapsed versions of
      <em>Lysistrata</em>, ad-hoc transformations added to test a
      sensitivity hypothesis) are <strong>not independent observations
      of the corpus</strong>.  Including them in the median computation
      double-counts the original play's contribution and inflates the
      reference, which biases the apparent position of every play
      &mdash; including the very variant being compared.  The
      anchor / display-only distinction surfaces this constructivist
      point and lets the user separate <em>"which plays do I want to
      see on the chart"</em> from <em>"which plays should the corpus
      reference be computed against"</em>.</p>
      <p class="ref"><b>Documentation in screenshots.</b>  When the
      anchor set differs from the selected set, the active-filters
      strip adds a second chip: <code>anchors $K$ / $N$ selected</code>.
      Screenshots that omit this chip have anchor = selected; screenshots
      that show it document the exact reference-set choice.</p>
    </article>

    <article class="metric">
      <h4>per-play dot colours</h4>
      <p>Each chip carries a small colour dot to its left.  Clicking
      the colour dot cycles through a $7$-colour qualitative palette
      (accent blue $\to$ coral $\to$ green $\to$ magenta $\to$ orange
      $\to$ purple $\to$ dark grey $\to$ accent blue).  The chosen
      colour is the play's dot colour on every scatter chart, allowing
      the user to highlight one or several plays of interest against a
      common background &mdash; e.g.~recolouring Lysistrata and its
      rigged variants in coral to track their movement across the
      density &times; order, average degree &times; order, and Gini
      &times; share scatters as toggles are applied.</p>
      <p>Colour state is in-memory only.  A <em>reset colours</em>
      button in the selector toolbar restores all chips to the default
      palette index $0$.</p>
      <p class="ref">Colour is purely a presentation aid; it carries
      no analytical meaning beyond what the user chooses to encode by
      assignment.  Tooltips and axis values are unaffected.</p>
    </article>

    <article class="metric">
      <h4>median crosshair</h4>
      <p>Vertical dashed line at $x = \mathrm{median}(x_i)$ and horizontal
      at $y = \mathrm{median}(y_i)$.  A descriptive anchor, not a
      regression line.</p>
      <p class="ref">Original to this dashboard.  Computed over the
      currently-selected subset of plays (see the selector entry above).</p>
    </article>

    <article class="metric">
      <h4>iso-degree curve (density &times; order only)</h4>
      <p>$$d = \frac{k}{n - 1}, \qquad
         k = \mathrm{median}_p \langle k \rangle_p$$</p>
      <p>The locus of "where would density fall for a given $n$, if every
      play had the corpus median average degree".  Plays above the curve
      are denser than the saturation hypothesis predicts; plays below,
      sparser.  Undefined when $n \le k + 1$ (would require $d > 1$);
      dots in that domain are drawn as hollow rings, with a tooltip note.</p>
      <p class="ref">Original to this dashboard.  The mathematical
      relation $d = k / (n - 1)$ is exact for any undirected graph &mdash;
      the curve is the trace of that identity at fixed $k$.  The
      <em>empirical</em> assumption that $\langle k \rangle$ is
      roughly constant across plays is supported by Stiller, Nettle &amp;
      Dunbar (2003) for Shakespeare and Trilcke et al. (2016/2017) for
      German drama.</p>
    </article>

    <article class="metric">
      <h4>pair-lines (density &times; order only)</h4>
      <p>Thin red segments connecting every pair of plays with order
      difference $\Delta n \le 5$.  Each segment's vertical span is the
      pairwise density difference between the two plays.  The tooltip
      reports the two plays' coordinates and the symmetric density
      excess $\max(d_P, d_Q) / \min(d_P, d_Q) - 1$.</p>
      <p>The methodological motive is to complement the iso-curve with
      a <em>model-free</em> measure of corpus deviation.  The iso-curve
      assumes the empirical regularity that $\langle k \rangle$ is
      approximately constant across the corpus; the pair-lines assume
      nothing &mdash; they simply show, for each region of $n$, how much
      density variation exists locally among plays of similar order.</p>
      <p>Two readings emerge from the visual pattern:</p>
      <ul>
        <li><b>Short lines in a cluster</b> &mdash; a region of $n$
        where the local pairwise variation is small.  The Aristophanic
        corpus has three such clusters: around $n \approx 17$
        (Plutus / Clouds / Thesmoph.), $n \approx 23$–$26$
        (Ecclesiazusae / Wasps / Frogs / Peace), and $n \approx 38$–$42$
        (Birds / Acharnians).  In each, pairwise density differences sit
        in the range $\sim 7$–$38\%$, with a median around $12\%$.</li>
        <li><b>Tall lines incident on a single play</b> &mdash; a play
        whose density does not match its nearest-order neighbours.  In
        the Aristophanic corpus, the only such play is
        <em>Lysistrata</em>: its incident lines (to Birds, to
        Acharnians) span density differences of $\approx 80\%$ and
        $\approx 92\%$, an order of magnitude above the local
        $\sim 7\%$ pairwise difference between its two neighbours.</li>
      </ul>
      <p>The reading is therefore symmetric with, and independent of,
      the iso-curve reading: the iso-curve says Lysistrata sits
      $\sim 94\%$ above the corpus-median curve; the pair-lines say
      Lysistrata sits $\sim 80\%$ above its nearest-order neighbours,
      with the natural pairwise density variation at that order being
      $\sim 7\%$.  Two independent diagnostics, the same conclusion.</p>
      <p class="ref"><b>Toggle.</b>  A checkbox in the chart header
      controls visibility (default on).  Switching off lets the iso-curve
      reading stand alone; switching on overlays the model-free reading
      on top.</p>
      <p class="ref">Original to this dashboard.  No reference threshold
      is theoretically required; $\Delta n \le 5$ is the working choice
      that captures every cluster of similar-order plays in the
      Aristophanic corpus without spurious cross-cluster connections.</p>
    </article>

    <article class="metric">
      <h4>Gini &times; average degree (speech inequality &times; network density)</h4>
      <p>The two axes encode independent dimensions: Gini of per-character
      verse counts records how unequally <em>speech</em> is distributed
      across the cast; average degree records how densely connected the
      <em>network</em> is on average.  Plotted together they let four
      dramaturgical configurations be read off the corpus scatter:</p>
      <table style="font-size: 12.5px; border-collapse: collapse; margin: 8px 0;">
        <tr><th style="text-align: left; padding-right: 16px;"></th>
            <th style="text-align: left; padding-right: 16px;">low Gini</th>
            <th style="text-align: left;">high Gini</th></tr>
        <tr><td><i>high avg-deg</i></td>
            <td><b>ensemble play</b> &mdash; speech and connections both spread broadly</td>
            <td><b>star-topology play</b> &mdash; a few dominant speakers also serve as connective hubs</td></tr>
        <tr><td><i>low avg-deg</i></td>
            <td>rare &mdash; distributed speech in a loosely-connected cast</td>
            <td><b>long-tail play</b> &mdash; a few speakers carry most verses; the rest sit on the periphery</td></tr>
      </table>
      <p>The chart responds to the network-model radio through the
      <code>averageDegree</code> axis (the Gini axis is computed on the
      full speech corpus and does not move).  The methodological reading
      is: the same dramatic inequality on speech, viewed against three
      different networks.  Under <em>stage co-presence</em> the cast is
      the full appearing cast and the staging-density inflation pushes
      avg-deg high; under <em>dialogic cast on play level</em> pure
      mutes are removed but stage co-presence among speakers still
      contributes edges (intermediate avg-deg); under <em>dialogic cast
      on segment level</em> only per-segment speakers are counted
      (avg-deg reflects co-speech only).  The same plays shift along
      the y-axis between the three readings; their positions on the
      x-axis stay fixed.</p>
      <p class="ref">Original to this dashboard.  No reference curve is
      drawn (no theoretical relationship binds Gini to avg-deg the way
      $d = k/(n-1)$ binds density to order); median crosshairs anchor the
      four quadrants descriptively.  $N = 11$ plays in the Aristophanic
      corpus, so the scatter is suited to identifying clusters and
      outliers, not to regression or significance claims.</p>
    </article>

    <article class="metric">
      <h4>top-speaker share &times; Gini (lead dominance &times; full-distribution inequality)</h4>
      <p>Both axes are speech-corpus metrics &mdash; they index the
      <em>verse-count</em> distribution across the cast and do not
      depend on the network model.  The chart is therefore invariant
      across all three network-model radio choices: only the
      network-based charts shift when the model changes.</p>
      <p>The two axes are deliberately partial views of the same
      distribution.  Top-speaker share is a single-point summary
      &mdash; it records what fraction of the play's verses the most
      voluble character speaks, and nothing about the rest.  Gini is
      a global inequality measure &mdash; it integrates the entire
      verse distribution into one number.  When the two diverge, the
      dramaturgical signal is in <em>how</em> they diverge:</p>
      <table style="font-size: 12.5px; border-collapse: collapse; margin: 8px 0;">
        <tr><th style="text-align: left; padding-right: 16px;"></th>
            <th style="text-align: left; padding-right: 16px;">low Gini</th>
            <th style="text-align: left;">high Gini</th></tr>
        <tr><td><i>high share</i></td>
            <td>rare &mdash; a dominant lead in an otherwise flat
            distribution (would require the rest of the cast to be
            near-uniform)</td>
            <td><b>star-vehicle play</b> &mdash; one figure carries
            the verse count and everyone else falls off steeply;
            classic Old-Comedy single-hero pattern</td></tr>
        <tr><td><i>low share</i></td>
            <td><b>ensemble play</b> &mdash; no dominant lead and a
            broadly distributed supporting cast</td>
            <td><b>coalitional-protagonist play</b> &mdash; the lead
            does not crush, but behind the lead the distribution
            drops steeply; a head-of-coalition pattern rather than a
            sole-hero pattern</td></tr>
      </table>
      <p>The chart sharpens a reading that neither axis can produce
      alone.  A protagonist who is "not dominant" (low share) might
      sit in a genuinely democratic distribution (low Gini) or at the
      top of a steep one (high Gini); the corpus scatter resolves the
      ambiguity by quadrant.</p>
      <p class="note"><b>partOf sensitivity.</b>  By default the metric
      is computed on the raw, non-aggregated speaker set: split
      semichoruses count as separate speakers.  Under
      <code>partOf</code> aggregation the merged chorus may absorb
      enough verses to overtake the eponymous lead (e.g. in
      <em>Lysistrata</em>, the aggregated <code>choros</code> would
      come within ~15 verses of <code>lysistrate</code>), which would
      reposition the play on both axes.  The global
      <b>aggregate chorus halves</b> toggle (&sect;7) now drives this
      chart too: under aggregation the play's speech distribution is
      recomputed over the merged speaker set, so the dot moves to its
      aggregated position.  Toggling it is the proper stress-test for
      any reading built on a <code>partOf</code>-fragmented corpus
      play.</p>
      <p class="ref">Original to this dashboard.  As with Gini &times;
      avg-deg, no reference curve is appropriate &mdash; the two axes
      are nonlinearly related (high share <em>requires</em> at least
      moderate Gini, since the top alone has share $s$, but Gini can
      be high at any share) and the relationship is not a clean
      identity.  Median crosshairs anchor the four quadrants
      descriptively.</p>
    </article>

    <article class="metric">
      <h4>top-speaker share &times; average degree (lead dominance &times; network density)</h4>
      <p>The third of three pairwise scatter plots over the metrics
      $\{\text{share}, \text{Gini}, \langle k \rangle\}$.  The Gini &times;
      avg-deg and share &times; Gini charts hold one of these three
      constant per chart; this chart fixes the remaining pair.  It is
      <em>not</em> derivable from the other two: knowing
      $(\text{share}, \text{Gini})$ and $(\text{Gini}, \langle k \rangle)$
      for each play does not fix $(\text{share}, \langle k \rangle)$
      &mdash; the projections genuinely differ.</p>
      <p>The chart asks a single methodologically rich question:
      <em>do plays with a dominant single protagonist also have dense
      networks, or sparse ones?</em>  The four quadrants:</p>
      <table style="font-size: 12.5px; border-collapse: collapse; margin: 8px 0;">
        <tr><th style="text-align: left; padding-right: 16px;"></th>
            <th style="text-align: left; padding-right: 16px;">low avg-deg</th>
            <th style="text-align: left;">high avg-deg</th></tr>
        <tr><td><i>high share</i></td>
            <td><b>sparse single-hero</b> &mdash; dominant lead on a
            loosely connected cast (classic Old-Comedy single-hero
            pattern: Acharnians, Peace, Clouds)</td>
            <td>rare under <i>dialogic on segment level</i>; possible
            under <i>stage co-presence</i> when staging density is high
            alongside a dominant lead</td></tr>
        <tr><td><i>low share</i></td>
            <td><b>distributed sparse</b> &mdash; no dominant lead,
            loosely connected (Ecclesiazusae, Plutus, Knights)</td>
            <td><b>coalitional dense</b> &mdash; no dominant lead but
            high stage co-presence; <em>Lysistrata</em> sits here
            under <i>stage co-presence</i> (avg-deg $14.65$, share
            $0.289$), driven by the women's mass occupation of the
            Acropolis and the split-semichorus interactions</td></tr>
      </table>
      <p>The chart is therefore the place where the
      <b>three-model methodology</b> becomes visually legible on a
      single scatter.  Under <i>stage co-presence</i>,
      <em>Lysistrata</em> is a far outlier on the y-axis (avg-deg
      $\approx 14.65$); under <i>dialogic cast on play level</i>
      (drop pure mutes, keep stage-presence edges) the play moves
      partway back toward the cluster (avg-deg $\approx 9.83$);
      under <i>dialogic cast on segment level</i> the staging-density
      artefact fully dissolves and avg-deg drops to $\approx 4.61$,
      placing the play near the corpus median.  The two-step descent
      decomposes the original anomaly: of the $14.65 - 4.61 \approx 10$
      units of inflation, roughly half is attributable to pure mute
      characters (archers, attendants, silent crowds) and roughly half
      to silent stage co-presence among dialogic agents (the women's
      collective occupation, the chorus halves as silent witnesses).
      A direct visual demonstration that the play's "anomalous density"
      is largely a property of the chosen network model, with both
      mute presence <em>and</em> silent-but-dialogic presence
      contributing.</p>
      <p class="ref"><b>Network-model response.</b>  The avg-deg axis
      shifts with the radio (same as on Gini &times; avg-deg); the
      share axis stays fixed (share is a speech-corpus property
      independent of the network model).  Plays move along the
      y-axis only.</p>
      <p class="ref">Original to this dashboard.  No reference curve
      (no theoretical relationship binds share to avg-deg); median
      crosshairs anchor the four quadrants descriptively.</p>
    </article>
  </section>

  <section class="methods-section">
    <h3>7. Cast transformations &mdash; <i>partOf</i> aggregation</h3>

    <article class="metric">
      <h4>aggregate <i>partOf</i></h4>
      <p>The Analysis toolbar shows one checkbox per distinct group
      (<code>passive</code> id) declared in <code>&lt;listRelation&gt;</code>.
      When a group $Y$ is checked, every character $X$ with
      <code>&lt;relation name="partOf" active="#X" passive="#Y"&gt;</code>
      is rewritten to $Y$ throughout the play data: in
      <code>&lt;sp who="..."&gt;</code> attributions, in
      <code>&lt;move&gt;</code> <code>@who</code> / <code>@corresp</code>,
      and in the cast list (members are dropped; $Y$ absorbs their chorus
      / speaker flags; the behavioural mute rule is re-evaluated on the
      rewritten speeches).  Other groups not currently checked stay
      disaggregated.  Segmentation, graph construction, and metric
      computation then run unchanged on the resulting character set.</p>
      <p class="ref"><b>Edge merge rule.</b>  None applied explicitly:
      the graph builder counts segments in which two characters are
      co-present, so the multiplicity sums by construction.  A segment
      that previously yielded $X\!-\!C$ and $Y\!-\!C$ with $X, Y$ both
      <i>partOf</i> $G$ contributes a single $G\!-\!C$ edge with the
      summed weight.</p>
      <p class="ref"><b>Split/merge moves.</b>  A <code>&lt;move
      type="split"&gt;</code> like <code>@who="#choros"
      @corresp="#chorosAndron #chorosGynaikon"</code> becomes, post-rewrite,
      $\{\text{choros}\} \to \{\text{choros}\}$ &mdash; a no-op for the
      stage-state machine.  This is the correct semantics: under
      aggregation the chorus does not visibly split.</p>
      <p class="ref"><b>partOf relations in this play.</b>
      <span id="aggregation-relations">&mdash;</span></p>
      <p class="note">The toggle is hidden when the play has no
      <code>&lt;listRelation&gt;</code> partOf entries.  The choice is a
      methodological commitment, not a "neutral" data-cleanup: both the
      raw and the aggregated network are legitimate readings, distinguished
      by what counts as a single dramaturgical agent.  Compare the two to
      see how much of the topology depends on that choice.</p>
    </article>
  </section>

  <section class="methods-section">
    <h3>8. Visualisation encodings &mdash; what node size means</h3>

    <article class="metric">
      <h4>static graph &mdash; node size &propto; degree</h4>
      <p>$$r = 3 + \sqrt{\deg(v)} \cdot 2.8$$</p>
      <p>Radius scales with the square root of unweighted degree, so
      <em>area</em> scales roughly linearly with the number of
      neighbours.  The multiplier (2.8) is chosen to keep degree-30 hubs
      clearly distinct from degree-0 isolates without dominating the
      layout.  Tooltip on each node carries the exact degree, weighted
      degree, betweenness, closeness, and eigenvector.</p>
      <p class="ref">A play-level reading: the size advertises
      <em>aggregate centrality across the entire play</em>, not what is
      happening in any one segment.</p>
    </article>

    <article class="metric">
      <h4>dynamic graph &mdash; node size depends on the frame</h4>
      <p>The dynamic-graph panel has two states:</p>
      <p><b>(a) Static-aggregate frame</b> (segment slider at $-1$).
      Same encoding as the static graph above &mdash;
      $r = 3 + \sqrt{\deg(v)} \cdot 2.8$ &mdash; so the overview view of
      the dynamic panel matches the larger static graph visually.</p>
      <p><b>(b) Per-segment frame</b> (any specific segment selected).
      Size encodes the <em>per-segment word count</em> attributed to the
      character in that segment, log-compressed:</p>
      <p>$$r = 3 + \log_2 \! \bigl(1 + \mathit{words}_v(S_i)\bigr) \cdot 1.5$$</p>
      <p>where $\mathit{words}_v(S_i)$ is the sum of <code>word_count</code>
      over speeches in segment $S_i$ with $v \in$ <code>@who</code>.
      Joint speeches (a single <code>&lt;sp who="#a #b"&gt;</code>) credit
      the full word count to each speaker, matching the convention used by
      the behavioural mute rule.  Log compression gives moderate
      visibility to differences across the typical Aristophanic range
      (single-digit interjections to 700-word rheseis).</p>
      <p class="ref"><b>Why two encodings.</b>  Per-segment degree on the
      dynamic graph would be uninformative: each segment's edge set is a
      complete graph on its co-active cast by construction, so every
      visible node has the same degree.  Per-segment <em>words</em> is
      the natural per-character, per-segment quantity that captures
      "who is carrying the speech in this scene" &mdash; a real time-varying
      signal the static view cannot show.  The two encodings are
      deliberately different because the two graphs answer different
      questions.</p>
      <p class="note">Hover tooltip on any node in a per-segment frame
      reports its word count in that segment, so the encoding is
      verifiable without inferring from the visual.</p>
    </article>
  </section>

  <section class="methods-section">
    <h3>9. Annotation schema for <code>&lt;move&gt;</code></h3>

    <article class="metric">
      <h4>controlled vocabulary for <code>@type</code> and <code>@ana</code></h4>
      <p>The corpus annotates stage events as <code>&lt;move&gt;</code>
      elements.  The annotation guide fixes a closed vocabulary on two
      attributes:</p>

      <p><b>@type</b> — one of six values:</p>
      <ul>
        <li><code>entrance</code> — character arrives on stage</li>
        <li><code>exit</code> — character leaves the stage</li>
        <li><code>onStage</code> — state assertion at a non-transition
        moment (opening / closing tableaux; empty <code>@who</code>
        marks an empty stage)</li>
        <li><code>state-change</code> — character transitions to a new
        perception / visibility / vitality / participation state
        without entering or leaving</li>
        <li><code>merge</code> — split parts re-unify (e.g. semichoruses
        become a single chorus)</li>
        <li><code>split</code> — a unified collective divides into parts</li>
      </ul>

      <p><b>@ana</b> — space-separated <code>#</code>-references into
      the <code>move-subtype</code> taxonomy declared in the TEI header.
      Tokens are drawn from six orthogonal axes, one token per axis;
      e.g. <code>ana="#withdrawn #unaware"</code> records two
      simultaneous axis transitions on the same dramatic beat.</p>
      <table style="font-size: 12.5px; border-collapse: collapse;">
        <tr><th style="text-align: left; padding-right: 16px;">axis</th>
            <th style="text-align: left; padding-right: 16px;">tokens</th>
            <th style="text-align: left;">default</th></tr>
        <tr><td><i>location</i></td>
            <td><code>stage</code> · <code>voice-only</code></td>
            <td><code>stage</code></td></tr>
        <tr><td><i>visibility</i></td>
            <td><code>unhidden</code> · <code>hidden</code></td>
            <td><code>unhidden</code></td></tr>
        <tr><td><i>capacity</i></td>
            <td><code>awake</code> · <code>asleep</code></td>
            <td><code>awake</code></td></tr>
        <tr><td><i>vitality</i></td>
            <td><code>alive</code> · <code>dead</code></td>
            <td><code>alive</code></td></tr>
        <tr><td><i>engagement</i></td>
            <td><code>aware</code> · <code>unaware</code></td>
            <td><code>aware</code></td></tr>
        <tr><td><i>participation</i></td>
            <td><code>engaged</code> · <code>withdrawn</code></td>
            <td><code>engaged</code></td></tr>
      </table>
      <p>The <i>engagement</i> and <i>participation</i> axes are genuinely
      independent: <i>engagement</i> records whether the character
      <em>perceives</em> the action (aware = perceiving, unaware = not
      perceiving), <i>participation</i> records whether the character
      <em>takes part in</em> the action (engaged = in the action,
      withdrawn = stepped aside).  Most combinations are dramaturgically
      meaningful — a withdrawn character may still be aware (a silent
      witness), and an engaged character may be unaware (deceived or
      distracted within the action).</p>

      <p><b>@ana rules per @type:</b></p>
      <ul>
        <li><code>entrance</code>, <code>onStage</code> — <code>@ana</code>
        optional.  When omitted, default is
        <code>"#stage #unhidden #awake #alive #aware #engaged"</code>.
        Specify only the tokens that deviate from default.</li>
        <li><code>state-change</code> — <code>@ana</code> required
        (otherwise the move has no effect).</li>
        <li><code>exit</code> — <code>@ana</code> <b>forbidden</b>.  The
        character's exit state is inherited from their most recent
        prior <code>entrance</code> / <code>state-change</code> /
        <code>onStage</code>.</li>
        <li><code>merge</code>, <code>split</code> — <code>@ana</code>
        not used.  Parts inherit their state from prior moves; the
        unified collective's state defaults.</li>
      </ul>
      <p class="note">Legacy: a previous convention used
      <code>@subtype</code> with bare (non-prefixed) tokens.  The parser
      still reads <code>@subtype</code> with a deprecation warning so
      partially-migrated files keep loading; once every TEI file has
      been converted to <code>@ana</code> the fallback can be removed.</p>
    </article>

    <article class="metric">
      <h4>segmentation triggers (stage-direction segmenter)</h4>
      <p>A new <code>sd</code> segment is opened when any of the
      following structural moves is encountered:</p>
      <ul>
        <li><code>&lt;move type="entrance"&gt;</code></li>
        <li><code>&lt;move type="exit"&gt;</code></li>
        <li><code>&lt;move type="onStage"&gt;</code></li>
        <li><code>&lt;move type="merge"&gt;</code></li>
        <li><code>&lt;move type="split"&gt;</code></li>
      </ul>
      <p>These are exactly the moves that change <em>who</em> is on
      stage.  In contrast, <code>state-change</code> moves apply their
      perception / visibility / vitality effect but do <em>not</em>
      trigger a segment boundary &mdash; the segment "spans" them.  This
      keeps a voice-only interjection followed by a normal entrance
      (now encoded as <code>entrance subtype="voice-only"</code> +
      later <code>state-change subtype="stage"</code>) in a single
      dramaturgical unit alongside the dialogic exchange it belongs to,
      rather than fragmenting it into three short and mostly-empty
      segments.</p>
      <p><b>Model-specific spine.</b>  The triggers above define the
      <em>stage</em> spine, in which every entrance / exit cuts a segment.
      Under the two mutes-out models the spine is recomputed: adjacent
      <code>sd</code> segments whose cast is identical <em>under the active
      model</em> are folded into one, because a boundary triggered solely
      by a non-node &mdash; a mute's entrance under the dialogic model, or
      a move that does not change who is currently speaking under
      co-speech &mdash; is invisible to that model.  A character that does
      not exist in the network cannot structure its time.  The fold is
      provably <em>topology-preserving</em>: the merged segment re-emits
      the identical co-presence / co-speech clique, so order, size,
      density, average degree, clustering and diameter are unchanged; only
      the segment count, the drama-change rate (&sect;4), the segment
      indices and the beat / heatmap binning move.  In the Aristophanic
      corpus the dialogic fold removes 1&ndash;15 boundaries per play
      (<em>Lysistrata</em> and <em>Birds</em>: 15 each &mdash; the silent
      supernumeraries), so e.g. <em>Lysistrata</em> reads as 67 stage
      segments but ~52 dialogic ones.  This applies to the <code>sd</code>
      spine only: <code>div2</code> / <code>div3</code> are textual
      divisions, not cast-triggered boundaries, so their count stays fixed
      and model-independent (and DraCor-comparable).  Consequence: segment
      <em>k</em> is not the same moment across models, so cross-model
      comparison is by shape / normalised position, not aligned index.</p>
      <p class="ref"><b>Parser is permissive.</b>  Files written in the
      previous annotation convention (e.g. <code>exit</code> with
      <code>@subtype</code>, or <code>@subtype</code> values not in the
      controlled vocabulary) are still processed.  Each schema
      violation is logged as a WARNING but never raises &mdash; this
      allows the corpus to be migrated to the new schema incrementally
      without breaking the dashboard pipeline mid-migration.</p>
    </article>
  </section>

  <section class="methods-section">
    <h3>10. Character &times; segment heatmap</h3>

    <article class="metric">
      <h4>matrix view: who is doing what across all segments</h4>
      <p>A matrix with one row per character (rows = visible cast,
      filtered by the network-model radio) and one column per segment.
      Each cell encodes three possible states:</p>
      <ul>
        <li><b>transparent</b> &mdash; character is not in
        <code>characters_present</code> for this segment (off-stage,
        or for play-level mute characters under either dialogic-cast
        model, excluded);</li>
        <li><b>light grey</b> &mdash; character is present in the
        segment but contributes no non-empty <code>&lt;l&gt;</code>
        ("present but silent");</li>
        <li><b>white &rarr; red ramp</b> &mdash; character is speaking;
        intensity is proportional to the per-segment verse count
        $\mathit{verses}_v(S_i)$, normalised against the max
        per-cell verse count in the visible matrix.  Saturated red
        marks the loudest cell in the play.</li>
      </ul>
      <p>The colour ramp is the standard sequential reds (Brewer
      <code>Reds</code> palette family), chosen for legibility against
      the light-grey "present but silent" state.</p>
    </article>

    <article class="metric">
      <h4>row order</h4>
      <p>The "row order" dropdown above the heatmap offers three modes:</p>
      <ul>
        <li><b>loudest first</b> (default) &mdash; characters sorted
        by total verses across the play, descending.  Mute characters
        (zero total verses) land at the bottom as a uniform grey-only
        band, which makes the speakers/silents stratification visible
        at a glance.</li>
        <li><b>appearance order</b> &mdash; sorted by the earliest
        segment id where the character is in
        <code>characters_present</code>.  Reads the play's "introduction
        rhythm" &mdash; how quickly the cast accumulates.</li>
        <li><b>alphabetical</b> &mdash; by display name.  Useful for
        looking up a specific character.</li>
      </ul>
    </article>

    <article class="metric">
      <h4>interaction</h4>
      <p>Click any cell to set the dynamic graph's current segment to
      the column's segment id &mdash; the dynamic graph, the segments
      table, the segment timeline, and the heatmap's own
      current-segment outline all update in sync.  Hover any cell for a
      tooltip with character name, segment id and label, and per-segment
      verse count (or "absent" / "present (silent)" status).</p>
      <p class="ref"><b>Network-model response.</b>  Under
      <em>stage co-presence</em> the matrix includes every appearing
      character (cat 1 + 2 + 3); mute characters appear as rows full
      of transparent and light-grey cells, showing pure stage presence
      without speech.  Under either of the <em>dialogic-cast</em>
      models the cat-2 mute rows disappear entirely and the red-ramp
      is renormalised against the remaining (cat 1 + 3) maximum.  The
      two dialogic-cast modes produce the same matrix (the cast filter
      is the same; only the edge rule on the network charts differs),
      so the heatmap toggles between two distinct visual states across
      the three radio options.  The gap between the stage and dialogic
      views is exactly the "how much of the play is silent stage
      presence by pure mutes?" question at character granularity.</p>
    </article>
  </section>

  <section class="methods-section">
    <h3>11. Chorus presence beat chart (corpus dashboard)</h3>

    <article class="metric">
      <h4>matrix view: chorus participation across the corpus</h4>
      <p>One row per chorus character, one cell per segment in that
      chorus's own play.  Three states, identical to the per-play
      character &times; segment heatmap (&sect;10):</p>
      <ul>
        <li><b>transparent (over a thin grey baseline)</b> &mdash;
        chorus is not in <code>characters_present</code> for that
        segment;</li>
        <li><b>light grey</b> &mdash; chorus is on stage but utters no
        non-empty <code>&lt;l&gt;</code> in the segment ("present but
        silent");</li>
        <li><b>red ramp</b> &mdash; chorus speaks; saturation
        $\propto \sqrt{\mathit{verses}_v(S_i)}$, normalised against the
        maximum verse count seen across all visible rows in the chart
        (not per row), so a cell's intensity is directly comparable
        across plays.</li>
      </ul>
      <p class="note">Each row carries a thin horizontal baseline
      spanning the full cell area, so that a chorus absent in the
      opening or closing segments does not visually truncate the row.
      Without it, a chorus that exits before the final segment would
      conflate with "row ends here"; with the baseline visible, the
      row's full extent is unambiguous and only the cell density
      varies.</p>
    </article>

    <article class="metric">
      <h4>x-axis normalisation</h4>
      <p>Each row's segment array is stretched to the full chart width,
      so the x-axis encodes <em>play progress in $[0, 1]$</em> rather
      than absolute segment count.  This makes the distribution
      <i>shape</i> &mdash; "front-loaded chorus", "back-loaded chorus",
      "evenly spaced", "exclusively in the parabasis" &mdash; comparable
      across plays of different lengths.  The trade-off is that a single
      cell does not represent the same dramaturgical quantity in two
      plays of different segment count: a cell is "$1/N_p$ of play $p$",
      not "one event".  This is the correct trade-off for
      <em>shape comparison</em>; absolute beat data is available on the
      per-play dashboards (&sect;10).</p>
    </article>

    <article class="metric">
      <h4>row sort &mdash; genre, then author, then title, then chorus name</h4>
      <p>Rows are grouped first by <em>genre</em> (heuristic from author
      name: Aristophanes / Menander / Plautus / Terence &rarr; comedy;
      Aeschylus / Sophocles / Euripides / Seneca &rarr; tragedy; other
      &rarr; other), then by <em>author</em>, then by play
      <em>title</em>, then by chorus <em>name</em> for plays with
      multiple choruses.  A subtle grey band shades alternating
      (genre, author) groups behind the rows so sub-corpora read as
      contiguous blocks.</p>
      <p class="note">The genre heuristic is a stand-in for a TEI
      <code>&lt;classCode scheme="#genre"&gt;</code> element until the
      corpus annotates genre explicitly.  Any expansion to comedies of
      Menander, Plautus, or to the tragic corpus will pick up the
      author-name match without code changes; unknown authors fall into
      <em>other</em>, sorted after both canonical buckets.</p>
    </article>

    <article class="metric">
      <h4>toggle response</h4>
      <p>Three toggles modulate the chart:</p>
      <ul>
        <li><b>Segmentation tab</b> (sd / div2 / div3).  Same data
        source, different cell granularity.  The number of cells in a
        given chorus row scales with the segmentation choice.</li>
        <li><b>Network model</b> (corpus-wide radio in the header).
        Switches between the three <em>variants</em> of the underlying
        play data &mdash; this affects the chorus row only when a chorus
        character has <code>word_count = 0</code> across the entire
        play (rare; sporadically a partial chorus or a noted-but-silent
        group).  Under either of the two dialogic-cast modes, such rows
        disappear from the chart.  The two dialogic-cast modes produce
        identical chorus rows (the chart shows verses; the model only
        controls cast filtering and edge rules, both irrelevant to
        per-chorus per-segment verse counts).</li>
        <li><b>Aggregate chorus halves</b> (global toggle in the
        seg-tabs strip, beside the network-model selector).  When
        checked, every chorus character that is the <code>active</code>
        in a <code>&lt;relation name="partOf"&gt;</code> is collapsed
        into its <code>passive</code> group.  In the Aristophanic corpus
        this primarily affects <em>Lysistrata</em>'s split semichoruses
        (<code>chorosAndron</code> + <code>chorosGynaikon</code>
        &rarr; <code>choros</code>): in the heat-map two rows become one,
        with the verses of both halves summed per segment.  Plays
        without partOf relations are unaffected.  The toggle is now
        <em>global</em>: it routes through <code>segOf</code>, so the
        collapse propagates to every panel at once &mdash; the
        density&nbsp;&times;&nbsp;order scatter (one fewer node lowers
        the order and raises the density, shifting the play along and
        above the iso-curve), the average-degree and topology scatters,
        the cast-composition bars, the speech-distribution charts (the
        merged chorus's verses sum into one speaker, changing Gini and
        top-speaker share), the DCR (a semichorus-A&rarr;semichorus-B
        exchange no longer registers as a cast change), the KPI ranges
        and the plays table.  The aggregated metrics are precomputed per
        play (one variant per <code>partOf</code> subset), so the toggle
        is a view swap, not a recomputation.  The one quantity that does
        <em>not</em> move with the toggle is the <code>col/spk</code>
        ratio in the plays table, which is computed against the
        fully-aggregated demographics by design (&sect;3) so that each
        chorus counts once in every view.</li>
      </ul>
    </article>

    <article class="metric">
      <h4>interpretation</h4>
      <p>The chart answers a specific comparative question:
      <em>how does chorus participation distribute across the play, and
      do plays in the same genre / by the same poet share a
      profile?</em>  Patterns to look for:</p>
      <ul>
        <li><b>Front-loaded shapes</b> &mdash; chorus dense at $x &lt; 0.5$,
        fading thereafter (the chorus carries the parodos but recedes
        as the agon between individuals takes over).</li>
        <li><b>Evenly-spaced shapes</b> &mdash; the chorus interleaves
        regularly with the individual episodes throughout.</li>
        <li><b>Parabasis-centred shapes</b> &mdash; a concentrated
        red block near $x \approx 0.5$ where Old Comedy locates its
        author-address.</li>
        <li><b>Silent-presence gaps</b> &mdash; long grey stretches
        signal a chorus that stays on stage as silent witness
        between contributions, distinct from a chorus that leaves
        and re-enters.</li>
      </ul>
      <p class="ref">Original to this dashboard.  Compare with the
      per-play heatmap (&sect;10), which gives the absolute per-segment
      verse counts for every character including the chorus, on the
      play's own segmentation grid.  This chart is the cross-play view
      of the chorus row of that heatmap.</p>
    </article>
  </section>

  <section class="methods-section">
    <h3>References</h3>
    <ul class="biblio">
      <li>Fischer, F., Göbel, M., Kampkaspar, D., Kittel, C. &amp; Trilcke, P.
        (2017).  <em>Network Dynamics, Plot Analysis. Approaching the
        Progressive Structuration of Literary Texts</em>.  DH 2017
        Montréal.
        [<a href="https://dh2017.adho.org/abstracts/071/071.pdf">PDF</a>]</li>
      <li>Trilcke, P., Fischer, F., Göbel, M., Kampkaspar, D. &amp;
        Kittel, C. (2016).  <em>Theatre Plays as &lsquo;Small Worlds&rsquo;?
        Network Data on the History and Typology of German Drama,
        1730&ndash;1930</em>.  DH 2016 Krak&oacute;w.</li>
      <li>Stiller, J., Nettle, D. &amp; Dunbar, R. I. M. (2003).
        <em>The Small World of Shakespeare's Plays</em>.  Human Nature 14,
        397&ndash;408.</li>
      <li>Jockers, M. L. (2013).  <em>Macroanalysis: Digital Methods and
        Literary History</em>.  Univ. of Illinois Press.</li>
      <li>DraCor API documentation:
        <a href="https://dracor.org/doc/api">dracor.org/doc/api</a>.</li>
      <li>DraCor frontend, beat-chart issue #65:
        <a href="https://github.com/dracor-org/dracor-frontend/issues/65">github.com/dracor-org/dracor-frontend/issues/65</a>.</li>
    </ul>
  </section>
</div>
"""


__all__ = ["methods_panel_html"]
