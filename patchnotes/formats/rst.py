"""
patchnotes.formats.rst

reStructuredText changelog parser.

rST has no fixed heading syntax: a section is a title line followed (and
optionally preceded) by an *adornment* line of repeated punctuation, and the
hierarchy is defined by the order in which adornment styles first appear in
the document. So the parser learns the document's own heading levels as it
reads, rather than matching a fixed pattern the way the markdown parser
matches ``##``.

Typical shape this targets::

    Changelog
    =========

    2.32.0 (2024-05-20)
    -------------------

    Security
    ~~~~~~~~

    - Fixed a certificate verification issue

Like every patchnotes format this is lenient: nothing raises, problems become
``ValidationIssue`` records. Issue codes match the markdown parser's so that
quality statistics are comparable across the two formats.
"""

from __future__ import annotations

import re
from typing import Optional

from .. import _validation as _v
from .._models import Changelog, ChangeType, Entry, Release
from .._validation import Severity, ValidationIssue
from . import FormatParser
from .markdown import _TYPE_ALIASES, _TYPE_MAP, _parse_date

#: Punctuation rST permits as section adornment.
ADORNMENT_CHARS = "!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~"
ADORNMENT = re.compile(r"^([" + re.escape(ADORNMENT_CHARS) + r"])\1{1,}\s*$")

#: A section title that names a release. Covers "1.2.3", "v1.2.3",
#: "Version 1.2.3", "1.2.3 (2024-05-20)", "1.2.3 - 2024-05-20".
VERSION_TITLE = re.compile(
    r"^\s*(?:version\s+|release\s+)?"
    r"v?(?P<version>\d+(?:\.\d+){0,3}(?:[-.+][\w.]+)?)"
    r"\s*(?:[-–—:]\s*|\(\s*)?"
    r"(?P<date>[\d]{4}[-/.][\d]{1,2}[-/.][\d]{1,2}|[\d]{1,2}[-/.][\d]{1,2}[-/.][\d]{4})?"
    r"\s*\)?\s*$",
    re.IGNORECASE,
)
UNRELEASED_TITLE = re.compile(
    r"^\s*\(?(?:unreleased|in development|upcoming|master|main|next)\)?\s*$",
    re.IGNORECASE,
)
YANKED = re.compile(r"\[?YANKED\]?", re.IGNORECASE)

BULLET = re.compile(r"^(\s*)[-*+•]\s+(.+)$")
#: A directive or comment block: ".. note::", ".. towncrier release notes start"
DIRECTIVE = re.compile(r"^\s*\.\.(\s|$)")
#: An ATX markdown heading ("## 1.2.0"). Note the required space: a row of
#: "#" characters is a valid rST adornment, not a heading.
ATX_HEADING = re.compile(r"^#{1,6}\s")

# ── inline markup ─────────────────────────────────────────────────────────────

_INLINE_SUBS = (
    # :role:`text <target>` and :role:`text`  ->  text
    (re.compile(r":[\w:+.-]+:`([^`<]*?)(?:\s*<[^`>]*>)?`"), r"\1"),
    # ``literal``  ->  literal
    (re.compile(r"``(.+?)``", re.DOTALL), r"\1"),
    # `text <url>`_ / `text <url>`__  ->  text
    (re.compile(r"`([^`<]*?)\s*<[^`>]*>`__?"), r"\1"),
    # `text`_ , `text`  ->  text
    (re.compile(r"`(.+?)`_{0,2}", re.DOTALL), r"\1"),
    # **strong** / *emphasis*  ->  text
    (re.compile(r"\*\*(.+?)\*\*", re.DOTALL), r"\1"),
    (re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", re.DOTALL), r"\1"),
    # standalone reference "issue_" -> issue
    (re.compile(r"\b(\w+)__?\b(?=[\s.,;:)]|$)"), r"\1"),
)


def strip_inline(text: str) -> str:
    """Reduce rST inline markup to readable plain text."""
    for pattern, repl in _INLINE_SUBS:
        text = pattern.sub(repl, text)
    text = text.replace("\\ ", "").replace("\\", "")
    return re.sub(r"\s+", " ", text).strip()


# ── section scanning ──────────────────────────────────────────────────────────

class _Section:
    __slots__ = ("title", "level", "lineno", "body_start")

    def __init__(self, title: str, level: int, lineno: int, body_start: int):
        self.title = title
        self.level = level
        self.lineno = lineno
        self.body_start = body_start


def _scan_sections(lines: list[str]) -> list[_Section]:
    """Find every section, assigning levels by adornment-style first use.

    rST defines hierarchy by convention, not by character: whichever style
    appears first is level 0, the next new style is level 1, and so on. An
    overlined title outranks the same character underlined only, so the style
    key includes whether an overline was present.
    """
    styles: list[tuple[bool, str]] = []
    sections: list[_Section] = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]
        over = ADORNMENT.match(line)

        # Overline form: adornment / title / adornment (same char)
        if over and i + 2 < n:
            title = lines[i + 1].strip()
            under = ADORNMENT.match(lines[i + 2])
            if title and under and under.group(1) == over.group(1) \
                    and not ADORNMENT.match(lines[i + 1]):
                key = (True, over.group(1))
                if key not in styles:
                    styles.append(key)
                sections.append(_Section(title, styles.index(key), i + 2, i + 3))
                i += 3
                continue

        # Underline form: title / adornment
        if i + 1 < n and line.strip() and not over and not DIRECTIVE.match(line):
            under = ADORNMENT.match(lines[i + 1])
            title = line.strip()
            # rST wants the adornment at least as long as the title; be lenient
            # by a couple of characters, since hand-maintained files drift.
            if under and len(lines[i + 1].strip()) >= max(2, len(title) - 2):
                key = (False, under.group(1))
                if key not in styles:
                    styles.append(key)
                sections.append(_Section(title, styles.index(key), i + 1, i + 2))
                i += 2
                continue

        i += 1

    return sections


