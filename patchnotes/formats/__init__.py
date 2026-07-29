"""
patchnotes.formats
Pluggable changelog format parsers.

Each format is a ``FormatParser`` registered by name. ``patchnotes.parse``
dispatches here, so new formats (YAML, other markdown dialects, ...) can be
added — including by third-party code — without touching the core:

    from patchnotes.formats import FormatParser, register_format

    class MyFormat(FormatParser):
        name = "myformat"
        extensions = (".mycl",)

        def parse(self, text):
            ...
            return changelog  # with .issues populated

    register_format(MyFormat())
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .._models import Changelog


class FormatParser(ABC):
    """Base class for changelog format parsers.

    Implementations must be *lenient*: never raise on malformed input.
    Record problems as ``ValidationIssue`` objects on ``Changelog.issues``
    and recover as sensibly as possible. Strict-mode enforcement is handled
    centrally by ``patchnotes.parse(strict=True)``.
    """

    #: Unique registry key, e.g. "markdown" or "yaml".
    name: str = ""
    #: File extensions used for auto-detection, e.g. (".md",).
    extensions: tuple[str, ...] = ()

    @abstractmethod
    def parse(self, text: str) -> Changelog:
        """Parse ``text`` into a Changelog, collecting issues, never raising."""

    def sniff(self, text: str) -> bool:
        """Return True if ``text`` looks like this format (content-based
        auto-detection when no filename is available)."""
        return False


_REGISTRY: dict[str, FormatParser] = {}


def register_format(parser: FormatParser) -> None:
    """Register (or replace) a format parser under ``parser.name``."""
    if not parser.name:
        raise ValueError("FormatParser.name must be a non-empty string")
    _REGISTRY[parser.name] = parser


def get_format(name: str) -> FormatParser:
    """Look up a registered format parser by name."""
    try:
        return _REGISTRY[name]
    except KeyError:
        available = ", ".join(sorted(_REGISTRY)) or "(none)"
        raise ValueError(
            f"Unknown changelog format {name!r}. Available formats: {available}"
        ) from None


def available_formats() -> list[str]:
    """Names of all registered formats."""
    return sorted(_REGISTRY)


def detect_format(text: str, filename: str | None = None) -> FormatParser:
    """
    Pick the best parser for the given content/filename.

    Extension match wins; then each parser's ``sniff``; markdown is the
    final fallback (it is the lenient historical default).
    """
    if filename:
        lowered = filename.lower()
        for parser in _REGISTRY.values():
            if lowered.endswith(parser.extensions):
                return parser
    for parser in _REGISTRY.values():
        if parser.name != "markdown" and parser.sniff(text):
            return parser
    return get_format("markdown")


# Register built-in formats. YAML registers itself only if importable;
# actually *using* it without PyYAML raises a helpful error.
from . import markdown as _markdown  # ruff:ignore[module-import-not-at-top-of-file]

register_format(_markdown.MarkdownFormat())

from . import yaml_format as _yaml_format  # ruff:ignore[module-import-not-at-top-of-file]

register_format(_yaml_format.YamlFormat())
