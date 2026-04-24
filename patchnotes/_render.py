"""
patchnotes._render
Render a Changelog to HTML, RSS, or plain text.
"""

from __future__ import annotations
import html as _html
import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ._parser import Changelog, Release

# ── Helpers ───────────────────────────────────────────────────────────────────

_BACKTICK = re.compile(r'`([^`]+)`')


def _md_inline(text: str, escape: bool = True) -> str:
    """Convert backtick spans to <code> and optionally HTML-escape."""
    if escape:
        text = _html.escape(text)
    return _BACKTICK.sub(r'<code>\1</code>', text)


_TYPE_COLORS = {
    "Added":      "#3dd68c",
    "Fixed":      "#60a5fa",
    "Changed":    "#facc15",
    "Removed":    "#f87171",
    "Breaking":   "#fb923c",
    "Security":   "#c084fc",
    "Deprecated": "#94a3b8",
}

_TYPE_EMOJI = {
    "Added":      "＋",
    "Fixed":      "✦",
    "Changed":    "◈",
    "Removed":    "−",
    "Breaking":   "⚠",
    "Security":   "🔒",
    "Deprecated": "⌛",
}


# ── HTML ──────────────────────────────────────────────────────────────────────

def to_html(changelog: "Changelog", full_page: bool = True) -> str:
    """
    Render a Changelog to HTML.

    Args:
        changelog: The parsed Changelog object.
        full_page: If True, wrap in a complete HTML document with styles.
                   If False, return a bare <div> fragment for embedding.

    Returns:
        HTML string.

    Example::

        cl = patchnotes.parse_file("CHANGELOG.md")
        print(patchnotes.to_html(cl))
        # or save it:
        with open("changelog.html", "w") as f:
            f.write(patchnotes.to_html(cl))
    """
    parts: list[str] = []

    for release in changelog.releases:
        has_breaking = bool(release.breaking_changes)
        date_str = str(release.release_date) if release.release_date else ""

        badges = ""
        if release.is_unreleased:
            badges += '<span class="pn-badge pn-unreleased">unreleased</span>'
        if has_breaking:
            badges += '<span class="pn-badge pn-breaking">breaking</span>'
        if release.yanked:
            badges += '<span class="pn-badge pn-yanked">yanked</span>'

        parts.append(
            f'<div class="pn-release">'
            f'<div class="pn-release-header">'
            f'<span class="pn-version">v{_html.escape(release.version)}</span>'
            + (f'<span class="pn-date">{date_str}</span>' if date_str else '')
            + badges
            + '</div>'
        )

        for type_name, entries in release.by_type.items():
            color = _TYPE_COLORS.get(type_name, "#888")
            emoji = _TYPE_EMOJI.get(type_name, "·")
            parts.append(
                f'<div class="pn-group">'
                f'<div class="pn-type-header" style="color:{color}">'
                f'<span class="pn-type-bar" style="background:{color}"></span>'
                f'{_html.escape(type_name)}</div>'
                f'<ul class="pn-entries">'
            )
            for entry in entries:
                parts.append(
                    f'<li class="pn-entry" style="border-left:3px solid {color}20">'
                    f'<span class="pn-dot" style="color:{color}">{emoji}</span>'
                    f'<span>{_md_inline(entry.text)}</span></li>'
                )
            parts.append('</ul></div>')

        parts.append('</div>')

    inner = "\n".join(parts)
    fragment = (
        f'<div class="pn-changelog" data-title="{_html.escape(changelog.title)}">'
        f'\n{inner}\n</div>'
    )

    if not full_page:
        return fragment

    css = _HTML_CSS
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_html.escape(changelog.title)} — Changelog</title>
<style>{css}</style>
</head>
<body>
<div class="pn-page">
  <h1 class="pn-title">{_html.escape(changelog.title)}</h1>
  {('<p class="pn-desc">' + _html.escape(changelog.description) + '</p>') if changelog.description else ''}
  {fragment}
</div>
</body>
</html>"""


_HTML_CSS = """
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body { background: #0d0f14; color: #dde3f0; font-family: system-ui, sans-serif;
       font-size: 15px; line-height: 1.6; padding: 40px 24px; }
.pn-page { max-width: 760px; margin: 0 auto; }
.pn-title { font-size: 28px; font-weight: 700; color: #fff;
            letter-spacing: -0.5px; margin-bottom: 6px; }
