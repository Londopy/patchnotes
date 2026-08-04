"""
patchnotes.mkdocs_plugin
Render your changelog into your mkdocs documentation site.

Setup (``pip install patchnotes mkdocs``)::

    # mkdocs.yml
    plugins:
      - search
      - patchnotes:
          file: CHANGELOG.md   # relative to mkdocs.yml (default)

Then put a marker in any docs page (e.g. ``docs/changelog.md``)::

    # Changelog

    <!-- patchnotes -->

The marker is replaced with the parsed, styled changelog at build time.
Off-spec changelogs render best-effort (the parser is lenient); run
``patchnotes CHANGELOG.md validate`` in CI to keep it clean.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Optional

try:
    from mkdocs.config import config_options
    from mkdocs.config.base import LegacyConfig
    from mkdocs.plugins import BasePlugin
except ImportError as e:  # pragma: no cover
    raise ImportError(
        "The patchnotes mkdocs plugin requires mkdocs. "
        "Install it with: pip install mkdocs"
    ) from e

if TYPE_CHECKING:
    from mkdocs.config.defaults import MkDocsConfig
    from mkdocs.structure.files import Files
    from mkdocs.structure.pages import Page

MARKER = "<!-- patchnotes -->"

# Scoped styles: only .pn-* selectors, safe to embed in any docs theme.
_EMBED_CSS = """
<style>
.pn-changelog { --pn-fg: inherit; }
.pn-changelog .pn-release { border: 1px solid rgba(128,128,128,.25);
  border-radius: 10px; padding: 20px; margin: 16px 0; }
.pn-changelog .pn-release-header { display: flex; align-items: baseline;
  gap: 12px; flex-wrap: wrap; margin-bottom: 14px; padding-bottom: 10px;
  border-bottom: 1px solid rgba(128,128,128,.2); }
.pn-changelog .pn-version { font-family: monospace; font-size: 1.2em;
  font-weight: 700; }
.pn-changelog .pn-date { font-family: monospace; font-size: .85em;
  opacity: .6; }
.pn-changelog .pn-badge { font-size: .65em; font-weight: 700;
  font-family: monospace; letter-spacing: .05em; padding: 2px 8px;
  border-radius: 4px; text-transform: uppercase;
  background: rgba(128,128,128,.15); }
.pn-changelog .pn-type-header { display: flex; align-items: center; gap: 8px;
  font-size: .75em; font-weight: 700; font-family: monospace;
  letter-spacing: .06em; text-transform: uppercase; margin: 12px 0 6px; }
.pn-changelog .pn-type-bar { width: 3px; height: 13px; border-radius: 2px; }
.pn-changelog .pn-entries { list-style: none; margin: 0; padding: 0;
  display: flex; flex-direction: column; gap: 4px; }
.pn-changelog .pn-entry { display: flex; gap: 10px; padding: 6px 10px;
  border-radius: 6px; background: rgba(128,128,128,.07); font-size: .9em; }
.pn-changelog .pn-dot { flex-shrink: 0; }
.pn-changelog code { font-family: monospace; font-size: .9em; }
</style>
"""


# mkdocs' BasePlugin.__init_subclass__ carries no annotations, so mypy flags
# subclassing it as a call to an untyped function; mkdocs ships no stubs to fix
# that upstream. When mkdocs is not installed at all (it is an optional extra),
# BasePlugin resolves to Any instead and 'misc' fires rather than
# 'no-untyped-call' — hence both codes, with warn_unused_ignores disabled for
# this module in pyproject.toml.
class PatchnotesPlugin(BasePlugin[LegacyConfig]):  # type: ignore[no-untyped-call,misc]
    """Replaces ``<!-- patchnotes -->`` markers with the rendered changelog."""

    config_scheme = (
        ("file", config_options.Type(str, default="CHANGELOG.md")),
    )

    def on_page_markdown(
        self,
        markdown: str,
        page: Optional[Page] = None,
        config: Optional[MkDocsConfig] = None,
        files: Optional[Files] = None,
    ) -> str:
        if MARKER not in markdown:
            return markdown

        from patchnotes import parse_file, to_html

        path = self.config["file"]
        if config is not None and not os.path.isabs(path):
            base = os.path.dirname(config.get("config_file_path") or "") or "."
            path = os.path.join(base, path)

        try:
            cl = parse_file(path)
        except OSError as e:
            raise FileNotFoundError(
                f"patchnotes plugin: cannot read changelog at {path!r} ({e}). "
                "Set the 'file' option to the changelog path relative to "
                "mkdocs.yml."
            ) from e

        fragment = to_html(cl, full_page=False)
        return markdown.replace(MARKER, _EMBED_CSS + "\n" + fragment)
