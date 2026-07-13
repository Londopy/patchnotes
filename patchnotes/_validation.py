"""
patchnotes._validation
Validation primitives: issues, severities, and the strict-mode exception.

Parsers collect ``ValidationIssue`` objects instead of crashing on
off-standard input. In lenient mode (the default) issues are attached to
the parsed ``Changelog``; in strict mode any ERROR-severity issue raises
``ChangelogValidationError``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Severity(str, Enum):
    """How serious a validation issue is.

    ERROR:   Spec violation where data was lost or guessed
             (malformed date, duplicate version, unparseable header).
    WARNING: Off-standard but recoverable
             (unknown section label, out-of-order versions, empty release).
    """

    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True)
class ValidationIssue:
    """A single problem found while parsing or validating a changelog."""

    code: str
    message: str
    severity: Severity
    line: Optional[int] = None

    def __str__(self) -> str:
        loc = f"line {self.line}: " if self.line is not None else ""
        return f"[{self.severity.value.upper()}] {self.code} {loc}{self.message}"

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "message": self.message,
            "severity": self.severity.value,
            "line": self.line,
        }


# Issue codes (stable identifiers — safe to grep for in CI logs)
BAD_DATE = "PN101"            # date present but not ISO YYYY-MM-DD
DUPLICATE_VERSION = "PN102"   # same version listed twice
MALFORMED_HEADER = "PN103"    # '## ...' line that isn't a valid release header
ENTRY_OUTSIDE_RELEASE = "PN104"  # bullet before any release header
UNKNOWN_CHANGE_TYPE = "PN201"    # '### Foo' not in the Keep a Changelog set
VERSIONS_OUT_OF_ORDER = "PN202"  # releases not newest-first
EMPTY_RELEASE = "PN203"          # release header with no entries
NO_RELEASES = "PN204"            # nothing parseable in the document
NON_SEMVER_VERSION = "PN205"     # version string isn't semver-ish
MISSING_COMPARE_LINK = "PN206"   # release lacks a [version]: url footnote
ORPHAN_COMPARE_LINK = "PN207"    # link footnote for a version that doesn't exist
YAML_SCHEMA = "PN301"            # YAML document doesn't match expected schema


class ChangelogValidationError(ValueError):
    """Raised by strict-mode parsing when ERROR-severity issues are found.

    The full issue list (errors *and* warnings) is available on ``.issues``.
    """

    def __init__(self, issues: list[ValidationIssue]):
        self.issues = issues
        errors = [i for i in issues if i.severity is Severity.ERROR]
        summary = "; ".join(str(i) for i in errors[:5])
        more = f" (+{len(errors) - 5} more)" if len(errors) > 5 else ""
        super().__init__(
            f"Changelog failed strict validation with "
            f"{len(errors)} error(s): {summary}{more}"
        )
