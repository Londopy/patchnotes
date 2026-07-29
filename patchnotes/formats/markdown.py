"""
patchnotes.formats.markdown

Keep a Changelog (keepachangelog.com) markdown parser.

Lenient and line-number aware: malformed constructs become
``ValidationIssue`` records on the returned ``Changelog`` instead of
exceptions, and the parser recovers with the most sensible interpretation.
"""

from __future__ import annotations

import re
from datetime import date

from .. import _validation as _v
from .._models import Changelog, ChangeType, Entry, Release
from .._validation import Severity, ValidationIssue
from . import FormatParser

VERSION_HEADER = re.compile(
    r'^##\s+\[(?P<version>[^\]]+)\]'
    r'(?:\s*[-–—:]?\s*(?P<date>\S+))?'
    r'(?P<rest>.*)$',
    re.IGNORECASE,
)
# Stricter variant used to distinguish "spec-perfect" from "recovered".
SPEC_DATE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
LOOSE_DATE_FORMATS = (
    ("%Y/%m/%d", re.compile(r'^\d{4}/\d{2}/\d{2}$')),
    ("%d-%m-%Y", re.compile(r'^\d{2}-\d{2}-\d{4}$')),
    ("%Y.%m.%d", re.compile(r'^\d{4}\.\d{2}\.\d{2}$')),
)
# Headers without brackets: "## 1.2.0 - 2024-01-01" (common off-spec style)
BARE_VERSION_HEADER = re.compile(
    r'^##\s+(?P<version>v?\d+(?:\.\d+){0,2}(?:[-+][\w.]+)?)'
    r'(?:\s*[-–—:]?\s*(?P<date>\S+))?'
    r'(?P<rest>.*)$'
)
UNRELEASED_HEADER = re.compile(r'^##\s+\[?Unreleased\]?\s*$', re.IGNORECASE)
CHANGE_TYPE_HEADER = re.compile(r'^###\s+(.+)', re.IGNORECASE)
BULLET = re.compile(r'^\s*[-*+]\s+(.+)')
CONTINUATION = re.compile(r'^\s{2,}(\S.*)$')
LINK_DEF = re.compile(r'^\[([^\]]+)\]:\s*(\S+)\s*$')
# RST/setext style: "2.32.3 (2024-05-29)" underlined with ---- or ====
SETEXT_UNDERLINE = re.compile(r'^[-=~^]{3,}\s*$')
SETEXT_VERSION = re.compile(
    r'^\s*v?(?P<version>\d+(?:\.\d+){0,3}[\w.-]*)\s*'
    r'(?:\((?P<date>[^)]+)\))?\s*$'
)
YANKED = re.compile(r'\[YANKED\]', re.IGNORECASE)

_TYPE_MAP = {t.value.lower(): t for t in ChangeType}
# Common aliases seen in the wild -> canonical Keep a Changelog type
_TYPE_ALIASES = {
    "add": ChangeType.ADDED,
    "new": ChangeType.ADDED,
    "features": ChangeType.ADDED,
    "feature": ChangeType.ADDED,
    "fix": ChangeType.FIXED,
    "fixes": ChangeType.FIXED,
    "bugfixes": ChangeType.FIXED,
    "bug fixes": ChangeType.FIXED,
    "change": ChangeType.CHANGED,
    "changes": ChangeType.CHANGED,
    "improved": ChangeType.CHANGED,
    "improvements": ChangeType.CHANGED,
    "remove": ChangeType.REMOVED,
    "removals": ChangeType.REMOVED,
    "deprecate": ChangeType.DEPRECATED,
    "breaking changes": ChangeType.BREAKING,
    "breaking change": ChangeType.BREAKING,
}


def _parse_date(
    raw: str, lineno: int, issues: list[ValidationIssue]
) -> date | None:
    """Parse a release date, recording an issue if it's off-spec."""
    from datetime import datetime

    raw = raw.strip()
    if SPEC_DATE.match(raw):
        try:
            return date.fromisoformat(raw)
        except ValueError:
            issues.append(ValidationIssue(
                _v.BAD_DATE,
                f"invalid calendar date {raw!r}",
                Severity.ERROR, lineno,
            ))
            return None
    for fmt, pattern in LOOSE_DATE_FORMATS:
        if pattern.match(raw):
            try:
                parsed = datetime.strptime(raw, fmt).date()
            except ValueError:
                continue
            issues.append(ValidationIssue(
                _v.BAD_DATE,
                f"date {raw!r} is not ISO 8601 (expected YYYY-MM-DD); "
                f"interpreted as {parsed.isoformat()}",
                Severity.ERROR, lineno,
            ))
            return parsed
    issues.append(ValidationIssue(
        _v.BAD_DATE,
        f"unparseable date {raw!r} (expected YYYY-MM-DD)",
        Severity.ERROR, lineno,
    ))
    return None


