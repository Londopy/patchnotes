"""
patchnotes._parser
Parses Keep a Changelog (keepachangelog.com) formatted CHANGELOG.md files
into structured Python objects.
"""

import re
import json
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from datetime import date
from typing import Optional
from enum import Enum


class ChangeType(str, Enum):
    ADDED = "Added"
    CHANGED = "Changed"
    DEPRECATED = "Deprecated"
    REMOVED = "Removed"
    FIXED = "Fixed"
    SECURITY = "Security"
    BREAKING = "Breaking"


@dataclass
class Entry:
    """A single changelog entry (one bullet point)."""
    text: str
    change_type: ChangeType

    def __repr__(self):
        return f"Entry({self.change_type.value}: {self.text!r})"

    def to_dict(self) -> dict:
        return {"text": self.text, "change_type": self.change_type.value}


def _parse_semver(version: str) -> tuple:
    """Parse a version string into a sortable tuple."""
    if version.lower() == "unreleased":
        return (float("inf"),) * 3
    v = version.lstrip("v")
    numeric = re.split(r"[-+]", v)[0]
    parts = numeric.split(".")
    result = []
    for p in parts[:3]:
        try:
            result.append(int(p))
        except ValueError:
            result.append(0)
    while len(result) < 3:
        result.append(0)
    return tuple(result)


@dataclass
class Release:
    """A single versioned release block."""
    version: str
    release_date: Optional[date]
    is_unreleased: bool
    entries: list[Entry] = field(default_factory=list)
    yanked: bool = False

    @property
    def breaking_changes(self) -> list[Entry]:
        return [e for e in self.entries
                if e.change_type in (ChangeType.BREAKING, ChangeType.REMOVED)]

    @property
    def by_type(self) -> dict[str, list[Entry]]:
        result: dict[str, list[Entry]] = {}
        for entry in self.entries:
            result.setdefault(entry.change_type.value, []).append(entry)
        return result

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "release_date": self.release_date.isoformat() if self.release_date else None,
            "is_unreleased": self.is_unreleased,
            "yanked": self.yanked,
            "entries": [e.to_dict() for e in self.entries],
            "by_type": {k: [e.to_dict() for e in v] for k, v in self.by_type.items()},
        }

    def __repr__(self):
        d = self.release_date or "unreleased"
        return f"Release(v{self.version}, {d}, {len(self.entries)} entries)"


