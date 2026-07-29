"""
patchnotes.formats.yaml_format
YAML changelog parser.

Expected schema (all keys except ``releases`` optional)::

    title: My Project
    description: What the project does.
    releases:
      - version: "2.0.0"          # or unreleased: true
        date: 2024-11-15          # ISO date, quoted string, or omitted
        yanked: false
        changes:
          added:
            - New feature
          fixed:
            - Some bug
          breaking:
            - Renamed foo() to bar()

For flexibility the parser also accepts ``changes`` entries directly as a
mapping on the release (``added: [...]`` at release level) and a flat
``entries`` list of ``{text, type}`` mappings.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from .. import _validation as _v
from .._models import Changelog, ChangeType, Entry, Release
from .._validation import Severity, ValidationIssue
from . import FormatParser

_TYPE_MAP = {t.value.lower(): t for t in ChangeType}

_MISSING_PYYAML_MSG = (
    "YAML changelog support requires PyYAML. "
    "Install it with: pip install PyYAML"
)


def _load_yaml(text: str):
    try:
        import yaml
    except ImportError as e:  # pragma: no cover - depends on environment
        raise ImportError(_MISSING_PYYAML_MSG) from e
    return yaml.safe_load(text)


class YamlFormat(FormatParser):
    """YAML-based changelog format."""

    name = "yaml"
    extensions = (".yml", ".yaml")

    def sniff(self, text: str) -> bool:
        stripped = text.lstrip()
        if stripped.startswith(("---", "%YAML")):
            return True
        # A releases: key near the top strongly suggests our YAML schema.
        head = "\n".join(stripped.splitlines()[:10])
        return "releases:" in head and not head.startswith("#")

    def parse(self, text: str) -> Changelog:
        changelog = Changelog()
        issues = changelog.issues

        try:
            data = _load_yaml(text)
        except ImportError:
            raise
        except Exception as e:
            issues.append(ValidationIssue(
                _v.YAML_SCHEMA, f"invalid YAML: {e}", Severity.ERROR,
                getattr(getattr(e, "problem_mark", None), "line", None),
            ))
            return changelog

        if not isinstance(data, dict):
            issues.append(ValidationIssue(
                _v.YAML_SCHEMA,
                f"expected a mapping at the document root, got "
                f"{type(data).__name__}",
                Severity.ERROR,
            ))
            return changelog

        changelog.title = str(data.get("title") or "Changelog")
        changelog.description = str(data.get("description") or "").strip()

        raw_releases = data.get("releases")
        if raw_releases is None:
            issues.append(ValidationIssue(
                _v.YAML_SCHEMA, "missing top-level 'releases' key",
                Severity.ERROR,
            ))
            return changelog
        if not isinstance(raw_releases, list):
            issues.append(ValidationIssue(
                _v.YAML_SCHEMA, "'releases' must be a list", Severity.ERROR,
            ))
            return changelog

        for idx, raw in enumerate(raw_releases):
            release = self._parse_release(raw, idx, issues)
            if release is not None:
                changelog.releases.append(release)
        return changelog

    def _parse_release(
        self, raw: Any, idx: int, issues: list[ValidationIssue]
    ) -> Release | None:
        where = f"releases[{idx}]"
        if not isinstance(raw, dict):
            issues.append(ValidationIssue(
                _v.YAML_SCHEMA,
                f"{where}: expected a mapping, got {type(raw).__name__}; skipped",
                Severity.ERROR,
            ))
            return None

        is_unreleased = bool(raw.get("unreleased")) or (
            str(raw.get("version", "")).lower() == "unreleased"
        )
        version = str(raw.get("version") or ("Unreleased" if is_unreleased else ""))
        if not version:
            issues.append(ValidationIssue(
                _v.YAML_SCHEMA,
                f"{where}: missing 'version' key; release skipped",
                Severity.ERROR,
            ))
            return None

        release_date = self._parse_date(raw.get("date"), where, issues)
        release = Release(
            version=version,
            release_date=release_date,
            is_unreleased=is_unreleased,
            yanked=bool(raw.get("yanked", False)),
        )

        changes = raw.get("changes")
        if changes is None:
            # Accept type keys directly on the release mapping.
            changes = {
                k: v for k, v in raw.items() if k.lower() in _TYPE_MAP
            } or None

        if isinstance(changes, dict):
            for type_key, items in changes.items():
                ct = _TYPE_MAP.get(str(type_key).lower())
                if ct is None:
                    ct = ChangeType.CHANGED
                    issues.append(ValidationIssue(
                        _v.UNKNOWN_CHANGE_TYPE,
                        f"{where}: unknown change type {type_key!r}; "
                        "entries filed under 'Changed'",
                        Severity.WARNING,
                    ))
                if items is None:
                    continue
                if not isinstance(items, list):
                    items = [items]
                for item in items:
                    release.entries.append(
                        Entry(text=str(item).strip(), change_type=ct)
                    )
        elif isinstance(raw.get("entries"), list):
            for e_idx, item in enumerate(raw["entries"]):
                if isinstance(item, dict) and "text" in item:
                    ct = _TYPE_MAP.get(
                        str(item.get("type", "changed")).lower(),
                        ChangeType.CHANGED,
                    )
                    release.entries.append(
                        Entry(text=str(item["text"]).strip(), change_type=ct)
                    )
                else:
                    issues.append(ValidationIssue(
                        _v.YAML_SCHEMA,
                        f"{where}.entries[{e_idx}]: expected a mapping with "
                        "'text' (and optional 'type'); skipped",
                        Severity.WARNING,
                    ))
        elif changes is not None:
            issues.append(ValidationIssue(
                _v.YAML_SCHEMA,
                f"{where}: 'changes' must be a mapping of change type to "
                "list of entries",
                Severity.ERROR,
            ))
        return release

    @staticmethod
    def _parse_date(
        raw: Any, where: str, issues: list[ValidationIssue]
    ) -> date | None:
        if raw is None:
            return None
        if isinstance(raw, datetime):
            return raw.date()
        if isinstance(raw, date):
            return raw
        try:
            return date.fromisoformat(str(raw).strip())
        except ValueError:
            issues.append(ValidationIssue(
                _v.BAD_DATE,
                f"{where}: unparseable date {raw!r} (expected YYYY-MM-DD)",
                Severity.ERROR,
            ))
            return None