class MarkdownFormat(FormatParser):
    """Keep a Changelog markdown (the default format)."""

    name = "markdown"
    extensions = (".md", ".markdown")

    def sniff(self, text: str) -> bool:
        return bool(re.search(r'^##\s+\[', text, re.MULTILINE))

    def parse(self, text: str) -> Changelog:
        changelog = Changelog()
        issues = changelog.issues
        lines = self._normalize_setext(text.splitlines(), issues)

        current_release: Release | None = None
        current_type: ChangeType = ChangeType.CHANGED
        in_header = True

        for lineno, line in enumerate(lines, start=1):
            if line.startswith('# ') and in_header:
                changelog.title = line[2:].strip()
                continue
            m = LINK_DEF.match(line)
            if m:
                # Keep a Changelog compare-link footnote: [1.2.0]: https://...
                changelog.links[m.group(1)] = m.group(2)
                continue
            if in_header and not line.startswith('## '):
                bullet = BULLET.match(line)
                if bullet:
                    issues.append(ValidationIssue(
                        _v.ENTRY_OUTSIDE_RELEASE,
                        f"entry {bullet.group(1).strip()!r} appears before any "
                        "release block and was skipped",
                        Severity.WARNING, lineno,
                    ))
                elif line.strip() and not line.startswith('#'):
                    changelog.description += line.strip() + ' '
                continue

            if UNRELEASED_HEADER.match(line):
                in_header = False
                if '[' not in line:
                    issues.append(ValidationIssue(
                        _v.MALFORMED_HEADER,
                        "'## Unreleased' should be written as '## [Unreleased]'",
                        Severity.WARNING, lineno,
                    ))
                current_release = Release(
                    version="Unreleased", release_date=None, is_unreleased=True
                )
                changelog.releases.append(current_release)
                continue

            release = self._try_release_header(line, lineno, issues)
            if release is not None:
                in_header = False
                current_release = release
                current_type = ChangeType.CHANGED
                changelog.releases.append(current_release)
                continue

            if line.startswith('## '):
                # A level-2 header that didn't parse as a release at all.
                in_header = False
                issues.append(ValidationIssue(
                    _v.MALFORMED_HEADER,
                    f"could not parse release header: {line.strip()!r} "
                    "(expected '## [X.Y.Z] - YYYY-MM-DD')",
                    Severity.ERROR, lineno,
                ))
                current_release = None
                continue

            m = CHANGE_TYPE_HEADER.match(line)
            if m and current_release is not None:
                label = m.group(1).strip()
                key = label.lower()
                if key in _TYPE_MAP:
                    current_type = _TYPE_MAP[key]
                elif key in _TYPE_ALIASES:
                    current_type = _TYPE_ALIASES[key]
                    issues.append(ValidationIssue(
                        _v.UNKNOWN_CHANGE_TYPE,
                        f"non-standard section {label!r}; "
                        f"interpreted as {current_type.value!r}",
                        Severity.WARNING, lineno,
                    ))
                else:
                    current_type = ChangeType.CHANGED
                    issues.append(ValidationIssue(
                        _v.UNKNOWN_CHANGE_TYPE,
                        f"unknown change type {label!r}; "
                        "entries filed under 'Changed'",
                        Severity.WARNING, lineno,
                    ))
                continue

            m = BULLET.match(line)
            if m:
                if current_release is None:
                    issues.append(ValidationIssue(
                        _v.ENTRY_OUTSIDE_RELEASE,
                        f"entry {m.group(1).strip()!r} appears outside any "
                        "release block and was skipped",
                        Severity.WARNING, lineno,
                    ))
                    continue
                current_release.entries.append(
                    Entry(text=m.group(1).strip(), change_type=current_type)
                )
                continue

            # Wrapped continuation of the previous bullet
            m = CONTINUATION.match(line)
            if (
                m
                and current_release is not None
                and current_release.entries
                and not line.lstrip().startswith('#')
            ):
                current_release.entries[-1].text += ' ' + m.group(1).strip()

        changelog.description = changelog.description.strip()
        return changelog

    @staticmethod
    def _normalize_setext(
        lines: list, issues: list
    ) -> list:
        """Rewrite RST/setext version headers ("2.3.0" over ----) into
        '## [2.3.0] - date' so changelogs like requests' HISTORY.md parse."""
        out = list(lines)
        for i in range(len(out) - 1):
            if not SETEXT_UNDERLINE.match(out[i + 1]):
                continue
            m = SETEXT_VERSION.match(out[i])
            if not m:
                continue
            ver = m.group('version').rstrip('.')
            raw_date = (m.group('date') or '').strip()
            out[i] = f"## [{ver}]" + (f" - {raw_date}" if raw_date else "")
            out[i + 1] = ""
            issues.append(ValidationIssue(
                _v.MALFORMED_HEADER,
                f"RST-style release header for {ver!r} interpreted as "
                f"'{out[i]}'",
                Severity.WARNING, i + 1,
            ))
        return out

    def _try_release_header(
        self, line: str, lineno: int, issues: list[ValidationIssue]
    ) -> Release | None:
        """Parse '## [version] - date' (spec) or '## version - date' (loose)."""
        bracketed = True
        m = VERSION_HEADER.match(line)
        if not m:
            m = BARE_VERSION_HEADER.match(line)
            bracketed = False
        if not m:
            return None

        ver = m.group('version').strip()
        raw_date = m.group('date')
        rest = m.group('rest') or ""

        if not bracketed:
            issues.append(ValidationIssue(
                _v.MALFORMED_HEADER,
                f"version {ver!r} is not wrapped in brackets "
                f"(expected '## [{ver}]')",
                Severity.WARNING, lineno,
            ))

        # A trailing [YANKED] can be captured as the "date" token.
        if raw_date and YANKED.match(raw_date):
            rest = raw_date + rest
            raw_date = None

        parsed_date = None
        if raw_date:
            parsed_date = _parse_date(raw_date, lineno, issues)

        yanked = bool(YANKED.search(line))
        return Release(
            version=ver,
            release_date=parsed_date,
            is_unreleased=False,
            yanked=yanked,
        )