def _parse_title(
    title: str, lineno: int, issues: list[ValidationIssue]
) -> Optional[Release]:
    """Interpret a section title as a release, or return None."""
    if UNRELEASED_TITLE.match(title):
        return Release(version="Unreleased", release_date=None, is_unreleased=True)

    cleaned = YANKED.sub("", title).strip()
    m = VERSION_TITLE.match(cleaned)
    if not m:
        return None

    version = m.group("version")
    raw_date = m.group("date")
    parsed = _parse_date(raw_date, lineno, issues) if raw_date else None
    return Release(
        version=version,
        release_date=parsed,
        is_unreleased=False,
        yanked=bool(YANKED.search(title)),
    )


def _collect_entries(
    lines: list[str], start: int, end: int, change_type: ChangeType
) -> list[Entry]:
    """Pull bullet items (with their continuation lines) out of a line range."""
    entries: list[Entry] = []
    buf: list[str] = []
    indent = 0

    def flush() -> None:
        if buf:
            text = strip_inline(" ".join(buf))
            if text:
                entries.append(Entry(text=text, change_type=change_type))
            buf.clear()

    i = start
    while i < end and i < len(lines):
        line = lines[i]
        if DIRECTIVE.match(line):
            flush()
            i += 1
            # skip the directive's indented body
            while i < end and i < len(lines) and (not lines[i].strip()
                                                  or lines[i][:1].isspace()):
                i += 1
            continue

        m = BULLET.match(line)
        if m:
            flush()
            indent = len(m.group(1))
            buf.append(m.group(2).strip())
        elif buf and line.strip() and len(line) - len(line.lstrip()) > indent:
            buf.append(line.strip())
        elif not line.strip():
            pass  # blank lines may separate a wrapped bullet's paragraphs
        else:
            flush()
        i += 1

    flush()
    return entries


