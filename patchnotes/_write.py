"""
patchnotes._write
Write a Changelog back out as Keep a Changelog markdown or YAML.

Enables round-tripping (parse -> modify -> write), format conversion,
and auto-fixing off-spec changelogs.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ._models import Changelog

_COMPARE_RE = re.compile(r"^(?P<base>.+?)/compare/(?P<from>.+?)\.\.\.(?P<to>.+)$")


def _generated_links(
    changelog: "Changelog", repo_url: str, tag_prefix: str = "v"
) -> dict:
    """Generate Keep a Changelog compare-link footnotes for every release."""
    repo_url = repo_url.rstrip("/")
    links: dict[str, str] = {}
    versioned = [r for r in changelog.releases if not r.is_unreleased]
    oldest_first = list(reversed(versioned))
    prev = None
    for r in oldest_first:
        tag = f"{tag_prefix}{r.version}"
        if prev is None:
            links[r.version] = f"{repo_url}/releases/tag/{tag}"
        else:
            links[r.version] = f"{repo_url}/compare/{tag_prefix}{prev}...{tag}"
        prev = r.version
    if changelog.unreleased() is not None and prev is not None:
        links["Unreleased"] = f"{repo_url}/compare/{tag_prefix}{prev}...HEAD"
    # Emit newest-first to match the release order in the document.
    ordered: dict[str, str] = {}
    if "Unreleased" in links:
        ordered["Unreleased"] = links["Unreleased"]
    for r in versioned:
        if r.version in links:
            ordered[r.version] = links[r.version]
    return ordered


def infer_repo_url(changelog: "Changelog") -> Optional[str]:
    """Infer the repository URL from any existing compare link, or None."""
    for url in changelog.links.values():
        m = _COMPARE_RE.match(url)
        if m:
            return m.group("base")
    return None


def to_markdown(
    changelog: "Changelog",
    repo_url: Optional[str] = None,
    tag_prefix: str = "v",
) -> str:
    """
    Render a Changelog to spec-compliant Keep a Changelog markdown.

    Args:
        changelog:  The Changelog to write.
        repo_url:   If given (e.g. "https://github.com/you/project"),
                    compare-link footnotes are (re)generated for every
                    release. If omitted, existing ``changelog.links``
                    are written as-is.
        tag_prefix: Tag prefix used for generated links. Default "v".

    Example::

        cl = patchnotes.parse_file("CHANGELOG.md")
        text = patchnotes.to_markdown(cl, repo_url="https://github.com/you/project")
    """
    lines: list[str] = [f"# {changelog.title}"]

    if changelog.description:
        lines.append("")
        lines.append(changelog.description)

    for r in changelog.releases:
        lines.append("")
        if r.is_unreleased:
            lines.append("## [Unreleased]")
        else:
            header = f"## [{r.version}]"
            if r.release_date:
                header += f" - {r.release_date.isoformat()}"
            if r.yanked:
                header += " [YANKED]"
            lines.append(header)
        for type_name, entries in r.by_type.items():
            lines.append("")
            lines.append(f"### {type_name}")
            lines.append("")
            for e in entries:
                lines.append(f"- {e.text}")

    links = (
        _generated_links(changelog, repo_url, tag_prefix)
        if repo_url
        else dict(changelog.links)
    )
    if links:
        lines.append("")
        for name, url in links.items():
            lines.append(f"[{name}]: {url}")

    return "\n".join(lines) + "\n"


def to_yaml(changelog: "Changelog") -> str:
    """
    Render a Changelog to the patchnotes YAML schema.

    The output round-trips: ``parse(to_yaml(cl), format="yaml")`` yields an
    equivalent changelog. Compare links are a markdown concept and are not
    included.

    Example::

        cl = patchnotes.parse_file("CHANGELOG.md")
        with open("changelog.yml", "w") as f:
            f.write(patchnotes.to_yaml(cl))
    """
    import yaml

    data: dict = {"title": changelog.title}
    if changelog.description:
        data["description"] = changelog.description

    releases = []
    for r in changelog.releases:
        item: dict = {}
        if r.is_unreleased:
            item["unreleased"] = True
        else:
            item["version"] = r.version
        if r.release_date:
            item["date"] = r.release_date.isoformat()
        if r.yanked:
            item["yanked"] = True
        if r.entries:
            item["changes"] = {
                type_name.lower(): [e.text for e in entries]
                for type_name, entries in r.by_type.items()
            }
        releases.append(item)
    data["releases"] = releases

    return yaml.safe_dump(
        data, sort_keys=False, allow_unicode=True, width=88
    )
