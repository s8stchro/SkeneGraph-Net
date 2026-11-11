"""Third-party libraries, inlined so a dashboard works offline.

Both dashboards draw with d3 and typeset the Methods tab with KaTeX.  Loaded
from a CDN, a page opened without a network shows its frame and nothing
else: the first d3 call throws and no chart is drawn.  A dashboard is meant
to be copied onto a projector laptop or a USB stick, so the libraries travel
inside it instead.

The pinned files live in `vendor/` (d3 7.9.0, KaTeX 0.16.9, both with their
licences).  KaTeX's stylesheet points at its fonts by relative URL; each
woff2 face is rewritten to a data URI and the woff/ttf fallbacks are
dropped, since every browser that runs the dashboards reads woff2.

Inserted via a literal placeholder and `str.replace`, like the Methods panel
and the figure exporter, so the libraries' braces need no escaping for
`str.format`.
"""

from __future__ import annotations

import base64
import functools
import re
from pathlib import Path

VENDOR_DIR = Path(__file__).resolve().parent / "vendor"
PLACEHOLDER = "<!--VENDOR_ASSETS-->"

# One @font-face `src:` list: the woff2 entry first, then any fallbacks.
_FONT_SRC = re.compile(
    r'src:url\(fonts/([\w-]+)\.woff2\) format\("woff2"\)'
    r'(?:,url\([^)]*\) format\("[^"]*"\))*')


def _read(rel: str) -> str:
    return (VENDOR_DIR / rel).read_text(encoding="utf-8")


def _script(rel: str) -> str:
    body = _read(rel)
    # The HTML parser ends the element at the first `</script`, whatever
    # the JavaScript around it means.
    if re.search(r"</script", body, re.I):
        raise ValueError(f"vendor/{rel} contains '</script' and cannot be inlined")
    return f"<script>/* vendor/{rel} */\n{body}\n</script>"


def _katex_css() -> str:
    def inline(m: re.Match) -> str:
        font = (VENDOR_DIR / "katex" / "fonts" / f"{m.group(1)}.woff2").read_bytes()
        data = base64.b64encode(font).decode("ascii")
        return f'src:url(data:font/woff2;base64,{data}) format("woff2")'

    css = _FONT_SRC.sub(inline, _read("katex/katex.min.css"))
    if "url(fonts/" in css:
        raise ValueError("vendor/katex/katex.min.css has a font the rewrite missed")
    return f"<style>/* vendor/katex/katex.min.css */\n{css}\n</style>"


@functools.lru_cache(maxsize=1)
def vendor_assets_html() -> str:
    """d3, KaTeX and its auto-render extension, ready for a page's <head>."""
    return "\n".join([
        _script("d3/d3.min.js"),
        _katex_css(),
        _script("katex/katex.min.js"),
        _script("katex/contrib/auto-render.min.js"),
    ])


__all__ = ["vendor_assets_html", "PLACEHOLDER"]
