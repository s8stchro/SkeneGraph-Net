"""Single source of the application version.

`app.py` re-exports it, so `from app import __version__` keeps working.  The
dashboards import it from here instead: they cannot import `app`, which
imports them.  The figure exporter stamps it into every exported figure, so a
graphic in an article can be traced to the build that drew it.

Keep in step with `CITATION.cff` and `.zenodo.json`, which cannot import.
"""

__version__ = "2.0.0"

__all__ = ["__version__"]
