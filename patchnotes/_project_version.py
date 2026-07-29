"""
patchnotes._project_version
Extract the package version from project metadata files, for
`patchnotes CHANGELOG.md check-version` — catches the classic
"changelog says 2.1.0, pyproject says 2.0.4" mismatch before it ships.
"""

from __future__ import annotations

import json
import os
import pathlib
import re

_VERSION_LINE = re.compile(
    r'^\s*version\s*=\s*["\']([^"\']+)["\']', re.MULTILINE
)
_LITERAL_VERSION = re.compile(r"^v?\d+(\.\d+){0,2}([-+.][\w.]+)?$")

#: metadata files probed by auto-discovery, in order
DISCOVERY_FILES = ("pyproject.toml", "package.json", "Cargo.toml")


def normalize(version: str) -> str:
    """Normalize for comparison: strip whitespace and a leading 'v'."""
    version = version.strip()
    return version[1:] if version[:1] in ("v", "V") else version


def extract_version(target: str) -> tuple[str, str]:
    """
    Get a version from ``target``, which may be:

    - a metadata file path (pyproject.toml, package.json, Cargo.toml, or
      any file with a ``version = "..."`` line),
    - a literal version string ("2.1.0" or "v2.1.0" — handy for
      ``--against "$GITHUB_REF_NAME"`` in tag-triggered workflows).

    Returns (version, source_description). Raises ValueError if no
    version can be found.
    """
    if pathlib.Path(target).is_file():
        with pathlib.Path(target).open("r", encoding="utf-8") as fh:
            text = fh.read()
        name = os.path.basename(target).lower()
        if name == "package.json":
            try:
                version = json.loads(text).get("version")
            except json.JSONDecodeError as e:
                raise ValueError(f"{target}: invalid JSON ({e})") from None
            if not version:
                raise ValueError(f'{target}: no "version" key')
            return str(version), target
        m = _VERSION_LINE.search(text)
        if m:
            return m.group(1), target
        if "dynamic" in text and "version" in text:
            raise ValueError(
                f"{target}: version appears to be dynamic — pass the "
                f'resolved version explicitly, e.g. --against "$VERSION"'
            )
        raise ValueError(f'{target}: no version = "..." line found')

    if _LITERAL_VERSION.match(target.strip()):
        return target.strip(), "command line"

    raise ValueError(
        f"--against {target!r} is neither an existing file nor a "
        "version string"
    )


def discover_target(base_dir: str) -> str | None:
    """Find a metadata file near the changelog for auto-discovery."""
    for name in DISCOVERY_FILES:
        candidate = os.path.join(base_dir or ".", name)
        if pathlib.Path(candidate).is_file():
            return candidate
    return None
