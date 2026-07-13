"""
patchnotes._dispatch
Top-level parse/validate entry points that route to the format registry.
"""

from __future__ import annotations

from typing import Optional

from ._models import Changelog
from ._validation import (
    ChangelogValidationError,
    Severity,
    ValidationIssue,
)
from .formats import detect_format, get_format


def parse(
    text: str,
    format: str = "auto",
    strict: bool = False,
    filename: Optional[str] = None,
) -> Changelog:
    """
    Parse a changelog string into a Changelog object.

    Args:
        text:     The raw changelog content.
        format:   "auto" (default), "markdown", "yaml", or any registered
                  third-party format name.
        strict:   If True, raise ChangelogValidationError when the input
                  violates the spec (ERROR-severity issues). If False
                  (default), the parser is lenient: it recovers where it can
                  and records problems on ``Changelog.issues`` /
                  ``Changelog.validate()``.
        filename: Optional filename hint used for format auto-detection.

    Example::

        cl = patchnotes.parse(raw_text)                  # lenient
        cl = patchnotes.parse(raw_text, strict=True)     # CI-friendly
        cl = patchnotes.parse(raw_yaml, format="yaml")
    """
    if format == "auto":
        parser = detect_format(text, filename)
    else:
        parser = get_format(format)
    changelog = parser.parse(text)
    if strict:
        issues = changelog.validate()
        if any(i.severity is Severity.ERROR for i in issues):
            raise ChangelogValidationError(issues)
    return changelog


def parse_file(path: str, format: str = "auto", strict: bool = False) -> Changelog:
    """Parse a changelog file from disk (format auto-detected by extension)."""
    with open(path, "r", encoding="utf-8") as f:
        return parse(f.read(), format=format, strict=strict, filename=path)


def validate(
    text: str, format: str = "auto", filename: Optional[str] = None
) -> list[ValidationIssue]:
    """
    Validate a changelog string and return all issues found (never raises).

    Example::

        issues = patchnotes.validate(raw_text)
        errors = [i for i in issues if i.severity == "error"]
    """
    return parse(text, format=format, strict=False, filename=filename).validate()


def validate_file(path: str, format: str = "auto") -> list[ValidationIssue]:
    """Validate a changelog file from disk and return all issues found."""
    with open(path, "r", encoding="utf-8") as f:
        return validate(f.read(), format=format, filename=path)
