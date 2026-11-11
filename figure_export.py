"""Client-side figure export, shared by the play and corpus dashboards.

Every figure in both dashboards is an `<svg>`, so a figure can be lifted out
of the page as vector art instead of being photographed.  This module holds
the CSS and JavaScript that put an `SVG` / `PNG` pair into each panel header;
both dashboards inject it through the same comment-and-replace mechanism they
already use for the Methods panel, so the strings need no brace escaping.

Three things make this more than a call to `XMLSerializer`.

*Colour.*  The charts colour themselves through CSS custom properties --
`fill` is literally `var(--chorus)` in the d3 code -- and custom properties
resolve only inside the document that defines them, so a naively serialised
`<svg>` opens black or empty in Inkscape.  The exporter walks the clone and
freezes each element's *computed* value for a short list of presentation
properties, skipping any value the element would inherit anyway, which keeps
the output small for the character x segment heatmap's few thousand cells.

*Completeness.*  A panel is not always one `<svg>`: the corpus beat chart is
a grid of small multiples, one per play, and the graph panels carry their
colour key in an HTML `<div class="legend">` beside the drawing.  Exporting
the first `<svg>` would silently drop eleven twelfths of the one and the key
to the other.  Children are therefore composed into a single root at their
measured offsets, and the legend is rebuilt as SVG primitives from the same
swatches the page shows.

*Provenance.*  Each dashboard defines `figureProvenance(panel)`, returning
`{caption, slug}`.  The caption is drawn into the figure as a footer line and
written into its `<title>` and `<desc>`; the slug names the file.  This is the
point of the feature: the same panel shows different numbers under different
segmentations and network models, and an image carries none of that on its
own.  A figure that states its own configuration can be checked by a reader
and re-made by its author.
"""

from __future__ import annotations

from version import __version__


CSS_PLACEHOLDER = "<!--FIGURE_EXPORT_CSS-->"
JS_PLACEHOLDER = "<!--FIGURE_EXPORT_JS-->"


def figure_export_css() -> str:
    """Styling for the per-panel export control."""
    return """<style>
/* Figure export control -- one per panel that holds an <svg>.  The panel
   header is a flex row (title | hint); pinning the hint to the right keeps
   the title left-aligned once a third child joins it. */
.panel h3 .hint { margin-left: auto; }
.fig-export { display: inline-flex; gap: 4px; margin-left: 10px;
  flex: none; align-self: center; }
.fig-export button { font: inherit; font-size: 10px; letter-spacing: 0.04em;
  text-transform: uppercase; color: var(--muted); background: transparent;
  border: 1px solid var(--border); border-radius: 3px; padding: 1px 6px;
  cursor: pointer; line-height: 1.5; }
.fig-export button:hover { color: var(--accent); border-color: var(--accent); }
.fig-export button:disabled { opacity: 0.5; cursor: progress; }
@media print { .fig-export { display: none; } }
</style>"""


