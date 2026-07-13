"""
patchnotes — Parse changelogs (Keep a Changelog markdown, YAML) into
structured Python objects.

Basic usage::

    import patchnotes

    # From a file (format auto-detected; lenient by default)
    cl = patchnotes.parse_file("CHANGELOG.md")

    # Strict mode for CI — raises ChangelogValidationError on spec violations
    cl = patchnotes.parse_file("CHANGELOG.md", strict=True)

    # YAML changelogs
    cl = patchnotes.parse_file("changelog.yml")

    # Validate without raising
    issues = cl.validate()   # -> list[ValidationIssue]

    # From a GitHub repo (auto-fetches the raw file)
    cl = patchnotes.Changelog.from_github("Londopy", "patchnotes")

    # Query
    print(cl.latest())
    print(cl.diff("1.4.0", "2.1.0"))

    # Render
    html = patchnotes.to_html(cl)
    rss  = patchnotes.to_rss(cl, project_url="https://github.com/you/project")
    text = patchnotes.to_text(cl, max_releases=3)
"""

from ._dispatch import (
    parse,
    parse_file,
    validate,
    validate_file,
)
from ._models import (
    Changelog,
    ChangeType,
    Entry,
    Release,
)
from ._render import (
    to_html,
    to_rss,
    to_text,
)
from ._validation import (
    ChangelogValidationError,
    Severity,
    ValidationIssue,
)
from .formats import (
    FormatParser,
    available_formats,
    register_format,
)

__version__ = "2.0.1"
__all__ = [
    "parse",
    "parse_file",
    "validate",
    "validate_file",
    "Changelog",
    "Release",
    "Entry",
    "ChangeType",
    "ValidationIssue",
    "Severity",
    "ChangelogValidationError",
    "FormatParser",
    "register_format",
    "available_formats",
    "to_html",
    "to_rss",
    "to_text",
    "__version__",
]
