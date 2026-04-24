"""
patchnotes.py — Pure Python implementation
Parses Keep a Changelog (keepachangelog.com) formatted CHANGELOG.md files
into structured Python objects.
"""

import re
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
        return [e for e in self.entries if e.change_type == ChangeType.BREAKING
                or e.change_type == ChangeType.REMOVED]

    @property
    def by_type(self) -> dict[str, list[Entry]]:
        result: dict[str, list[Entry]] = {}
        for entry in self.entries:
            result.setdefault(entry.change_type.value, []).append(entry)
        return result

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
        for r in self.releases:
            if not r.is_unreleased:
                return r
        return None

    def unreleased(self) -> Optional[Release]:
        for r in self.releases:
            if r.is_unreleased:
                return r
        return None

    def since_version(self, version: str) -> list[Release]:
        """Return all releases newer than the given version."""
        result = []
        for r in self.releases:
            if r.is_unreleased:
                result.append(r)
                continue
            if r.version == version:
                break
            result.append(r)
        return result

    def get_version(self, version: str) -> Optional[Release]:
        for r in self.releases:
            if r.version == version:
                return r
        return None

    def all_breaking_changes(self) -> list[tuple[str, Entry]]:
        """Return (version, entry) pairs for all breaking changes."""
        out = []
        for r in self.releases:
            for e in r.breaking_changes:
                out.append((r.version, e))
        return out

    def diff(self, from_version: str, to_version: str) -> list[Release]:
        """Return releases between two versions (exclusive of from_version)."""
        collecting = False
        result = []
        for r in self.releases:
            if r.is_unreleased:
                continue
            if r.version == to_version:
                collecting = True
            if collecting:
                result.append(r)
            if r.version == from_version:
                break
        return result

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
        # Top-level title
        if line.startswith('# ') and in_header:
            changelog.title = line[2:].strip()
            continue

        # Collect description lines before first release
        if in_header and not line.startswith('## '):
            if line.strip() and not line.startswith('#'):
                changelog.description += line.strip() + ' '
            continue

        # Unreleased block
        if UNRELEASED_HEADER.match(line):
            in_header = False
            current_release = Release(version="Unreleased", release_date=None, is_unreleased=True)
            changelog.releases.append(current_release)
            continue

        # Versioned release header
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

        # Change type subheader (### Added, ### Fixed, etc.)
        m = CHANGE_TYPE_HEADER.match(line)
        if m and current_release is not None:
            label = m.group(1).strip().lower()
            current_type = _TYPE_MAP.get(label, ChangeType.CHANGED)
            continue

        # Bullet entry
        m = BULLET.match(line)
        if m and current_release is not None:
            current_release.entries.append(Entry(text=m.group(1).strip(),
                                                  change_type=current_type))

    changelog.description = changelog.description.strip()
    return changelog


def parse_file(path: str) -> Changelog:
    """Parse a CHANGELOG.md file from disk."""
    with open(path, 'r', encoding='utf-8') as f:
        return parse(f.read())
