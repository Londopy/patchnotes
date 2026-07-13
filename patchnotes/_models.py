"""
patchnotes._models
Data model: Changelog, Release, Entry, ChangeType.

Format-specific parsing lives in ``patchnotes.formats``; these classes are
format-agnostic.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from enum import Enum

from . import _validation as _v
from ._validation import Severity, ValidationIssue


class ChangeType(str, Enum):
    ADDED = "Added"
    CHANGED = "Changed"
    DEPRECATED = "Deprecated"
    REMOVED = "Removed"
    FIXED = "Fixed"
    SECURITY = "Security"
    BREAKING = "Breaking"


_SEMVER_ISH = re.compile(r"^v?\d+(\.\d+){0,2}([-+.].*)?$")


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
class Entry:
    """A single changelog entry (one bullet point)."""

    text: str
    change_type: ChangeType

    def __repr__(self):
        return f"Entry({self.change_type.value}: {self.text!r})"

    def to_dict(self) -> dict:
        return {"text": self.text, "change_type": self.change_type.value}


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
        return [
            e
            for e in self.entries
            if e.change_type in (ChangeType.BREAKING, ChangeType.REMOVED)
        ]

    @property
    def by_type(self) -> dict[str, list[Entry]]:
        result: dict[str, list[Entry]] = {}
        for entry in self.entries:
            result.setdefault(entry.change_type.value, []).append(entry)
        return result

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "release_date": self.release_date.isoformat()
            if self.release_date
            else None,
            "is_unreleased": self.is_unreleased,
            "yanked": self.yanked,
            "entries": [e.to_dict() for e in self.entries],
            "by_type": {
                k: [e.to_dict() for e in v] for k, v in self.by_type.items()
            },
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
    #: Keep a Changelog compare-link footnotes: {"1.2.0": "https://.../compare/..."}.
    links: dict = field(default_factory=dict)
    #: Issues collected while parsing (lenient mode). Excluded from repr
    #: and from to_dict() for backward compatibility; use validate().
    issues: list[ValidationIssue] = field(default_factory=list, repr=False, compare=False)

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
            r
            for r in self.releases
            if not r.is_unreleased and from_v < _parse_semver(r.version) <= to_v
        ]

    # ── Validation ────────────────────────────────────────────────────────

    def validate(self) -> list[ValidationIssue]:
        """
        Return every issue with this changelog: problems recorded during
        parsing plus semantic checks on the parsed structure.

        An empty list means the changelog is fully spec-compliant::

            cl = patchnotes.parse_file("CHANGELOG.md")
            issues = cl.validate()
            if any(i.severity == "error" for i in issues):
                sys.exit(1)
        """
        issues = list(self.issues)
        issues.extend(self._semantic_issues())
        return issues

    def is_valid(self, strict: bool = False) -> bool:
        """
        True if the changelog has no ERROR-severity issues.
        With ``strict=True``, warnings also count as failures.
        """
        issues = self.validate()
        if strict:
            return not issues
        return not any(i.severity is Severity.ERROR for i in issues)

    def _semantic_issues(self) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        if not self.releases:
            issues.append(
                ValidationIssue(
                    _v.NO_RELEASES,
                    "no releases found in changelog",
                    Severity.WARNING,
                )
            )
            return issues

        seen: set[str] = set()
        prev_key: Optional[tuple] = None
        for r in self.releases:
            if r.version in seen:
                issues.append(
                    ValidationIssue(
                        _v.DUPLICATE_VERSION,
                        f"version {r.version!r} appears more than once",
                        Severity.ERROR,
                    )
                )
            seen.add(r.version)

            if not r.entries:
                issues.append(
                    ValidationIssue(
                        _v.EMPTY_RELEASE,
                        f"release {r.version!r} has no entries",
                        Severity.WARNING,
                    )
                )

            if not r.is_unreleased and not _SEMVER_ISH.match(r.version):
                issues.append(
                    ValidationIssue(
                        _v.NON_SEMVER_VERSION,
                        f"version {r.version!r} is not a semver-like version",
                        Severity.WARNING,
                    )
                )

            key = _parse_semver(r.version)
            if prev_key is not None and key > prev_key:
                issues.append(
                    ValidationIssue(
                        _v.VERSIONS_OUT_OF_ORDER,
                        f"version {r.version!r} is newer than the release "
                        "listed above it (releases should be newest-first)",
                        Severity.WARNING,
                    )
                )
            prev_key = key

        # Compare-link footnotes are only checked when the changelog uses them.
        if self.links:
            link_keys = {k.lower() for k in self.links}
            known = {r.version.lower() for r in self.releases}
            for r in self.releases:
                if not r.is_unreleased and r.version.lower() not in link_keys:
                    issues.append(
                        ValidationIssue(
                            _v.MISSING_COMPARE_LINK,
                            f"release {r.version!r} has no [version]: url "
                            "link footnote",
                            Severity.WARNING,
                        )
                    )
            for k in self.links:
                if k.lower() != "unreleased" and k.lower() not in known:
                    issues.append(
                        ValidationIssue(
                            _v.ORPHAN_COMPARE_LINK,
                            f"link footnote {k!r} does not match any release",
                            Severity.WARNING,
                        )
                    )
        return issues

    # ── Release automation ────────────────────────────────────────────────

    def bump(
        self,
        version: str,
        release_date: Optional[date] = None,
        keep_unreleased: bool = True,
    ) -> Release:
        """
        Move the [Unreleased] entries into a new dated release.

        Args:
            version:         The new version number (e.g. "2.1.0").
            release_date:    Release date; defaults to today.
            keep_unreleased: Keep an empty [Unreleased] section on top
                             (Keep a Changelog convention). Default True.

        Returns:
            The newly created Release.

        Raises:
            ValueError: If there are no unreleased entries, or the version
                        already exists.

        Example::

            cl = patchnotes.parse_file("CHANGELOG.md")
            cl.bump("2.1.0")
            with open("CHANGELOG.md", "w") as f:
                f.write(patchnotes.to_markdown(cl))
        """
        u = self.unreleased()
        if u is None or not u.entries:
            raise ValueError(
                "no unreleased changes to release — the [Unreleased] "
                "section is missing or empty"
            )
        if any(r.version == version for r in self.releases):
            raise ValueError(f"version {version!r} already exists in the changelog")

        previous = self.latest()
        new_release = Release(
            version=version,
            release_date=release_date or date.today(),
            is_unreleased=False,
            entries=list(u.entries),
        )
        idx = self.releases.index(u)
        self.releases.insert(idx + 1, new_release)
        u.entries = []
        if not keep_unreleased:
            self.releases.remove(u)

        self._refresh_links_after_bump(version, previous)
        return new_release

    def _refresh_links_after_bump(
        self, version: str, previous: Optional[Release]
    ) -> None:
        """Maintain compare-link footnotes, if the changelog uses them."""
        from ._write import _COMPARE_RE  # lazy: avoids circular import

        base = None
        prefix = "v"
        for url in self.links.values():
            m = _COMPARE_RE.match(url)
            if m:
                base = m.group("base")
                # Infer the tag prefix from the 'from' side — the 'to' side
                # may be HEAD (in the Unreleased link).
                prefix = "v" if m.group("from").startswith("v") else ""
                break
        if base is None:
            return
        tag = f"{prefix}{version}"
        if previous is not None:
            self.links[version] = (
                f"{base}/compare/{prefix}{previous.version}...{tag}"
            )
        else:
            self.links[version] = f"{base}/releases/tag/{tag}"
        for k in list(self.links):
            if k.lower() == "unreleased":
                self.links[k] = f"{base}/compare/{tag}...HEAD"

    # ── Serialization ─────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "description": self.description,
            "links": dict(self.links),
            "releases": [r.to_dict() for r in self.releases],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)

    # ── Remote fetching ───────────────────────────────────────────────────

    @classmethod
    def from_url(cls, url: str, format: str = "auto", strict: bool = False) -> "Changelog":
        """
        Fetch and parse a remote changelog from any URL.

        Example::

            cl = Changelog.from_url(
                "https://raw.githubusercontent.com/user/repo/main/CHANGELOG.md"
            )
        """
        from ._dispatch import parse  # lazy: avoids circular import

        req = urllib.request.Request(
            url, headers={"User-Agent": "patchnotes-python/2.0"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            text = resp.read().decode("utf-8", errors="replace")
        if format == "auto":
            format = "yaml" if url.rsplit("?", 1)[0].endswith((".yml", ".yaml")) else "auto"
        return parse(text, format=format, strict=strict)

    @classmethod
    def from_github(
        cls,
        owner: str,
        repo: str,
        branch: str = "main",
        filename: str = "CHANGELOG.md",
        format: str = "auto",
        strict: bool = False,
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
            format:   Input format ("auto", "markdown", "yaml").
            strict:   Raise ChangelogValidationError on spec violations.

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
                url, headers={"User-Agent": "patchnotes-python/2.0"}
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
        from ._dispatch import parse  # lazy: avoids circular import

        if format == "auto" and filename.endswith((".yml", ".yaml")):
            format = "yaml"
        return parse(text, format=format, strict=strict)

    def __repr__(self):
        return f"Changelog({len(self.releases)} releases)"
