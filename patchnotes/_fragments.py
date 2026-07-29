"""
patchnotes._fragments
Zero-config changelog fragments (news snippets).

The #1 reason busy repos abandon CHANGELOG.md is merge conflicts: every PR
edits the same [Unreleased] lines. Fragments fix that — each PR adds its
own file under ``changelog.d/`` and release day folds them in:

    patchnotes fragment add fixed "Handle empty input"
    # -> changelog.d/fixed-3fa9c2d1.md
    patchnotes CHANGELOG.md bump 2.2.0 --collect
    # -> entries folded into the new release, fragment files deleted

No config file, no tooling to learn: the change type is the filename
prefix, the entry text is the file content (one bullet per line).
"""

from __future__ import annotations

import os
import pathlib
import uuid
from typing import TYPE_CHECKING

from ._models import ChangeType, Entry

if TYPE_CHECKING:
    from ._models import Changelog

DEFAULT_DIR = "changelog.d"
_TYPE_MAP = {t.value.lower(): t for t in ChangeType}


def fragments_dir(changelog_path: str, override: str | None = None) -> str:
    """The fragments directory: ``changelog.d/`` next to the changelog."""
    if override:
        return override
    base = os.path.dirname(changelog_path) if changelog_path != "-" else "."
    return os.path.join(base or ".", DEFAULT_DIR)


def add_fragment(directory: str, type_name: str, text: str) -> str:
    """Create a fragment file; returns its path."""
    ct = _TYPE_MAP.get(type_name.strip().lower())
    if ct is None:
        valid = ", ".join(sorted(_TYPE_MAP))
        raise ValueError(f"unknown change type {type_name!r} (one of: {valid})")
    text = text.strip()
    if not text:
        raise ValueError("fragment text must not be empty")
    pathlib.Path(directory).mkdir(exist_ok=True, parents=True)
    path = os.path.join(
        directory, f"{ct.value.lower()}-{uuid.uuid4().hex[:8]}.md"
    )
    with pathlib.Path(path).open("w", encoding="utf-8") as fh:
        fh.write(text + "\n")
    return path


def list_fragments(directory: str) -> list[tuple[str, ChangeType, list[str]]]:
    """All pending fragments as (path, change_type, [entry texts])."""
    if not pathlib.Path(directory).is_dir():
        return []
    out = []
    for name in sorted(os.listdir(directory)):
        if not name.endswith(".md"):
            continue
        path = os.path.join(directory, name)
        ct = _TYPE_MAP.get(name.split("-", 1)[0].lower(), ChangeType.CHANGED)
        with pathlib.Path(path).open("r", encoding="utf-8") as fh:
            texts = [
                line.strip().lstrip("-* ").strip()
                for line in fh.read().splitlines()
                if line.strip()
            ]
        if texts:
            out.append((path, ct, texts))
    return out


def collect(changelog: Changelog, directory: str) -> list[str]:
    """
    Fold all pending fragments into the [Unreleased] section (creating it
    if needed). Returns the fragment file paths that were folded in —
    delete them only after the updated changelog is safely written.
    """
    from ._models import Release

    pending = list_fragments(directory)
    if not pending:
        return []
    u = changelog.unreleased()
    if u is None:
        u = Release(version="Unreleased", release_date=None, is_unreleased=True)
        changelog.releases.insert(0, u)
    for _path, ct, texts in pending:
        for text in texts:
            u.entries.append(Entry(text=text, change_type=ct))
    return [p for p, _, _ in pending]