@dataclass
class Changelog:
    """The full parsed changelog."""
    releases: list[Release] = field(default_factory=list)
    title: str = "Changelog"
    description: str = ""

    def latest(self) -> Optional[Release]:
        """Return the highest versioned (non-unreleased) release."""
        candidates = [r for r in self.releases if not r.is_unreleased]
        if not candidates:
            return None
        return max(candidates, key=lambda r: _parse_semver(r.version))

    def unreleased(self) -> Optional[Release]:
        for r in self.releases:
            if r.is_unreleased:
                return r
        return None

    def since_version(self, version: str) -> list[Release]:
        """Return all releases strictly newer than the given version."""
        threshold = _parse_semver(version)
        return [r for r in self.releases if _parse_semver(r.version) > threshold]

    def get_version(self, version: str) -> Optional[Release]:
        for r in self.releases:
            if r.version == version:
                return r
        return None

    def all_breaking_changes(self) -> list[tuple[str, Entry]]:
        """Return (version, entry) pairs for all breaking/removed entries."""
        out = []
        for r in self.releases:
            for e in r.breaking_changes:
                out.append((r.version, e))
        return out

    def diff(self, from_version: str, to_version: str) -> list[Release]:
        """
        Return all releases strictly between from_version (exclusive)
        and to_version (inclusive), ordered newest-first.
        """
        from_v = _parse_semver(from_version)
        to_v = _parse_semver(to_version)
        if from_v >= to_v:
            raise ValueError(
                f"from_version ({from_version}) must be older than to_version ({to_version})"
            )
        return [
            r for r in self.releases
            if not r.is_unreleased
            and from_v < _parse_semver(r.version) <= to_v
        ]

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "description": self.description,
            "releases": [r.to_dict() for r in self.releases],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)

    @classmethod
    def from_url(cls, url: str) -> "Changelog":
        """
        Fetch and parse a remote CHANGELOG.md from any URL.

        Example::

            cl = Changelog.from_url(
                "https://raw.githubusercontent.com/user/repo/main/CHANGELOG.md"
            )
        """
        req = urllib.request.Request(
            url, headers={"User-Agent": "patchnotes-python/1.0"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            text = resp.read().decode("utf-8", errors="replace")
        return parse(text)

    @classmethod
    def from_github(
        cls,
        owner: str,
        repo: str,
        branch: str = "main",
        filename: str = "CHANGELOG.md",
    ) -> "Changelog":
        """
        Fetch and parse a CHANGELOG.md directly from a GitHub repository.

        Automatically falls back to the 'master' branch if 'main' returns 404.

        Args:
            owner:    GitHub username or org (e.g. "Londopy").
            repo:     Repository name (e.g. "patchnotes").
            branch:   Branch name. Defaults to "main".
            filename: File to fetch. Defaults to "CHANGELOG.md".
                      Common alternatives: "CHANGES.md", "HISTORY.md", "NEWS.md".

        Raises:
            ValueError: If the file cannot be found.

        Example::

            cl = Changelog.from_github("Londopy", "patchnotes")
            cl = Changelog.from_github("psf", "requests", filename="HISTORY.md")
        """
        def _fetch(branch_name: str) -> Optional[str]:
            url = (
                f"https://raw.githubusercontent.com/"
                f"{owner}/{repo}/{branch_name}/{filename}"
            )
            req = urllib.request.Request(
                url, headers={"User-Agent": "patchnotes-python/1.0"}
            )
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    return resp.read().decode("utf-8", errors="replace")
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    return None
                raise

        text = _fetch(branch)
        if text is None and branch == "main":
            text = _fetch("master")
        if text is None:
            raise ValueError(
                f"Could not find {filename!r} in {owner}/{repo} "
                f"on branch {branch!r} (also tried 'master'). "
                f"Check the owner, repo, branch, and filename."
            )
        return parse(text)

    def __repr__(self):
        return f"Changelog({len(self.releases)} releases)"


# ── Parser ────────────────────────────────────────────────────────────────────

VERSION_HEADER = re.compile(
    r'^##\s+\[(?P<version>[^\]]+)\]'
    r'(?:\s+-\s+(?P<date>\d{4}-\d{2}-\d{2}))?'
    r'(?:\s+\[YANKED\])?',
    re.IGNORECASE
)
UNRELEASED_HEADER = re.compile(r'^##\s+\[Unreleased\]', re.IGNORECASE)
CHANGE_TYPE_HEADER = re.compile(r'^###\s+(.+)', re.IGNORECASE)
BULLET = re.compile(r'^[-*]\s+(.+)')
YANKED = re.compile(r'\[YANKED\]', re.IGNORECASE)

_TYPE_MAP = {t.value.lower(): t for t in ChangeType}


def parse(text: str) -> Changelog:
    """Parse a Keep a Changelog formatted string into a Changelog object."""
    changelog = Changelog()
    lines = text.splitlines()

    current_release: Optional[Release] = None
    current_type: ChangeType = ChangeType.CHANGED
    in_header = True

    for line in lines:
        if line.startswith('# ') and in_header:
            changelog.title = line[2:].strip()
            continue
        if in_header and not line.startswith('## '):
            if line.strip() and not line.startswith('#'):
                changelog.description += line.strip() + ' '
            continue
        if UNRELEASED_HEADER.match(line):
            in_header = False
            current_release = Release(version="Unreleased", release_date=None, is_unreleased=True)
            changelog.releases.append(current_release)
            continue
        m = VERSION_HEADER.match(line)
        if m:
            in_header = False
            ver = m.group('version')
            raw_date = m.group('date')
            parsed_date = date.fromisoformat(raw_date) if raw_date else None
            yanked = bool(YANKED.search(line))
            current_release = Release(version=ver, release_date=parsed_date,
                                      is_unreleased=False, yanked=yanked)
            changelog.releases.append(current_release)
            continue
        m = CHANGE_TYPE_HEADER.match(line)
        if m and current_release is not None:
            label = m.group(1).strip().lower()
            current_type = _TYPE_MAP.get(label, ChangeType.CHANGED)
            continue
        m = BULLET.match(line)
        if m and current_release is not None:
            current_release.entries.append(
                Entry(text=m.group(1).strip(), change_type=current_type)
            )

    changelog.description = changelog.description.strip()
    return changelog


def parse_file(path: str) -> Changelog:
    """Parse a CHANGELOG.md file from disk."""
    with open(path, 'r', encoding='utf-8') as f:
        return parse(f.read())
