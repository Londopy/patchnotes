"""
tests/test_formats.py
Tests for the format registry, auto-detection, and the YAML format.
"""

import pytest

from patchnotes import (
    ChangeType,
    FormatParser,
    available_formats,
    parse,
    parse_file,
    register_format,
    validate,
)
from patchnotes import _validation as codes
from patchnotes.formats import detect_format, get_format

yaml = pytest.importorskip("yaml", reason="PyYAML not installed")

YAML_SAMPLE = """\
title: My YAML Project
description: Changelog kept in YAML.
releases:
  - version: "2.0.0"
    date: 2024-06-01
    changes:
      breaking:
        - Renamed foo() to bar()
      added:
        - New thing
  - version: "1.0.0"
    date: "2024-01-01"
    yanked: true
    changes:
      added:
        - Initial release
  - unreleased: true
    changes:
      fixed:
        - Pending fix
"""

YAML_FLAT_ENTRIES = """\
releases:
  - version: "1.0.0"
    date: 2024-01-01
    entries:
      - text: Added a thing
        type: added
      - text: Fixed a bug
        type: fixed
"""

MD_SAMPLE = """\
# MD Project

## [1.0.0] - 2024-01-01

### Added
- a
"""


class TestRegistry:
    def test_builtin_formats_registered(self):
        assert "markdown" in available_formats()
        assert "yaml" in available_formats()

    def test_get_unknown_format_raises(self):
        with pytest.raises(ValueError, match="Unknown changelog format"):
            get_format("toml")

    def test_explicit_format_selection(self):
        cl = parse(YAML_SAMPLE, format="yaml")
        assert cl.title == "My YAML Project"

    def test_third_party_format_registration(self):
        class UpperFormat(FormatParser):
            name = "upper"
            extensions = (".upper",)

            def parse(self, text):
                from patchnotes import Changelog
                return Changelog(title=text.strip().upper())

        register_format(UpperFormat())
        try:
            assert "upper" in available_formats()
            cl = parse("hello", format="upper")
            assert cl.title == "HELLO"
        finally:
            # keep the registry clean for other tests
            from patchnotes.formats import _REGISTRY
            _REGISTRY.pop("upper", None)


class TestAutoDetection:
    def test_detect_markdown_by_content(self):
        assert detect_format(MD_SAMPLE).name == "markdown"

    def test_detect_yaml_by_content(self):
        assert detect_format(YAML_SAMPLE).name == "yaml"

    def test_detect_by_filename(self, tmp_path):
        f = tmp_path / "changelog.yml"
        f.write_text(YAML_SAMPLE, encoding="utf-8")
        cl = parse_file(str(f))
        assert cl.title == "My YAML Project"

    def test_markdown_file_still_default(self, tmp_path):
        f = tmp_path / "CHANGELOG.md"
        f.write_text(MD_SAMPLE, encoding="utf-8")
        cl = parse_file(str(f))
        assert cl.title == "MD Project"


class TestYamlFormat:
    def test_parses_releases(self):
        cl = parse(YAML_SAMPLE, format="yaml")
        assert len(cl.releases) == 3
        assert cl.latest().version == "2.0.0"

    def test_dates_from_yaml_native_and_string(self):
        cl = parse(YAML_SAMPLE, format="yaml")
        assert cl.get_version("2.0.0").release_date.isoformat() == "2024-06-01"
        assert cl.get_version("1.0.0").release_date.isoformat() == "2024-01-01"

    def test_yanked(self):
        cl = parse(YAML_SAMPLE, format="yaml")
        assert cl.get_version("1.0.0").yanked is True

    def test_unreleased_block(self):
        cl = parse(YAML_SAMPLE, format="yaml")
        u = cl.unreleased()
        assert u is not None
        assert u.entries[0].change_type is ChangeType.FIXED

    def test_change_types(self):
        cl = parse(YAML_SAMPLE, format="yaml")
        r = cl.get_version("2.0.0")
        assert {e.change_type for e in r.entries} == {
            ChangeType.BREAKING,
            ChangeType.ADDED,
        }
        assert len(r.breaking_changes) == 1

    def test_flat_entries_schema(self):
        cl = parse(YAML_FLAT_ENTRIES, format="yaml")
        r = cl.get_version("1.0.0")
        assert len(r.entries) == 2
        assert r.entries[1].change_type is ChangeType.FIXED

    def test_missing_releases_key_is_error(self):
        issues = validate("title: whoops\n", format="yaml")
        assert any(i.code == codes.YAML_SCHEMA for i in issues)

    def test_release_missing_version_skipped(self):
        text = "releases:\n  - date: 2024-01-01\n"
        cl = parse(text, format="yaml")
        assert cl.releases == []
        assert any(i.code == codes.YAML_SCHEMA for i in cl.validate())

    def test_invalid_yaml_reported_not_raised(self):
        cl = parse("releases: [unclosed", format="yaml")
        assert cl.releases == []
        assert any(i.code == codes.YAML_SCHEMA for i in cl.validate())

    def test_unknown_change_type_warning(self):
        text = (
            "releases:\n"
            "  - version: '1.0.0'\n"
            "    changes:\n"
            "      misc:\n"
            "        - something\n"
        )
        cl = parse(text, format="yaml")
        r = cl.get_version("1.0.0")
        assert r.entries[0].change_type is ChangeType.CHANGED
        assert any(i.code == codes.UNKNOWN_CHANGE_TYPE for i in cl.validate())

    def test_roundtrip_query_api_parity(self):
        """YAML-parsed changelogs support the same query API as markdown."""
        cl = parse(YAML_SAMPLE, format="yaml")
        assert cl.diff("1.0.0", "2.0.0")[0].version == "2.0.0"
        assert cl.all_breaking_changes()[0][0] == "2.0.0"
        assert cl.to_dict()["title"] == "My YAML Project"
