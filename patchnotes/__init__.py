"""
patchnotes — Parse Keep a Changelog formatted CHANGELOG.md files.

Basic usage::

    import patchnotes

    cl = patchnotes.parse_file("CHANGELOG.md")
    print(cl.latest())          # Release(v2.1.0, 2024-11-15, 6 entries)
    print(cl.unreleased())      # Release(vUnreleased, unreleased, 2 entries)

    # What changed between two versions?
    for r in cl.diff("1.4.0", "2.1.0"):
        print(r.version, r.breaking_changes)

    # Dump to JSON
    print(cl.to_json())
"""

from ._parser import (
    parse,
    parse_file,
    Changelog,
    Release,
    Entry,
    ChangeType,
)

__version__ = "1.0.0"
__all__ = [
    "parse",
    "parse_file",
    "Changelog",
    "Release",
    "Entry",
    "ChangeType",
    "__version__",
]