_JS = """<script>
(function () {
  "use strict";
  const APP_VERSION = "__APP_VERSION__";
  const PNG_SCALE = 3;          // crisp on a projector
  const PNG_MAX_EDGE = 4000;    // ... without producing absurd files
  const PAD = 8;                // breathing room around the composed figure
  const HEADING_ROW = 22;
  const LEGEND_ROW = 18;
  const CAPTION_ROW = 20;
  const CAPTION_LINE = 13;      // a further line of the caption
  const SANS = "-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,Helvetica,"
             + "Arial,sans-serif";
  const NS = "http://www.w3.org/2000/svg";

  // Presentation properties worth carrying into a standalone file.  Split by
  // whether SVG inherits them: an inherited property can be skipped whenever
  // it matches the parent's computed value, which is what keeps the heatmap
  // export small.  `opacity` must never be skipped that way -- it multiplies
  // down the tree rather than inheriting, so dropping a child's 0.5 because
  // its parent is also 0.5 would change the picture.
  const INHERITED = ["fill", "fill-opacity", "fill-rule", "stroke",
    "stroke-opacity", "stroke-width", "stroke-dasharray", "stroke-linecap",
    "stroke-linejoin", "color", "font-family", "font-size", "font-style",
    "font-weight", "letter-spacing", "text-anchor", "paint-order",
    "shape-rendering"];
  const STANDALONE = { "opacity": "1", "dominant-baseline": "auto" };

  function provenanceOf(panel) {
    try {
      if (typeof figureProvenance === "function") return figureProvenance(panel) || {};
    } catch (e) { /* a caption is a nicety; never block the export */ }
    return {};
  }

  function panelTitle(panel) {
    const h = panel.querySelector("h3");
    if (!h) return "figure";
    const c = h.cloneNode(true);
    // The heading also holds controls -- the fullscreen toggle among them --
    // whose text is no part of the figure's name.
    c.querySelectorAll(".hint, .fig-export, button").forEach(n => n.remove());
    return (c.textContent || "figure").replace(/\\s+/g, " ").trim();
  }

  function slugify(s) {
    return (s || "").normalize("NFKD").replace(/[\\u0300-\\u036f]/g, "")
      .replace(/[^A-Za-z0-9\\s-]/g, "").trim()
      .replace(/\\s+/g, "-").replace(/-+/g, "-").toLowerCase() || "figure";
  }

  // Text measurement.  The exporter runs in the page, so the browser can
  // measure a string exactly instead of counting characters.
  let _measureCtx = null;
  function textWidth(text, font) {
    try {
      if (!_measureCtx) _measureCtx = document.createElement("canvas").getContext("2d");
      _measureCtx.font = font;
      return _measureCtx.measureText(String(text)).width;
    } catch (e) {
      return String(text).length * 6;    // never 0: a rough width is better
    }
  }

  // Greedy wrap to `maxWidth`, `measure(text)` giving the width of a string.
  // A single word wider than the line keeps a line of its own and overruns
  // it: nothing in a caption is that long, and breaking a word mid-way
  // would lose more than it saves.
  function wrapText(text, maxWidth, measure) {
    const words = String(text).split(/\\s+/).filter(Boolean);
    const lines = [];
    let line = "";
    for (const word of words) {
      const candidate = line ? line + " " + word : word;
      if (line && measure(candidate) > maxWidth) {
        lines.push(line);
        line = word;
      } else {
        line = candidate;
      }
    }
    if (line) lines.push(line);
    return lines.length ? lines : [""];
  }

  function pageBackground() {
    const v = getComputedStyle(document.body).backgroundColor;
    return (!v || v === "transparent" || /rgba\\(0, 0, 0, 0\\)/.test(v))
      ? "#ffffff" : v;
  }

  // Copy the computed presentation style of every node onto its clone, and
  // drop whatever the page is not showing.
  function freeze(srcRoot, cloneRoot) {
    // The root is included and gets the full declaration rather than a diff
    // against its parent: in the page it inherits font and colour from the
    // surrounding HTML, which will not be there in the exported file, so the
    // root has to carry the baseline its descendants inherit from.
    const src = [srcRoot].concat(Array.from(srcRoot.querySelectorAll("*")));
    const dst = [cloneRoot].concat(Array.from(cloneRoot.querySelectorAll("*")));
    const drop = [];
    for (let i = 0; i < src.length; i++) {
      const cs = getComputedStyle(src[i]);
      // Hidden in the page means absent from the figure.  Carrying
      // `display:none` across would be fragile; removing the node is not.
      if (i > 0 && (cs.display === "none" || cs.visibility === "hidden")) {
        drop.push(dst[i]);
        continue;
      }
      const parent = i === 0 ? null : src[i].parentElement;
      const ps = parent ? getComputedStyle(parent) : null;
      let decl = "";
      for (const p of INHERITED) {
        const v = cs.getPropertyValue(p);
        if (!v) continue;
        if (ps && ps.getPropertyValue(p) === v) continue;
        decl += p + ":" + v + ";";
      }
      for (const p in STANDALONE) {
        const v = cs.getPropertyValue(p);
        if (v && v !== STANDALONE[p]) decl += p + ":" + v + ";";
      }
      if (decl) dst[i].setAttribute("style", decl);
      else dst[i].removeAttribute("style");
      dst[i].removeAttribute("class");
      // d3 sets several presentation attributes to `var(--accent)` and the
      // like.  The frozen style above wins where it was written, but a
      // property skipped as inherited would leave the attribute to resolve
      // against a document that no longer exists -- black, or nothing.
      // Dropping them lets the inherited value through, which is the value
      // the page was showing.
      for (const a of Array.from(dst[i].attributes)) {
        if (a.value && a.value.indexOf("var(--") !== -1) {
          dst[i].removeAttribute(a.name);
        }
      }
    }
    drop.forEach(n => { if (n.parentNode) n.parentNode.removeChild(n); });
  }

  // A label that belongs to one figure but lives in HTML rather than in the
  // drawing: the corpus small multiples caption each chart with a sibling
  // <div class="title">.  Exporting the <svg> alone would give a grid of
  // unlabelled charts, so such a title travels with its <svg>, drawn at the
  // position it occupies on the page.  Nothing else does: where a panel's
  // <svg> sits in the panel itself, the heading is a sibling too, with its
  // hint and controls, and in fullscreen the segmentation and play controls
  // move in beside it.  The figure's own heading is set by serialise().
  function labelsFor(svg) {
    const host = svg.parentElement;
    if (!host || host.querySelectorAll("svg").length !== 1) return [];
    return Array.from(host.children).filter(function (el) {
      return el.classList.contains("title")
        && (el.textContent || "").trim() && el.getBoundingClientRect().width > 1;
    }).map(function (el) {
      const cs = getComputedStyle(el);
      const r = el.getBoundingClientRect();
      return { rect: r, text: (el.textContent || "").replace(/\\s+/g, " ").trim(),
               size: parseFloat(cs.fontSize) || 11, weight: cs.fontWeight,
               colour: cs.color, family: cs.fontFamily,
               align: cs.textAlign };
    });
  }

  // Every <svg> in the panel that is actually laid out, its HTML labels, and
  // the panel's legend swatches if it has any.
  function figureParts(panel) {
    const svgs = Array.from(panel.querySelectorAll("svg")).filter(function (s) {
      const r = s.getBoundingClientRect();
      return r.width > 1 && r.height > 1;
    });
    const labels = [];
    svgs.forEach(s => labelsFor(s).forEach(l => labels.push(l)));
    // Legend entries, in page order.  A key sits in `.legend` (the network,
    // the cast composition, the heatmap) or in `.legend-inline` (the chorus
    // chart).  How a swatch is painted cannot always be read off a
    // background colour -- a hatch and a ramp are neither -- so a swatch
    // says which it is in `data-swatch`, with its colours in `data-colors`.
    // An entry without a swatch is a note rather than a key -- "node area
    // proportional to degree" and the like -- and is worth keeping in a
    // figure, so it travels as label-only.
    const legend = Array.from(
      panel.querySelectorAll(".legend > span, .legend-inline > span"))
      .map(function (span) {
        const sw = span.querySelector('[class*="swatch"]');
        const label = (span.textContent || "").replace(/\\s+/g, " ").trim();
        if (!sw) return { color: null, label: label };
        const cs = getComputedStyle(sw);
        return {
          label: label,
          kind: sw.getAttribute("data-swatch") || "solid",
          colors: (sw.getAttribute("data-colors") || "").split(/\\s+/).filter(Boolean),
          color: cs.backgroundColor,
          swatchWidth: Math.max(9, Math.min(60, parseFloat(cs.width) || 9)),
        };
      })
      .filter(e => e.label);
    return { svgs: svgs, legend: legend, labels: labels };
  }

  // Compose the panel into one standalone SVG document.
  function serialise(panel, caption) {
    const parts = figureParts(panel);
    if (!parts.svgs.length) return null;
    const rects = parts.svgs.map(s => s.getBoundingClientRect());
    const boxes = rects.concat(parts.labels.map(l => l.rect));
    const minX = Math.min.apply(null, boxes.map(r => r.left));
    const minY = Math.min.apply(null, boxes.map(r => r.top));
    const maxX = Math.max.apply(null, boxes.map(r => r.right));
    const maxY = Math.max.apply(null, boxes.map(r => r.bottom));
    const artW = Math.max(1, maxX - minX);
    const artH = Math.max(1, maxY - minY);
    // The figure's name, set above it: the panel heading's own text, without
    // its hint and controls, and laid out here rather than where the page
    // has it, since in fullscreen the page's controls stand in between.
    const heading = panel.querySelector("h3") ? panelTitle(panel) : "";
    const top = PAD + (heading ? HEADING_ROW : 0);
    const HEADING_FONT = "600 13px " + SANS;
    const CAPTION_FONT = "10px " + SANS;
    // The figure is as wide as its art, or as its heading where that is
    // wider; the caption is wrapped to that width further down.
    const totalW = Math.round(
      Math.max(artW, heading ? textWidth(heading, HEADING_FONT) : 0) + PAD * 2);

    const root = document.createElementNS(NS, "svg");
    root.setAttribute("xmlns", NS);
    root.setAttribute("xmlns:xlink", "http://www.w3.org/1999/xlink");
    if (heading) {
      const t = document.createElementNS(NS, "text");
      t.setAttribute("x", PAD);
      t.setAttribute("y", PAD + 13);
      t.setAttribute("style", "font-family:" + SANS
        + ";font-size:13px;font-weight:600;fill:#333;");
      t.textContent = heading;
      root.appendChild(t);
    }

    // Each source <svg> is nested at its measured offset, so a grid of small
    // multiples comes out laid out exactly as the page lays it out.  A child
    // without a viewBox has CSS pixels for internal coordinates, so its own
    // box is the right one to declare.
    parts.svgs.forEach(function (svg, i) {
      const clone = svg.cloneNode(true);
      freeze(svg, clone);
      const r = rects[i];
      const vb = svg.viewBox && svg.viewBox.baseVal;
      if (!(vb && vb.width && vb.height)) {
        clone.setAttribute("viewBox", [0, 0, r.width, r.height].join(" "));
      }
      clone.setAttribute("x", PAD + (r.left - minX));
      clone.setAttribute("y", top + (r.top - minY));
      clone.setAttribute("width", r.width);
      clone.setAttribute("height", r.height);
      clone.removeAttribute("id");
      root.appendChild(clone);
    });

    // HTML labels, redrawn as SVG text where the page puts them.
    parts.labels.forEach(function (l) {
      const t = document.createElementNS(NS, "text");
      const centred = l.align === "center";
      t.setAttribute("x", PAD + (l.rect.left - minX) + (centred ? l.rect.width / 2 : 0));
      t.setAttribute("y", top + (l.rect.top - minY) + l.rect.height / 2 + l.size * 0.36);
      if (centred) t.setAttribute("text-anchor", "middle");
      t.setAttribute("style", "font-family:" + l.family + ";font-size:" + l.size
        + "px;font-weight:" + l.weight + ";fill:" + l.colour + ";");
      t.textContent = l.text;
      root.appendChild(t);
    });

    // A hatch or a ramp is no colour, so the figure is given a pattern or a
    // gradient of its own, drawn as the charts draw theirs.
    let legendDefs = null;
    function legendPaint(item, i) {
      if (!legendDefs) {
        legendDefs = document.createElementNS(NS, "defs");
        root.appendChild(legendDefs);
      }
      const id = "fig-legend-" + item.kind + "-" + i;
      const colours = item.colors.length ? item.colors : ["#bbbbbb", "#ffffff"];
      if (item.kind === "ramp") {
        const grad = document.createElementNS(NS, "linearGradient");
        grad.setAttribute("id", id);
        colours.forEach(function (c, j) {
          const stop = document.createElementNS(NS, "stop");
          stop.setAttribute("offset", colours.length < 2 ? 1 : j / (colours.length - 1));
          stop.setAttribute("stop-color", c);
          grad.appendChild(stop);
        });
        legendDefs.appendChild(grad);
      } else {
        const pat = document.createElementNS(NS, "pattern");
        pat.setAttribute("id", id);
        pat.setAttribute("patternUnits", "userSpaceOnUse");
        pat.setAttribute("width", 4);
        pat.setAttribute("height", 4);
        pat.setAttribute("patternTransform", "rotate(45)");
        const bg = document.createElementNS(NS, "rect");
        bg.setAttribute("width", 4);
        bg.setAttribute("height", 4);
        bg.setAttribute("fill", colours[1] || "#ffffff");
        const line = document.createElementNS(NS, "line");
        line.setAttribute("x1", 0); line.setAttribute("y1", 0);
        line.setAttribute("x2", 0); line.setAttribute("y2", 4);
        line.setAttribute("stroke", colours[0]);
        line.setAttribute("stroke-width", 1.5);
        pat.appendChild(bg);
        pat.appendChild(line);
        legendDefs.appendChild(pat);
      }
      return "url(#" + id + ")";
    }

    // Legend, rebuilt from the page's own swatches.  Laid out in rows so a
    // long key wraps instead of running off the edge.
    let y = top + artH + (parts.legend.length ? 6 : 0);
    let rows = 0;
    if (parts.legend.length) {
      let x = PAD;
      rows = 1;
      parts.legend.forEach(function (item, i) {
        const swW = item.kind ? Math.round(item.swatchWidth) : 0;
        const indent = item.kind ? swW + 5 : 0;
        const w = indent + item.label.length * 5.6 + 12;
        if (x > PAD && x + w > PAD + artW) { x = PAD; rows += 1; }
        const top = y + (rows - 1) * LEGEND_ROW;
        if (item.kind) {
          const sw = document.createElementNS(NS, "rect");
          sw.setAttribute("x", x);
          sw.setAttribute("y", top + 3);
          sw.setAttribute("width", swW);
          sw.setAttribute("height", 9);
          sw.setAttribute("rx", 2);
          sw.setAttribute("fill", item.kind === "solid" ? item.color
                                                        : legendPaint(item, i));
          root.appendChild(sw);
        }
        const t = document.createElementNS(NS, "text");
        t.setAttribute("x", x + indent);
        t.setAttribute("y", top + 11);
        t.setAttribute("style", "font-family:" + SANS + ";font-size:10px;fill:"
          + (item.kind ? "#444" : "#777") + ";");
        t.textContent = item.label;
        root.appendChild(t);
        x += w;
      });
      y += rows * LEGEND_ROW;
    }

    const full = caption ? caption + " \\u00b7 SkeneGraph-Net " + APP_VERSION : "";
    if (full) {
      // Wrapped to the figure, and measured rather than counted: beside a
      // dashboard panel some 360px wide the ordinary caption runs to 700,
      // and as one line it lost half of itself past the edge -- in the PNG
      // for good, the caption being the whole point of the export.
      const lines = wrapText(full, totalW - PAD * 2,
                             s => textWidth(s, CAPTION_FONT));
      lines.forEach(function (line, i) {
        const t = document.createElementNS(NS, "text");
        t.setAttribute("x", PAD);
        t.setAttribute("y", y + 12 + i * CAPTION_LINE);
        t.setAttribute("style", "font-family:" + SANS + ";font-size:10px;fill:#777;");
        t.textContent = line;
        root.appendChild(t);
      });
      y += CAPTION_ROW + (lines.length - 1) * CAPTION_LINE;
    }

    const totalH = Math.round(y + PAD);
    root.setAttribute("width", totalW);
    root.setAttribute("height", totalH);
    root.setAttribute("viewBox", [0, 0, totalW, totalH].join(" "));

    const bg = document.createElementNS(NS, "rect");
    bg.setAttribute("x", 0); bg.setAttribute("y", 0);
    bg.setAttribute("width", totalW); bg.setAttribute("height", totalH);
    bg.setAttribute("fill", pageBackground());
    root.insertBefore(bg, root.firstChild);

    if (full) {
      const desc = document.createElementNS(NS, "desc");
      desc.textContent = full;
      root.insertBefore(desc, root.firstChild);
      const ttl = document.createElementNS(NS, "title");
      ttl.textContent = panelTitle(panel) + " \\u2014 " + caption;
      root.insertBefore(ttl, root.firstChild);
    }
    const xml = new XMLSerializer().serializeToString(root);
    return { xml: '<?xml version="1.0" encoding="UTF-8"?>\\n' + xml,
             width: totalW, height: totalH };
  }

  // ---------------------------------------------------------------- tables
  // A table is worth more as numbers than as a picture of numbers: pasted
  // into a spreadsheet it can be sorted, compared across configurations and
  // typeset properly.  Read from the DOM rather than from the data, so what
  // leaves is exactly the columns and rows on screen -- including the rows
  // below the fold, since these tables sit in 360px scroll boxes.
  function tableMatrix(table) {
    const head = Array.from(table.querySelectorAll("thead th"))
      .map(th => cellText(th));
    const body = Array.from(table.querySelectorAll("tbody tr"))
      .map(tr => Array.from(tr.children).map(td => cellText(td)));
    return { head: head, body: body };
  }

  function cellText(cell) {
    // innerText, not textContent: it puts a space between the role chips and
    // a newline where the cast column breaks a line, which textContent would
    // run together into one word.
    const t = (cell.innerText != null ? cell.innerText : cell.textContent) || "";
    return t.replace(/\\s*\\n+\\s*/g, "; ").replace(/[ \\t]+/g, " ").trim();
  }

  function delimited(head, body, sep) {
    const esc = function (v) {
      const s = (v == null) ? "" : String(v);
      if (sep === "\\t") return s.replace(/[\\t\\n\\r]+/g, " ");
      return /["\\n\\r,;]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
    };
    return [head].concat(body).map(r => r.map(esc).join(sep)).join("\\n");
  }

  function copyText(text, button) {
    const done = function (ok) {
      const was = button.textContent;
      button.textContent = ok ? "copied" : "failed";
      setTimeout(function () { button.textContent = was; }, 1200);
    };
    // `navigator.clipboard` is undefined on a file:// page, which is how
    // these dashboards are normally opened, so the old path is the one that
    // usually runs.
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(() => done(true), () => fallback());
    } else { fallback(); }
    function fallback() {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.cssText = "position:fixed;top:-1000px;opacity:0;";
      document.body.appendChild(ta);
      ta.select();
      let ok = false;
      try { ok = document.execCommand("copy"); } catch (e) { ok = false; }
      document.body.removeChild(ta);
      done(ok);
    }
  }

  function exportTableCSV(panel, table) {
    const m = tableMatrix(table);
    const prov = provenanceOf(panel);
    // A leading byte-order mark so Excel reads the Greek names as UTF-8
    // rather than as mojibake.
    const text = "\\ufeff" + delimited(m.head, m.body, ",");
    saveBlob(new Blob([text], { type: "text/csv;charset=utf-8" }),
             filenameFor(panel, prov, "csv"));
  }

  // ------------------------------------------- every configuration at once
  // The dashboards answer differently under each segmentation and network
  // model, and the only way to compare those answers today is to switch,
  // read, switch back and remember.  A dashboard that defines
  // `figureComparisonRows()` gets a button that writes all of them out as
  // one table.
  function exportComparison(button) {
    let data = null;
    try {
      if (typeof figureComparisonRows === "function") data = figureComparisonRows();
    } catch (e) { data = null; }
    if (!data || !data.rows || !data.rows.length) {
      const was = button.textContent;
      button.textContent = "no data";
      setTimeout(function () { button.textContent = was; }, 1200);
      return;
    }
    const text = "\\ufeff" + delimited(data.header, data.rows, ",");
    saveBlob(new Blob([text], { type: "text/csv;charset=utf-8" }),
             slugify(data.name || "configurations") + ".csv");
  }

  function saveBlob(blob, filename) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 4000);
  }

  function filenameFor(panel, prov, ext) {
    return slugify(prov.slug || document.title) + "-"
         + slugify(panelTitle(panel)) + "." + ext;
  }

  function exportSVG(panel) {
    const prov = provenanceOf(panel);
    const doc = serialise(panel, prov.caption || "");
    if (!doc) return;
    saveBlob(new Blob([doc.xml], { type: "image/svg+xml;charset=utf-8" }),
             filenameFor(panel, prov, "svg"));
  }

  function exportPNG(panel, done) {
    const prov = provenanceOf(panel);
    const doc = serialise(panel, prov.caption || "");
    if (!doc) { done(); return; }
    const scale = Math.max(1, Math.min(PNG_SCALE,
      PNG_MAX_EDGE / Math.max(doc.width, doc.height)));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(doc.width * scale);
    canvas.height = Math.round(doc.height * scale);
    const ctx = canvas.getContext("2d");
    const img = new Image();
    img.onload = function () {
      ctx.fillStyle = pageBackground();
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      canvas.toBlob(function (blob) {
        if (blob) saveBlob(blob, filenameFor(panel, prov, "png"));
        done();
      }, "image/png");
    };
    img.onerror = function () { done(); };
    // A data: URL rather than an object URL -- some browsers taint a canvas
    // that has had an SVG image drawn into it from a blob, and a tainted
    // canvas cannot be read back with toBlob.
    img.src = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(doc.xml);
  }

  function button(label, title, onClick) {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = label;
    b.title = title;
    b.addEventListener("click", function (ev) {
      ev.preventDefault();
      ev.stopPropagation();
      onClick(b);
    });
    return b;
  }

  function attach() {
    document.querySelectorAll(".panel").forEach(function (panel) {
      // A panel wrapping other panels would otherwise claim its children's
      // figures as its own.
      if (panel.querySelector(".panel")) return;
      const h3 = panel.querySelector("h3");
      if (!h3 || h3.querySelector(".fig-export")) return;
      const svg = panel.querySelector("svg");
      const table = panel.querySelector("table");
      const wantsComparison = panel.hasAttribute("data-comparison-export")
        && typeof figureComparisonRows === "function";
      if (!svg && !table && !wantsComparison) return;

      const box = document.createElement("span");
      box.className = "fig-export";
      if (svg) {
        box.appendChild(button("SVG",
          "Download as vector art, captioned with the current configuration",
          function () { exportSVG(panel); }));
        box.appendChild(button("PNG",
          "Download as a " + PNG_SCALE + "x bitmap, captioned with the "
          + "current configuration",
          function (b) {
            b.disabled = true;
            exportPNG(panel, function () { b.disabled = false; });
          }));
      }
      if (table) {
        box.appendChild(button("CSV",
          "Download the whole table as CSV, including the rows below the fold",
          function () { exportTableCSV(panel, table); }));
        box.appendChild(button("COPY",
          "Copy the whole table to the clipboard, tab-separated: pastes "
          + "straight into a spreadsheet",
          function (b) {
            const m = tableMatrix(table);
            copyText(delimited(m.head, m.body, "\\t"), b);
          }));
      }
      if (wantsComparison) {
        box.appendChild(button("CSV \\u00d7 ALL",
          "Download every segmentation and network model as one table, for "
          + "comparing configurations without switching between them",
          function (b) { exportComparison(b); }));
      }
      h3.appendChild(box);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", attach);
  } else {
    attach();
  }
  // Exposed for testing: the same payloads the buttons save, unsaved.
  window.__figureExport = function (sel) {
    const panel = (typeof sel === "string") ? document.querySelector(sel) : sel;
    if (!panel) return null;
    return serialise(panel, provenanceOf(panel).caption || "");
  };
  window.__figureExport.table = function (sel, sep) {
    const panel = (typeof sel === "string") ? document.querySelector(sel) : sel;
    const table = panel && panel.querySelector("table");
    if (!table) return null;
    const m = tableMatrix(table);
    return delimited(m.head, m.body, sep || ",");
  };
  window.__figureExport.comparison = function () {
    if (typeof figureComparisonRows !== "function") return null;
    const d = figureComparisonRows();
    return delimited(d.header, d.rows, ",");
  };
})();
</script>"""


def figure_export_js() -> str:
    """The exporter itself.  Expects `figureProvenance(panel)` to exist."""
    return _JS.replace("__APP_VERSION__", __version__)


__all__ = ["figure_export_css", "figure_export_js",
           "CSS_PLACEHOLDER", "JS_PLACEHOLDER"]