.pn-desc { color: #6b7a99; margin-bottom: 32px; }
.pn-release { background: #111520; border: 1px solid rgba(255,255,255,0.07);
              border-radius: 10px; padding: 24px; margin-bottom: 16px; }
.pn-release-header { display: flex; align-items: baseline; gap: 12px;
                     flex-wrap: wrap; margin-bottom: 18px;
                     padding-bottom: 14px; border-bottom: 1px solid rgba(255,255,255,0.06); }
.pn-version { font-family: monospace; font-size: 20px; font-weight: 700; color: #fff; }
.pn-date { font-family: monospace; font-size: 13px; color: #5a6480; }
.pn-badge { font-size: 10px; font-weight: 700; font-family: monospace;
            letter-spacing: .05em; padding: 2px 8px; border-radius: 4px;
            text-transform: uppercase; }
.pn-unreleased { background: rgba(56,189,248,.1); color: #38bdf8; }
.pn-breaking   { background: rgba(251,146,60,.1);  color: #fb923c; }
.pn-yanked     { background: rgba(248,113,113,.1); color: #f87171; }
.pn-group { margin-bottom: 16px; }
.pn-type-header { display: flex; align-items: center; gap: 8px;
                  font-size: 11px; font-weight: 700; font-family: monospace;
                  letter-spacing: .06em; text-transform: uppercase; margin-bottom: 8px; }
.pn-type-bar { width: 3px; height: 13px; border-radius: 2px; flex-shrink: 0; }
.pn-entries { list-style: none; display: flex; flex-direction: column; gap: 4px; }
.pn-entry { display: flex; gap: 10px; padding: 7px 12px; border-radius: 6px;
            background: rgba(255,255,255,0.03); font-size: 13.5px; }
.pn-entry:hover { background: rgba(255,255,255,0.05); }
.pn-dot { flex-shrink: 0; line-height: 1.5; }
.pn-entry code { font-family: monospace; font-size: 12px;
                 background: rgba(255,255,255,0.08); padding: 1px 5px;
                 border-radius: 3px; color: #a5b4fc; }
"""


# ── RSS ───────────────────────────────────────────────────────────────────────

def to_rss(
    changelog: "Changelog",
    feed_url: str = "",
    project_url: str = "",
) -> str:
    """
    Render a Changelog to an RSS 2.0 feed.

    Each versioned release becomes an <item>. Unreleased entries are skipped.

    Args:
        changelog:   The parsed Changelog object.
        feed_url:    URL where this RSS feed will be hosted (optional).
        project_url: URL of the project homepage (optional).

    Returns:
        RSS 2.0 XML string.

    Example::

        cl = patchnotes.parse_file("CHANGELOG.md")
        with open("changelog.rss", "w") as f:
            f.write(patchnotes.to_rss(cl, project_url="https://github.com/you/project"))
    """
    title = _html.escape(changelog.title)
    desc = _html.escape(changelog.description or f"Releases for {changelog.title}")
    link = _html.escape(project_url or feed_url or "")
    now = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")

    items: list[str] = []
    for release in changelog.releases:
        if release.is_unreleased:
            continue

        item_title = f"v{release.version}"
        if release.yanked:
            item_title += " [YANKED]"

        pub_date = ""
        if release.release_date:
            dt = datetime(
                release.release_date.year,
                release.release_date.month,
                release.release_date.day,
                tzinfo=timezone.utc,
            )
            pub_date = f"\n    <pubDate>{dt.strftime('%a, %d %b %Y %H:%M:%S +0000')}</pubDate>"

        # Build description as plain text grouped by type
        lines = []
        for type_name, entries in release.by_type.items():
            lines.append(f"{type_name}:")
            for e in entries:
                lines.append(f"  - {e.text}")
        content = _html.escape("\n".join(lines))

        item_link = _html.escape(project_url) if project_url else ""
        link_tag = f"\n    <link>{item_link}</link>" if item_link else ""

        items.append(
            f"  <item>\n"
            f"    <title>{_html.escape(item_title)}</title>{link_tag}"
            f"{pub_date}\n"
            f"    <guid isPermaLink=\"false\">{_html.escape(changelog.title)}-{release.version}</guid>\n"
            f"    <description><![CDATA[{content}]]></description>\n"
            f"  </item>"
        )

    items_str = "\n".join(items)
    link_tag = f"\n    <link>{link}</link>" if link else ""

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>{title}</title>{link_tag}
    <description>{desc}</description>
    <lastBuildDate>{now}</lastBuildDate>
{items_str}
  </channel>
</rss>"""


# ── Plain text ────────────────────────────────────────────────────────────────

def to_text(
    changelog: "Changelog",
    max_releases: int = 0,
    width: int = 72,
) -> str:
    """
    Render a Changelog to a plain text summary.

    Args:
        changelog:    The parsed Changelog object.
        max_releases: If > 0, only include this many releases (newest first).
                      0 means include all.
        width:        Line width for the separator. Default 72.

    Returns:
        Plain text string.

    Example::

        cl = patchnotes.parse_file("CHANGELOG.md")
        print(patchnotes.to_text(cl, max_releases=3))
    """
    sep = "─" * width
    lines: list[str] = []

    lines.append(changelog.title.upper())
    if changelog.description:
        lines.append(changelog.description)
    lines.append("")

    releases = changelog.releases
    if max_releases > 0:
        releases = releases[:max_releases]

    for release in releases:
        # Header
        version_str = f"v{release.version}"
        if release.release_date:
            version_str += f"  {release.release_date}"
        flags = []
        if release.is_unreleased:
            flags.append("UNRELEASED")
        if release.yanked:
            flags.append("YANKED")
        if flags:
            version_str += f"  [{', '.join(flags)}]"

        lines.append(sep)
        lines.append(version_str)
        lines.append("")

        for type_name, entries in release.by_type.items():
            lines.append(f"  {type_name}")
            for entry in entries:
                # Word-wrap long entries
                prefix = "    - "
                indent = " " * len(prefix)
                words = entry.text.split()
                current = prefix
                for word in words:
                    if len(current) + len(word) + 1 > width and current != prefix:
                        lines.append(current)
                        current = indent + word
                    else:
                        current = current + (" " if current != prefix else "") + word
                lines.append(current)
            lines.append("")

    lines.append(sep)
    return "\n".join(lines)
