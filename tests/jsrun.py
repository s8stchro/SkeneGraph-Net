"""Running one piece of the page's JavaScript.

Most of the chart code needs a browser, but a few pieces are plain
functions of their arguments -- the scatter's label placement, the figure
caption's wrap -- and those can be cut out of the generated page and run.

A script file, not `node -e`: where `node` on the PATH is a .CMD shim, a
multi-line `-e` script is cut at the first newline and the shim exits 0
having printed nothing, which would fail the tests for the environment
rather than for the code.
"""

from __future__ import annotations

import json
import pathlib
import re
import shutil
import subprocess
import tempfile

import pytest

NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None,
                                reason="runs the page's JavaScript in node")


def page_function(source: str, name: str) -> str:
    """One function of the page, cut out by counting braces -- enough for a
    function with no brace inside a string.  Indented definitions (the
    exporter's, inside its IIFE) are found as well as top-level ones."""
    m = re.search(rf"^[ \t]*function {re.escape(name)}\(", source, re.M)
    assert m, f"no function {name} in the page"
    start = m.start()
    depth = 0
    for j in range(source.index("{", source.index(")", start)), len(source)):
        depth += {"{": 1, "}": -1}.get(source[j], 0)
        if depth == 0:
            return source[start:j + 1]
    raise AssertionError(f"{name} does not close")


def run_node(script: str, payload) -> object:
    """Run `script` in node, handing it `payload` as JSON on stdin, and
    return the JSON it writes back."""
    with tempfile.TemporaryDirectory() as tmp:
        js = pathlib.Path(tmp) / "run.js"
        js.write_text(script, encoding="utf-8")
        # UTF-8 both ways: node writes it, and a caption carries middots and
        # Greek, which the system code page would mangle on the way back.
        run = subprocess.run([NODE, str(js)], input=json.dumps(payload),
                             capture_output=True, text=True, check=True,
                             encoding="utf-8")
    if not run.stdout.strip():
        raise AssertionError(
            f"{NODE} ran the script and printed nothing"
            + (f"; stderr: {run.stderr.strip()[:200]}" if run.stderr.strip() else ""))
    return json.loads(run.stdout)
