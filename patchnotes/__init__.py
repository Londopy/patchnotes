"""
patchnotes — Parse Keep a Changelog formatted CHANGELOG.md files.

Basic usage::

    import patchnotes

    # From a file
    cl = patchnotes.parse_file("CHANGELOG.md")

    # From a GitHub repo (auto-fetches the raw file)
    cl = patchnotes.Changelog.from_github("Londopy", "patchnotes")

    # Query
    print(cl.latest())
    print(cl.diff("1.4.0", "2.1.0"))

    # Render
    html = patchnotes.to_html(cl)
    rss  = patchnotes.to_rss(cl, project_url="https://github.com/you/project")
    text = patchnotes.to_text(cl, max_releases=3)
"""

from ._parser import (
    parse,
    parse_file,
    Changelog,
    Release,
    Entry,
    ChangeType,
)
from ._render import (
    to_html,
    to_rss,
    to_text,
)

__version__ = "1.1.0"
__all__ = [
    "parse",
    "parse_file",
    "Changelog",
    "Release",
    "Entry",
    "ChangeType",
    "to_html",
    "to_rss",
    "to_text",
    "__version__",
]
