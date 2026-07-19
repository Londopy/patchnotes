"""
patchnotes._depdiff
Dependency changelog diffs: what changed between two versions of a
package you depend on?

    patchnotes dep requests 2.30.0 2.32.0

Resolves the package's GitHub repository via PyPI metadata, fetches its
changelog, and surfaces the breaking and security changes between the
two versions — built for reviewing Dependabot/Renovate bump PRs.
Best-effort by nature: it needs the dependency to keep a parseable
changelog on GitHub.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import TYPE_CHECKING, Optional

from ._models import Changelog, ChangeType

if TYPE_CHECKING:
    from ._models import Release

_GITHUB_URL = re.compile(
    r"https?://github\.com/(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+)", re.IGNORECASE
)
#: changelog filenames tried, in order
CHANGELOG_FILENAMES = (
    "CHANGELOG.md", "CHANGES.md", "HISTORY.md", "NEWS.md", "CHANGELOG.rst",
)


def _get_json(url: str) -> dict:
    req = urllib.request.Request(
        url, headers={"User-Agent": "patchnotes-python/2.2"}
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def find_github_repo(package: str) -> tuple[str, str]:
    """Resolve a PyPI package name to (owner, repo) via its metadata."""
    try:
        data = _get_json(f"https://pypi.org/pypi/{package}/json")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise ValueError(f"package {package!r} not found on PyPI") from None
        raise
    info = data.get("info", {})
    candidates = list((info.get("project_urls") or {}).values())
    candidates.append(info.get("home_page") or "")
    for url in candidates:
        m = _GITHUB_URL.search(url or "")
        if m:
            return m.group("owner"), m.group("repo").removesuffix(".git")
    raise ValueError(
        f"couldn't find a GitHub repository in {package!r}'s PyPI metadata"
    )


def fetch_dep_changelog(owner: str, repo: str) -> Changelog:
    """Fetch and parse a dependency's changelog, trying common filenames."""
    last_error: Optional[Exception] = None
    for filename in CHANGELOG_FILENAMES:
        try:
            cl = Changelog.from_github(owner, repo, filename=filename)
        except (ValueError, urllib.error.URLError) as e:
            last_error = e
            continue
        if cl.releases:
            return cl
    raise ValueError(
        f"couldn't fetch a parseable changelog from {owner}/{repo} "
        f"(tried {', '.join(CHANGELOG_FILENAMES)}). "
        f"Last error: {last_error}"
    )


_HIGHLIGHT_TYPES = (ChangeType.BREAKING, ChangeType.REMOVED,
                    ChangeType.SECURITY, ChangeType.DEPRECATED)


def render_dep_diff(
    cl: Changelog,
    package: str,
    from_version: str,
    to_version: str,
    show_all: bool = False,
) -> tuple[str, int]:
    """
    Render the releases between two versions, surfacing breaking/security
    changes. Returns (text, flagged_count) where flagged_count is the
    number of breaking/removed/security/deprecated entries found.
    """
    releases = cl.diff(from_version, to_version)
    lines: list[str] = [
        f"{package}: {from_version} -> {to_version} "
        f"({len(releases)} release(s) in between)"
    ]
    flagged = 0
    if not releases:
        lines.append(
            "  No releases found in this range — the changelog may use "
            "different version numbers."
        )
        return "\n".join(lines), 0

    for r in releases:
        date_str = f"  {r.release_date}" if r.release_date else ""
        yank = "  [YANKED]" if r.yanked else ""
        lines.append("")
        lines.append(f"  v{r.version}{date_str}{yank}")
        shown = False
        for type_name, entries in r.by_type.items():
            important = any(
                e.change_type in _HIGHLIGHT_TYPES for e in entries
            )
            if not show_all and not important:
                continue
            for e in entries:
                marker = "!" if e.change_type in _HIGHLIGHT_TYPES else "-"
                lines.append(f"    {marker} [{type_name}] {e.text}")
                if e.change_type in _HIGHLIGHT_TYPES:
                    flagged += 1
                shown = True
        if not shown:
            lines.append("    (no breaking/security changes)")

    lines.append("")
    if flagged:
        lines.append(
            f"  {flagged} breaking/security-relevant change(s) flagged (!). "
            "Review before merging."
        )
    else:
        lines.append("  No breaking or security changes flagged.")
    return "\n".join(lines), flagged
