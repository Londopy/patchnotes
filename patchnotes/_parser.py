"""
patchnotes._parser
Backward-compatibility shim.

In patchnotes 2.0 the parser was split into:

- ``patchnotes._models``    — Changelog, Release, Entry, ChangeType
- ``patchnotes._dispatch``  — parse(), parse_file(), validate()
- ``patchnotes.formats``    — pluggable per-format parsers

Everything importable from here in 1.x still works.
"""

from ._dispatch import parse, parse_file  # noqa: F401
from ._models import (  # noqa: F401
    Changelog,
    ChangeType,
    Entry,
    Release,
    _parse_semver,
)

#: Everything this shim re-exports for 1.x compatibility.
__all__ = [
    "parse",
    "parse_file",
    "Changelog",
    "ChangeType",
    "Entry",
    "Release",
    "_parse_semver",
]
