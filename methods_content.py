"""Methods reference panel shared by the per-play and corpus dashboards.

Returns a self-contained HTML fragment with the formulas for every metric
the app computes, rendered via KaTeX.

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
    How every graph and every value in the dashboard is computed.  Each value
    is exact for the configuration selected &mdash; segmentation tab, network
    model, aggregation state &mdash; and changes with it.  Exported figures and
    tables record the configuration that produced them.
  </p>
  <p>Notation: $G = (V, E)$ is the undirected graph of the active
  configuration; $N$ the number of segments of the active segmentation; $S_i$
  the cast of segment $i$ under the active network model.</p>

  <article class="metric" style="background: #fbf8ec; border-left: 3px solid #d6c87a; padding: 8px 12px; margin-bottom: 18px;">
    <h4>Graph construction</h4>
    <p>Nodes are characters.  An edge joins two characters who belong to the
    same segment's cast.  Edges are undirected and record co-occurrence only:
    addressee annotation (<code>@toWhom</code>) is parsed but not used.</p>
    <ol>
      <li>The play is cut into segments by the active segmentation.</li>
      <li>Each segment's cast $S_i$ is taken under the active network
      model.</li>
      <li>Each cast is joined into a clique; $G$ is the union of the cliques.
      Excepted is the pair of a collective and a character declared
      <code>partOf</code> it (a chorus and its half-choruses): they can share
      the cast of a large or middle sequence that contains a split or a merge,
      and are not joined.</li>
    </ol>
    <p><b>Segmentation</b> (tabs):</p>
    <ul>
      <li><b>stage directions</b> (<code>sd</code>) &mdash; a segment opens at
      each $\langle\mathrm{stage}\rangle$ containing a move that changes who is
      on stage: <code>entrance</code>, <code>exit</code>,
      <code>onStage</code>, <code>merge</code>, <code>split</code>
      (&sect;9).</li>
      <li><b>large sequences</b> &mdash; one segment per
      <code>&lt;milestone unit="large-seq"/&gt;</code> (act level).</li>
      <li><b>middle sequences</b> &mdash; one segment per
      <code>&lt;milestone unit="middle-seq"/&gt;</code> (scene level).</li>
    </ul>
    <p>A segment's <b>stage cast</b> (<code>characters_present</code>):
    under <code>sd</code>, the characters on stage after the segment's opening
    moves; under the two sequence segmentations, every character on stage at
    any moment of the unit &mdash; at its start or after any move inside it.
    In both cases anyone given an $\langle\mathrm{sp}\rangle$ in the segment
    is added.  Milestones carrying <code>@source</code> or <code>@resp</code>
    (parallel segmentations) are ignored; text before a sequence's first
    milestone belongs to no unit of it (the parser logs it).</p>
    <p><b>Network model</b> (radio):</p>
    <table style="font-size: 12.5px; border-collapse: collapse; margin: 8px 0;">
      <tr><th style="text-align: left; padding-right: 16px;">model</th>
          <th style="text-align: left; padding-right: 16px;">node set $V$</th>
          <th style="text-align: left;">segment cast $S_i$</th></tr>
      <tr><td><b>stage co-presence</b> (default)</td>
          <td>every character in some segment's stage cast</td>
          <td>the stage cast of segment $i$</td></tr>
      <tr><td><b>speaking cast on play level</b></td>
          <td>characters given $\geq 1$ $\langle\mathrm{sp}\rangle$ in the
          play; a speaking collective's silent parts are first rewritten to
          it (&sect;7)</td>
          <td>the stage cast of segment $i$, $\cap\, V$</td></tr>
      <tr><td><b>speaking cast on segment level</b></td>
          <td>characters given $\geq 1$ $\langle\mathrm{sp}\rangle$ in the
          play (no &sect;7 rewrite)</td>
          <td>the characters given an $\langle\mathrm{sp}\rangle$ in
          segment $i$</td></tr>
    </table>
    <p>A character is given an $\langle\mathrm{sp}\rangle$ when its
    <code>@who</code> names them, whether or not its text survives (&sect;4).
    On the stage-direction segmentation the two speaking models merge
    segments whose boundary they cannot see (&sect;9), so $N$ differs between
    models; the sequence segmentations are the same under all three.</p>
    <p><b>Edge weight</b> $w(u, v)$: the number of segments whose cast holds
    both (default, <code>--weight segments</code>), or with
    <code>--weight words</code> the words spoken in those segments by anyone
    (&sect;4).  Weighted degree and eigenvector centrality use $w$; all other
    measures ignore it.</p>
  </article>

  <section class="methods-section">
    <h3>1. Network-level metrics</h3>

    <article class="metric">
      <h4>order</h4>
      <p>$|V|$.</p>
      <p class="note"><code>metrics.json</code> keeps DraCor's field names:
      <code>size</code> holds $|V|$, <code>numEdges</code> holds $|E|$.</p>
    </article>

    <article class="metric">
      <h4>edges</h4>
      <p>$|E|$: the pairs $\{u, v\}$ joined in at least one segment.  A pair
      counts once; recurrence is carried by $w$.</p>
    </article>

    <article class="metric">
      <h4>density</h4>
      <p>$$d = \frac{2 \, |E|}{|V| \, (|V| - 1)}$$</p>
      <p>$0$ for $|V| < 2$.  Since $d = \langle k \rangle / (|V| - 1)$, at a
      constant average degree density falls as $|V|$ grows; it changes with
      the node set as well as with the connections.</p>
    </article>

    <article class="metric">
      <h4>average degree</h4>
      <p>$$\langle k \rangle = \frac{2 \, |E|}{|V|}$$</p>
    </article>

    <article class="metric">
      <h4>max degree, max-degree ids</h4>
      <p>$$k_{\max} = \max_{v \in V} \deg(v)$$</p>
      <p>All characters attaining it are listed.</p>
    </article>

    <article class="metric">
      <h4>diameter, average path length</h4>
      <p>$$D = \max_{u, v \in V'} d(u, v), \qquad
         \langle d \rangle = \frac{1}{|V'| (|V'| - 1)} \sum_{u \neq v \in V'} d(u, v)$$</p>
      <p>$d(u, v)$ is the unweighted shortest-path distance; $V'$ is the
      largest connected component (DraCor's convention).  Both are $0$ for a
      graph without edges.  Where $D \le 2$, $\langle d \rangle = 2 - d'$,
      $d'$ being the density of $V'$.</p>
    </article>

    <article class="metric">
      <h4>average clustering coefficient</h4>
      <p>$$\langle C \rangle = \frac{1}{|V|} \sum_{v \in V} C(v)$$</p>
      <p>Mean of the local coefficients of &sect;2, over all of $V$:
      characters with fewer than two neighbours enter with $0$.  Unweighted
      (<code>nx.average_clustering</code>).</p>
      <p class="note">Every segment's cast is a clique, so all triples within
      one segment are closed by construction.  A closed triple means each pair
      shared some segment, not necessarily the same one.</p>
    </article>

    <article class="metric">
      <h4>number of connected components</h4>
      <p>$c(G)$, the number of maximal connected subgraphs; an isolated
      character is a component of its own.</p>
    </article>
  </section>

  <section class="methods-section">
    <h3>2. Per-character (centrality) metrics</h3>

    <article class="metric">
      <h4>degree, weighted degree</h4>
      <p>$$\deg(v) = |N(v)|, \qquad
         \deg_w(v) = \sum_{u \in N(v)} w(u, v)$$</p>
      <p>$N(v)$: the characters joined to $v$.  With the default weight, each
      segment containing $v$ adds the number of characters $v$ is joined to
      there.</p>
    </article>

    <article class="metric">
      <h4>betweenness centrality</h4>
      <p>$$B(v) = \frac{2}{(|V| - 1)(|V| - 2)}
         \sum_{\substack{\{s, t\} \subseteq V \setminus \{v\} \\ s \neq t}}
         \frac{\sigma_{st}(v)}{\sigma_{st}}$$</p>
      <p>$\sigma_{st}$: the number of shortest $s$&ndash;$t$ paths;
      $\sigma_{st}(v)$: those passing through $v$.  Unweighted, normalised to
      $[0, 1]$ (<code>nx.betweenness_centrality</code>,
      <code>normalized=True</code>).  A pair in different components
      contributes $0$ and is still counted in the prefactor.  $0$ for
      $|V| < 3$.</p>
    </article>

    <article class="metric">
      <h4>closeness centrality</h4>
      <p>$$C(v) = \frac{|V_v| - 1}{|V| - 1} \cdot
         \frac{|V_v| - 1}{\sum_{u \in V_v \setminus \{v\}} d(v, u)}$$</p>
      <p>$V_v$: the component containing $v$.  Unweighted, with the
      Wasserman&ndash;Faust factor (first fraction), which is $1$ when $G$ is
      connected (<code>nx.closeness_centrality</code>).  $0$ for an isolated
      character.</p>
    </article>

    <article class="metric">
      <h4>eigenvector centrality</h4>
      <p>$$\lambda x_v = \sum_{u \in N(v)} w(u,v) \, x_u$$</p>
      <p>$\mathbf{x}$: the principal eigenvector of the weighted adjacency
      matrix (<code>nx.eigenvector_centrality_numpy</code>).  Computed for each
      connected component separately and normalised to unit Euclidean length
      within it, so values compare within a component, not across components;
      $0$ for an isolated character.</p>
      <p class="note">Requires NumPy and SciPy.  Without them NetworkX's power
      iteration is used, and values differ from about the sixth decimal.</p>
    </article>

    <article class="metric">
      <h4>local clustering coefficient</h4>
      <p>$$C(v) = \frac{T(v)}{\deg(v) (\deg(v) - 1) / 2}$$</p>
      <p>The share of $v$'s neighbour pairs that are joined.  Unweighted
      (<code>nx.clustering</code>); $0$ when $\deg(v) < 2$.</p>
    </article>

    <article class="metric">
      <h4>triangles</h4>
      <p>$$T(v) = |\{\{u, w\} \subseteq N(v) : \{u, w\} \in E\}|$$</p>
      <p>The joined neighbour pairs of $v$ (<code>nx.triangles</code>).  Each
      triangle is counted at each of its three vertices.</p>
    </article>
  </section>

  <section class="methods-section">
    <h3>3. Cast composition</h3>

    <article class="metric">
      <h4>speakers / mutes</h4>
      <p><b>Speaker</b>: named in the <code>@who</code> of at least one
      $\langle\mathrm{sp}\rangle$, whether or not its text survives.
      <b>Mute</b>: never named.</p>
      <p class="note">Counted over every character declared in
      $\langle\mathrm{listPerson}\rangle$, including any who enter no segment
      (a figure whose only stage event is a <code>crossing</code>, &sect;9), so
      speakers + mutes can exceed the order.  Under both speaking models mutes
      are excluded from every count of this section.</p>
    </article>

    <article class="metric">
      <h4>individuals / collectives / chorus</h4>
      <p>$\langle\mathrm{person}\rangle$: individual;
      $\langle\mathrm{personGrp}\rangle$: collective.  A chorus is a character
      marked <code>#chorus</code> or <code>#semichorus</code> in its
      $\langle\mathrm{castList}\rangle$ entry; nothing is inferred from ids or
      names.</p>
      <p class="note">Role chips in the tables:
      <span class="chip">individual</span>,
      <span class="chip collective">collective</span>,
      <span class="chip chorus">chorus</span>; muteness adds
      <span class="chip mute">mute</span>.</p>
    </article>

    <article class="metric">
      <h4>male / female / mixed / unspecified</h4>
      <p>From <code>&lt;trait type="sex"&gt;</code>: <code>male</code>,
      <code>female</code>, <code>mixed</code>; <code>irrelevant</code>, any
      other value, or no trait is shown as <em>unspecified</em>.
      <em>mixed</em> is listed only where it occurs.</p>
    </article>

    <article class="metric">
      <h4>human / divine / animal / concept</h4>
      <p>From <code>&lt;trait type="nature"&gt;</code>: <code>human</code>,
      <code>divine</code>, <code>animal</code>;
      <code>personified-abstraction</code> is shown as <em>concept</em>.  Any
      other value, or no trait, is counted as <em>other</em>, listed only
      where it occurs.</p>
    </article>

    <article class="metric">
      <h4>composition ratios (corpus plays table)</h4>
      <p>$$\text{spk/cast} = \frac{|\text{speakers}|}{|\text{speakers}|+|\text{mutes}|}
         \qquad
         \text{col/spk} = \frac{|\text{collective speakers}|}{|\text{speakers}|}
         \qquad
         \text{f}/(\text{f}+\text{m}) = \frac{|\text{female}|}{|\text{female}|+|\text{male}|}$$</p>
      <p>Computed with every <code>partOf</code> group aggregated (&sect;7),
      so a divided chorus counts once, whatever the aggregation toggle.  Under
      the speaking models mutes are excluded, so spk/cast $= 1$.</p>
    </article>
  </section>

  <section class="methods-section">
    <h3>4. Speech distribution</h3>

    <article class="metric">
      <h4>words</h4>
      <p>A <b>word</b> is a whitespace-separated token containing at least one
      letter or digit, read from the verse lines ($\langle l \rangle$) of an
      $\langle\mathrm{sp}\rangle$ or, in prose, from its
      $\langle p \rangle$ and $\langle\mathrm{ab}\rangle$ blocks.  An
      $\langle\mathrm{sp}\rangle$ with none of these is read whole.  Not
      counted: $\langle\mathrm{note}\rangle$, $\langle\mathrm{gap}\rangle$,
      $\langle\mathrm{speaker}\rangle$, $\langle\mathrm{stage}\rangle$, and
      text outside the lines or blocks.  Counted: everything else in a line,
      $\langle\mathrm{del}\rangle$ included.  A sign standing alone (&dagger;,
      a spaced dash) is not a word.</p>
      <p><b>Attribution.</b>  A speech's words are credited in full to every
      character in its <code>@who</code>:</p>
      <p>$$W = \sum_{\mathrm{sp}} |\mathrm{@who}(\mathrm{sp})| \cdot
              \mathrm{words}(\mathrm{sp})
            = \sum_{c} w_c$$</p>
      <p>All word figures &mdash; play total $W$, character totals $w_c$,
      segment totals, words on an edge &mdash; follow this rule and so add up.
      $W$ exceeds the words of the text by the repeats of joint speeches.</p>
      <p><b>Speech versus words.</b>  Whether a character speaks is decided by
      the $\langle\mathrm{sp}\rangle$ (speaker status, segment-level casts,
      <code>num_speeches</code>); how much, by words.  A speech whose text is
      lost counts as one speech of $0$ words.  Exception: max simultaneous
      speakers (&sect;5) counts only speeches with words.</p>
      <p><code>num_speeches</code>: the $\langle\mathrm{sp}\rangle$ elements of
      a segment.  No per-character $\langle\mathrm{sp}\rangle$ count is
      reported, since the encoding splits a speech wherever a move or a change
      of addressee falls inside it.</p>
      <p class="note">This section's values depend on the character set only:
      they change with <code>partOf</code> aggregation (merged characters'
      words are summed), not with the segmentation or the network
      model.</p>
    </article>

    <article class="metric">
      <h4>top speaker, top-speaker word share</h4>
      <p>The character with the largest $w_c$, and $w_c / W$.  Tied characters
      are all listed (<code>top_speaker_ids</code>);
      <code>top_speaker_id</code> is the first of them.</p>
    </article>

    <article class="metric">
      <h4>Gini coefficient (words)</h4>
      <p>$$G = \frac{2 \sum_{i=1}^{n} i \cdot v_{(i)}}
              {n \sum_{i=1}^{n} v_{(i)}} - \frac{n + 1}{n}$$</p>
      <p>$v_{(1)} \le \ldots \le v_{(n)}$: the word totals of the $n$
      characters with at least one word.  $G = 0$ when all say the same;
      the maximum is $\frac{n-1}{n}$, which rises with $n$.  Adding or merging
      a minor speaker changes $n$ and can move $G$ noticeably in a small
      cast.</p>
    </article>

    <article class="metric">
      <h4>effective speakers</h4>
      <p>$$\mathrm{ESp} = \frac{1}{\sum_{c} s_c^{\,2}}, \qquad
         s_c = \frac{w_c}{W}$$</p>
      <p>Over the same $n$ characters as $G$.  $\mathrm{ESp} = n$ when all say
      the same, $1$ when one says everything.  The inverse Herfindahl index
      (Laakso &amp; Taagepera 1979).  A speaker with share $\varepsilon$
      changes it by about $2\varepsilon \cdot \mathrm{ESp}$.</p>
    </article>
  </section>

  <section class="methods-section">
    <h3>5. Plot dynamics &mdash; Fischer et al. 2017</h3>

    <article class="metric">
      <h4>segment-change rate</h4>
      <p>$$r_i = \frac{|S_i \mathbin{\triangle} S_{i+1}|}
                       {|S_i \cup S_{i+1}|}$$</p>
      <p>Jaccard distance between consecutive casts under the active model
      ($0$ if both are empty).  $T$, the transitions included, leaves out two:
      out of the first segment if its cast is empty, and into the last
      segment if its cast is empty &mdash; on the stage-direction segmentation
      only if the stage itself is empty there.</p>
      <p><b>Beat chart.</b>  Plots $r_i$ for $i \in T$, with the DCR as a
      dashed line.  The x-axis is the number of the segment the transition
      leaves (an empty first segment counting as $0$) or, with <em>space
      x-axis by word position</em>, the cumulative word count at that
      segment's end.</p>
    </article>

    <article class="metric">
      <h4>drama-change rate (DCR), $\sigma$</h4>
      <p>$$\mathrm{DCR} = \frac{1}{|T|} \sum_{i \in T} r_i, \qquad
         \sigma = \sqrt{\frac{1}{|T|} \sum_{i \in T}
            \left( r_i - \mathrm{DCR} \right)^2}$$</p>
      <p>Mean and population standard deviation of the included change
      rates.</p>
    </article>

    <article class="metric">
      <h4>all-in segment, all-in index</h4>
      <p>The scanned segments are the segments of the active spine, without the
      first if its cast is empty under the active model; $N'$ is their number
      and $S_{\mathrm{tot}}$ the union of their casts.  $j$ is the smallest
      (1-based) position with $\bigcup_{i \le j} S_i = S_{\mathrm{tot}}$:</p>
      <p>$$\text{all-in index} = \frac{j}{N'} \in (0, 1]$$</p>
      <p>The dashboard names segment $j$ by its label.
      <code>metrics.json</code> stores $j - 1$ in <code>all_in_segment</code>
      (0-based over the scanned segments) and the label in
      <code>all_in_segment_label</code>.</p>
    </article>

    <article class="metric">
      <h4>final segment cast share</h4>
      <p>$$\frac{|S_{\mathrm{last}}|}{|S_{\mathrm{tot}}|}$$</p>
      <p>$S_{\mathrm{last}}$: the cast of the last segment whose cast is
      non-empty under the active model.  Called <em>final-scene size</em> by
      Fischer et al. 2017, Fig. 2; here the unit is a segment of the active
      spine.</p>
    </article>

    <article class="metric">
      <h4>max simultaneous speakers</h4>
      <p>$$\max_{1 \le i \le N} \bigl| \bigcup \{\,
            \mathrm{@who}(\mathrm{sp}) : \mathrm{sp} \text{ in segment } i,\
            \mathrm{words}(\mathrm{sp}) > 0 \,\} \bigr|$$</p>
      <p>The most distinct characters given words in one segment.  A
      collective counts as one.</p>
    </article>

    <article class="metric">
      <h4>per-character temporal Gini (tGini)</h4>
      <p>For a character $c$ with at least one word: $\mathbf{v}^{(c)}$ holds
      $c$'s words in each of the $m_c$ segments in which $c$ is in the stage
      cast or speaks, zeros included.  Leading and trailing segments with
      nobody on stage are left out.</p>
      <p>$$\mathrm{tGini}(c) = \frac{2 \sum_{i=1}^{m_c} i \cdot v^{(c)}_{(i)}}
            {m_c \sum_{i=1}^{m_c} v^{(c)}_{(i)}} - \frac{m_c + 1}{m_c}$$</p>
      <p>$0$: $c$ speaks equally in every segment of their presence; the
      maximum $\frac{m_c - 1}{m_c}$: all of $c$'s words in one segment.
      Presence is the stage cast under every model; under the speaking models
      the stage-direction segmentation is the merged one (&sect;9).  Finer
      segmentations give longer vectors.</p>
      <p class="note">The speech-concentration table lists characters with
      $\geq 40$ words (display filter only).  The corpus column <em>top spk
      tGini</em> is the value of <code>top_speaker_id</code>.
      <code>metrics.json</code> and <code>characters.csv</code> carry, per
      character, <code>total_words</code>, <code>speaking_segments</code>,
      <code>n_onstage_segments</code> ($m_c$) and
      <code>temporal_gini</code>.</p>
    </article>
  </section>

  <section class="methods-section">
    <h3>6. Corpus charts</h3>

    <article class="metric">
      <h4>scatters</h4>
      <p><b>density &times; order</b>, <b>average degree &times; order</b>,
      <b>DCR &times; $\sigma$</b> (Fischer et al. 2017, Figs. 8&ndash;9) and
      <b>effective speakers &times; average degree</b>: one dot per play,
      under the active segmentation, model and aggregation state.  Effective
      speakers does not change with segmentation or model (&sect;4).</p>
    </article>

    <article class="metric">
      <h4>plays included</h4>
      <p>The chip selector includes or excludes plays from every panel.  KPI
      ranges and median crosshairs are computed over the included plays only.
      The selection is not saved.</p>
    </article>

    <article class="metric">
      <h4>median crosshair</h4>
      <p>Dashed lines at $x = \mathrm{median}(x_i)$ and
      $y = \mathrm{median}(y_i)$ over the included plays, on every
      scatter.</p>
    </article>

    <article class="metric">
      <h4>labels, highlight</h4>
      <p>Each dot is labelled to its right, or on another side where that
      label would overlap another label, sit nearer another dot, or leave the
      plot.  With more than twenty plays only highlighted plays are labelled.
      A highlight (the dot on a chip) rings the play's dot on every scatter,
      bolds its label, and is named in an exported scatter's caption; it
      changes no value.</p>
    </article>

    <article class="metric">
      <h4>pair-lines (density &times; order)</h4>
      <p>Optional (off by default).  A line joins every two plays whose orders
      differ by at most $5$; its tooltip gives both plays' coordinates and the
      excess $\max/\min - 1$ for density and for average degree.  A line that
      would pass under a third play's dot, or be hidden by its own two dots,
      is drawn as an arc; the curvature carries no value.</p>
    </article>

    <article class="metric">
      <h4>colour by average degree (density &times; order)</h4>
      <p>Optional (off by default).  Dots are coloured by $\langle k \rangle$
      on a reversed viridis scale (darker = higher), linear over
      $[A/4,\ 2A]$; values outside take the end colour.  $A$ is the median
      $\langle k \rangle$ over all plays, segmentations, models and
      aggregation states, rounded to the nearest power of two, so one colour
      means one value in every view.</p>
    </article>

    <article class="metric">
      <h4>beat-chart small multiples</h4>
      <p>One beat chart per play (&sect;5), with the same two x-axis
      options.</p>
    </article>
  </section>

  <section class="methods-section">
    <h3>7. <i>partOf</i> aggregation</h3>

    <article class="metric">
      <h4>aggregation toggle</h4>
      <p>One checkbox per group: each character that another is declared
      <code>partOf</code> (<code>&lt;relation name="partOf" active="#X"
      passive="#Y"/&gt;</code>), intermediate groups included.  Each member of
      a checked group is rewritten to its highest checked group in
      <code>sp/@who</code>, <code>sp/@toWhom</code> and
      <code>move/@who</code>, <code>@corresp</code>; members leave the cast
      list; the group takes over their chorus flag; muteness is recomputed.  A
      group leaves the stage only when its last present member does, so a
      split of the group into its own members changes nothing.  Segmentation,
      graphs and metrics then run unchanged.  A variant is precomputed for
      every combination of groups.</p>
    </article>

    <article class="metric">
      <h4>silent parts (speaking cast on play level only)</h4>
      <p>A <code>partOf</code> member never given an
      $\langle\mathrm{sp}\rangle$, whose group is given one, is rewritten to
      the group before the node set is taken; the group is then on stage
      wherever any such part is.  Members that speak are not affected.</p>
      <p class="note">In the Aristophanic corpus this applies only to
      Ecclesiazusae: <code>merosChorouA</code>&ndash;<code>C</code> enter at
      vv. 30, 43, 54 and merge into <code>choros</code> at v. 285.  Under this
      model <code>choros</code> therefore counts as on stage from v. 30; under
      <i>speaking cast on segment level</i> it enters the graph at v. 285,
      where it is first given a speech.  On the stage-direction segmentation this model gives 16
      nodes and 35 edges with or without the aggregation toggle (32 edges
      unaggregated without the rewrite); <i>stage co-presence</i>, which keeps
      the parts, gives 23 nodes and 63 edges, aggregated 20 and 51.</p>
      <p class="ref"><b>partOf relations in this play.</b>
      <span id="aggregation-relations">&mdash;</span></p>
    </article>
  </section>

  <section class="methods-section">
    <h3>8. Node size in the network views</h3>

    <article class="metric">
      <h4>static graph</h4>
      <p>$$r = 3 + 2.8\sqrt{\deg(v)}$$</p>
      <p>Radius in pixels; area roughly proportional to degree.  Tooltips give
      degree, weighted degree, betweenness, closeness and eigenvector
      centrality.</p>
    </article>

    <article class="metric">
      <h4>dynamic graph</h4>
      <p>With no segment selected, as the static graph.  With segment $i$
      selected, the graph is the clique on $S_i$ (less any collective&ndash;part
      pair, as in $G$) and size encodes $v$'s words in the segment:</p>
      <p>$$r = 3 + 1.5\log_2 \bigl(1 + \mathit{words}_v(i)\bigr)$$</p>
    </article>
  </section>

  <section class="methods-section">
    <h3>9. Stage-direction segmentation and the model-specific spine</h3>

    <article class="metric">
      <h4>segment boundaries</h4>
      <p>A $\langle\mathrm{stage}\rangle$ containing at least one
      <code>entrance</code>, <code>exit</code>, <code>onStage</code>,
      <code>merge</code> or <code>split</code> closes the open segment and
      opens a new one; all moves in one $\langle\mathrm{stage}\rangle$ form one
      boundary.  <code>state-change</code> and <code>crossing</code> open no
      segment.  Speeches belong to the segment in which they stand.</p>
      <ul>
        <li>A leading empty <code>&lt;move type="onStage"/&gt;</code> forms
        segment 1 on its own: the empty stage before the play.</li>
        <li>A closing empty <code>onStage</code> after a complete exit opens
        no segment, so the play ends on one empty segment.</li>
        <li>Moves outside any $\langle\mathrm{stage}\rangle$ (a schema
        violation, logged): consecutive ones with no speech between them form
        one boundary.</li>
      </ul>
      <p>A <code>crossing</code> leaves the stage state unchanged; its figure
      joins no cast.  Crossings are counted per segment as
      <code>num_crossings</code> (segments table, <code>segments.csv</code>).</p>
    </article>

    <article class="metric">
      <h4>model-specific spine</h4>
      <p>The boundaries above make the spine of <i>stage co-presence</i>.  The
      two speaking models merge adjacent segments.  A merged segment's stage
      cast is the union of its parts; its speeches, moves and crossings are
      concatenated and its words summed.  Segments are renumbered $1..N$.</p>
      <ul>
        <li><b>speaking cast on play level</b>: adjacent segments with the
        same stage cast within $V$ are merged.  $V$ and $E$ are unchanged;
        segment counts, per-segment series and segment-count weights change,
        word weights do not.</li>
        <li><b>speaking cast on segment level</b>: first, as above; then,
        left to right, each segment so formed is merged into the one before
        if, for every boundary inside the result, no character of $V$ entering
        or leaving there speaks anywhere in the result, and no boundary
        separates an empty from an occupied stage (within $V$).  This can join
        speakers from segments of different cast, adding edges.</li>
      </ul>
      <p>The sequence segmentations are not merged.  Segment $k$ is not the
      same stretch of the play under different models.</p>
    </article>
  </section>

  <section class="methods-section">
    <h3>10. Character &times; segment heatmap</h3>

    <article class="metric">
      <h4>cells</h4>
      <p>One row per node of the active graph, one column per segment.</p>
      <ul>
        <li><b>empty</b> &mdash; not in the segment's stage cast;</li>
        <li><b>grey</b> &mdash; in the stage cast, given no
        $\langle\mathrm{sp}\rangle$;</li>
        <li><b>red hatch</b> &mdash; given only speeches whose text is lost
        (e.g. the &Chi;&Omicron;&Rho;&Omicron;&Upsilon; interludes);</li>
        <li><b>red ramp</b> &mdash; words spoken, square-root scaled
        (<code>d3.scaleSqrt</code>) from <code>#fcbba1</code> to
        <code>#a50f15</code> against the largest cell of the matrix.</li>
      </ul>
      <p>Beside the matrix: the number of cells in each state, and two edge
      counts read off the visible matrix &mdash; pairs coloured together in
      some column (any colour), and pairs red together (both with words, so
      hatched cells do not count).</p>
    </article>

    <article class="metric">
      <h4>row order</h4>
      <ul>
        <li><b>loudest first</b> (default) &mdash; total words,
        descending.</li>
        <li><b>appearance order</b> &mdash; first segment in the stage
        cast.</li>
        <li><b>most stage entrances/exits</b> &mdash; entries into and exits
        from the stage cast along the columns, twice the number of unbroken
        stretches on stage; ties by total words.</li>
        <li><b>alphabetical</b> &mdash; display name.</li>
      </ul>
      <p>Remaining ties: by display name.</p>
    </article>

    <article class="metric">
      <h4>interaction</h4>
      <p>Clicking a cell selects its segment in the dynamic graph, the
      segments table, the timeline and the heatmap.  Under the speaking models
      the mute rows are absent and the ramp is rescaled; on the
      stage-direction segmentation the merged spines (&sect;9) give fewer
      columns.</p>
    </article>
  </section>

  <section class="methods-section">
    <h3>11. Chorus presence chart (corpus dashboard)</h3>

    <article class="metric">
      <h4>cells</h4>
      <p>One row per chorus character (&sect;3) of each included play, one
      cell per segment; states as in &sect;10.  The red ramp is scaled
      against the largest cell over all visible rows, so intensities compare
      across plays.</p>
    </article>

    <article class="metric">
      <h4>x-axis</h4>
      <p>Each play's segments, without leading and trailing segments with
      nobody on stage, fill the full width: the axis is the share of the
      play's segments, so a cell's width differs between plays.</p>
    </article>

    <article class="metric">
      <h4>row order</h4>
      <p>By genre, author, title, then chorus name; alternate (genre, author)
      groups are shaded.  Genre is read from
      <code>&lt;textClass&gt;&lt;catRef scheme="#genre" target="#..."/&gt;</code>;
      without it, from the author's name (Aristophanes, Menander, Plautus,
      Terence: comedy; Aeschylus, Sophocles, Euripides, Seneca: tragedy;
      otherwise <em>other</em>, last).</p>
    </article>

    <article class="metric">
      <h4>controls</h4>
      <p>All corpus panels follow the segmentation tab, the network model and
      the <b>aggregate chorus halves</b> toggle, which switches every play to
      its variant with all <code>partOf</code> groups aggregated (&sect;7).
      Under <i>speaking cast on play level</i> silent parts are absorbed into
      their chorus (&sect;7) and lose their rows.  The composition ratios
      (&sect;3) are always computed aggregated.</p>
    </article>
  </section>

  <section class="methods-section">
    <h3>References</h3>
    <ul class="biblio">
      <li>Fischer, F., Göbel, M., Kampkaspar, D., Kittel, C. &amp; Trilcke, P.
        (2017).  <em>Network Dynamics, Plot Analysis: Approaching the
        Progressive Structuration of Literary Texts</em>.  DH 2017 Montréal.
        [<a href="https://dh2017.adho.org/abstracts/071/071.pdf">PDF</a>]</li>
      <li>Laakso, M. &amp; Taagepera, R. (1979).  &ldquo;Effective&rdquo;
        Number of Parties: A Measure with Application to West Europe.
        <em>Comparative Political Studies</em> 12(1), 3&ndash;27.</li>
    </ul>
  </section>
</div>
"""


__all__ = ["methods_panel_html"]