class RstFormat(FormatParser):
    """reStructuredText changelog parser."""

    name = "rst"
    extensions = (".rst",)

    def sniff(self, text: str) -> bool:
        """True only on content that is distinctly rST.

        Deliberately conservative. Setext-underlined markdown ("2.32.0
        (2024-05-20)" over "-------") is indistinguishable from rST by
        adornments alone, and the markdown parser already handles it — so
        claiming it here would silently reroute existing documents. This
        requires a signal markdown never produces (a directive, an overlined
        title, or an adornment character outside ``-=``) and bails as soon as
        an ATX heading appears.
        """
        lines = text.splitlines()[:400]
        if any(ATX_HEADING.match(ln) for ln in lines):
            return False
        adorned = [ln for ln in lines if ADORNMENT.match(ln)]
        if len(adorned) < 2:
            return False
        if any(DIRECTIVE.match(ln) for ln in lines):
            return True
        # An adornment character beyond the setext-markdown repertoire, or an
        # overline (two adornment lines around one title), means real rST.
        if any(ADORNMENT.match(ln).group(1) not in "-=" for ln in adorned):
            return True
        for i in range(len(lines) - 2):
            if (ADORNMENT.match(lines[i]) and lines[i + 1].strip()
                    and ADORNMENT.match(lines[i + 2] if i + 2 < len(lines) else "")):
                return True
        return False

    def parse(self, text: str) -> Changelog:
        lines = text.splitlines()
        issues: list[ValidationIssue] = []
        sections = _scan_sections(lines)

        cl = Changelog()
        if not sections:
            issues.append(ValidationIssue(
                _v.NO_RELEASES,
                "no reStructuredText sections found; document may not be a changelog",
                Severity.ERROR, 1,
            ))
            cl.issues = issues
            return cl

        # Document title: the shallowest section, if it isn't itself a release.
        top = min(s.level for s in sections)
        first = sections[0]
        if first.level == top and _parse_title(first.title, first.lineno, []) is None:
            cl.title = first.title

        # Which level holds releases? The shallowest level at which any title
        # parses as a version. Deeper sections under it are change types.
        release_levels = [
            s.level for s in sections
            if _parse_title(s.title, s.lineno, []) is not None
        ]
        if not release_levels:
            issues.append(ValidationIssue(
                _v.NO_RELEASES,
                "no section title looks like a release version",
                Severity.ERROR, 1,
            ))
            cl.issues = issues
            return cl
        release_level = min(release_levels)

        seen: set[str] = set()
        current: Optional[Release] = None
        current_type = ChangeType.CHANGED

        for idx, sec in enumerate(sections):
            body_end = (sections[idx + 1].lineno - 1
                        if idx + 1 < len(sections) else len(lines))

            if sec.level == release_level:
                rel = _parse_title(sec.title, sec.lineno, issues)
                if rel is None:
                    issues.append(ValidationIssue(
                        _v.MALFORMED_HEADER,
                        f"section {sec.title!r} sits at the release level but "
                        "is not a recognisable version",
                        Severity.WARNING, sec.lineno,
                    ))
                    current = None
                    continue
                if rel.version in seen:
                    issues.append(ValidationIssue(
                        _v.DUPLICATE_VERSION,
                        f"version {rel.version!r} appears more than once",
                        Severity.ERROR, sec.lineno,
                    ))
                seen.add(rel.version)
                current = rel
                current_type = ChangeType.CHANGED
                cl.releases.append(rel)
                # Bullets directly under the release header, before any
                # change-type subsection, still belong to it.
                rel.entries.extend(
                    _collect_entries(lines, sec.body_start, body_end, current_type)
                )
                continue

            if sec.level > release_level and current is not None:
                label = sec.title.strip()
                key = label.lower().rstrip(":")
                if key in _TYPE_MAP:
                    current_type = _TYPE_MAP[key]
                elif key in _TYPE_ALIASES:
                    current_type = _TYPE_ALIASES[key]
                    issues.append(ValidationIssue(
                        _v.UNKNOWN_CHANGE_TYPE,
                        f"non-standard section {label!r}; "
                        f"interpreted as {current_type.value!r}",
                        Severity.WARNING, sec.lineno,
                    ))
                else:
                    current_type = ChangeType.CHANGED
                    issues.append(ValidationIssue(
                        _v.UNKNOWN_CHANGE_TYPE,
                        f"unknown change type {label!r}; "
                        "entries filed under 'Changed'",
                        Severity.WARNING, sec.lineno,
                    ))
                current.entries.extend(
                    _collect_entries(lines, sec.body_start, body_end, current_type)
                )
                continue

            # A section above the release level that isn't the document title:
            # anything bulleted under it is outside any release.
            if sec.level < release_level:
                stray = _collect_entries(lines, sec.body_start, body_end,
                                         ChangeType.CHANGED)
                if stray:
                    issues.append(ValidationIssue(
                        _v.ENTRY_OUTSIDE_RELEASE,
                        f"{len(stray)} entr{'y' if len(stray) == 1 else 'ies'} "
                        f"under {sec.title!r} precede any release",
                        Severity.ERROR, sec.lineno,
                    ))
                current = None

        for rel in cl.releases:
            if not rel.entries and not rel.is_unreleased:
                issues.append(ValidationIssue(
                    _v.EMPTY_RELEASE,
                    f"release {rel.version!r} has no entries",
                    Severity.WARNING, None,
                ))

        if not cl.releases:
            issues.append(ValidationIssue(
                _v.NO_RELEASES, "no releases found", Severity.ERROR, 1,
            ))

        cl.issues = issues
        return cl
