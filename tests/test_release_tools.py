"""
tests/test_release_tools.py
Tests for v2.1.0 features: bump, writers, compare links, and the new
CLI commands (bump, convert, fix, unreleased --fail-if-empty).
"""

from datetime import date

import pytest
from patchnotes import (
    ChangeType,
    parse,
    parse_file,
    to_markdown,
    to_yaml,
)
from patchnotes import _validation as codes
from patchnotes._cli import EXIT_FAIL, EXIT_OK, EXIT_USAGE, main

LINKED = """\
# Linked Project

## [Unreleased]

### Added
- Pending thing

## [1.1.0] - 2024-02-01

### Added
- Feature

## [1.0.0] - 2024-01-01

### Added
- Initial release

[unreleased]: https://github.com/Londopy/linked/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/Londopy/linked/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/Londopy/linked/releases/tag/v1.0.0
"""

PLAIN = """\
# Plain Project

## [Unreleased]

### Added
- Pending thing

## [1.0.0] - 2024-01-01

### Added
- Initial release
"""

MESSY = """\
## 1.0.0 - 2024/01/01

### Improvements
- Faster startup
"""


# ── Compare links ─────────────────────────────────────────────────────────────

class TestLinks:
    def test_links_parsed(self):
        cl = parse(LINKED)
        assert cl.links["1.1.0"].endswith("compare/v1.0.0...v1.1.0")
        assert len(cl.links) == 3

    def test_links_not_in_description(self):
        cl = parse(LINKED)
        assert "https://" not in cl.description

    def test_clean_linked_changelog_validates(self):
        assert parse(LINKED).validate() == []

    def test_no_links_no_warnings(self):
        assert parse(PLAIN).validate() == []

    def test_missing_link_warning(self):
        text = LINKED.replace(
            "[1.1.0]: https://github.com/Londopy/linked/compare/v1.0.0...v1.1.0\n",
            "",
        )
        issues = parse(text).validate()
        assert any(i.code == codes.MISSING_COMPARE_LINK for i in issues)

    def test_orphan_link_warning(self):
        text = LINKED + "[9.9.9]: https://github.com/Londopy/linked/releases/tag/v9.9.9\n"
        issues = parse(text).validate()
        assert any(i.code == codes.ORPHAN_COMPARE_LINK for i in issues)


# ── bump() ────────────────────────────────────────────────────────────────────

class TestBump:
    def test_bump_creates_release(self):
        cl = parse(PLAIN)
        r = cl.bump("1.1.0", release_date=date(2026, 7, 13))
        assert r.version == "1.1.0"
        assert r.release_date == date(2026, 7, 13)
        assert [e.text for e in r.entries] == ["Pending thing"]

    def test_bump_defaults_to_today(self):
        cl = parse(PLAIN)
        r = cl.bump("1.1.0")
        assert r.release_date == date.today()

    def test_bump_keeps_empty_unreleased(self):
        cl = parse(PLAIN)
        cl.bump("1.1.0")
        u = cl.unreleased()
        assert u is not None
        assert u.entries == []
        assert cl.releases[0] is u                # still on top
        assert cl.latest().version == "1.1.0"

    def test_bump_can_drop_unreleased(self):
        cl = parse(PLAIN)
        cl.bump("1.1.0", keep_unreleased=False)
        assert cl.unreleased() is None

    def test_bump_empty_unreleased_raises(self):
        cl = parse(PLAIN)
        cl.bump("1.1.0")
        with pytest.raises(ValueError, match="no unreleased changes"):
            cl.bump("1.2.0")

    def test_bump_duplicate_version_raises(self):
        cl = parse(PLAIN)
        with pytest.raises(ValueError, match="already exists"):
            cl.bump("1.0.0")

    def test_bump_maintains_links(self):
        cl = parse(LINKED)
        cl.bump("1.2.0")
        assert cl.links["1.2.0"].endswith("compare/v1.1.0...v1.2.0")
        assert cl.links["unreleased"].endswith("compare/v1.2.0...HEAD")

    def test_bump_without_links_is_fine(self):
        cl = parse(PLAIN)
        cl.bump("1.1.0")
        assert cl.links == {}


# ── Writers ───────────────────────────────────────────────────────────────────

class TestToMarkdown:
    def test_roundtrip_preserves_structure(self):
        cl = parse(LINKED)
        cl2 = parse(to_markdown(cl))
        assert [r.version for r in cl2.releases] == [r.version for r in cl.releases]
        assert cl2.links == cl.links
        assert cl2.title == cl.title
        assert cl2.validate() == []

    def test_yanked_preserved(self):
        text = "## [1.0.0] - 2024-01-01 [YANKED]\n\n### Fixed\n- x\n"
        cl2 = parse(to_markdown(parse(text)))
        assert cl2.get_version("1.0.0").yanked is True

    def test_generated_links(self):
        cl = parse(PLAIN)
        md = to_markdown(cl, repo_url="https://github.com/Londopy/plain")
        cl2 = parse(md)
        assert cl2.links["1.0.0"].endswith("releases/tag/v1.0.0")
        assert cl2.links["Unreleased"].endswith("compare/v1.0.0...HEAD")
        assert cl2.validate() == []

    def test_normalizes_messy_input(self):
        cl2 = parse(to_markdown(parse(MESSY)))
        assert cl2.validate() == []                     # clean after rewrite
        r = cl2.get_version("1.0.0")
        assert r.release_date == date(2024, 1, 1)       # recovered date kept


class TestToYaml:
    def test_roundtrip(self):
        cl = parse(LINKED)
        cl2 = parse(to_yaml(cl), format="yaml")
        assert [r.version for r in cl2.releases] == [r.version for r in cl.releases]
        assert cl2.unreleased() is not None
        r = cl2.get_version("1.0.0")
        assert r.entries[0].change_type is ChangeType.ADDED

    def test_yanked_roundtrip(self):
        text = "## [1.0.0] - 2024-01-01 [YANKED]\n\n### Fixed\n- x\n"
        cl2 = parse(to_yaml(parse(text)), format="yaml")
        assert cl2.get_version("1.0.0").yanked is True


# ── CLI ───────────────────────────────────────────────────────────────────────

@pytest.fixture
def plain_file(tmp_path):
    f = tmp_path / "CHANGELOG.md"
    f.write_text(PLAIN, encoding="utf-8")
    return str(f)


@pytest.fixture
def messy_file(tmp_path):
    f = tmp_path / "CHANGELOG.md"
    f.write_text(MESSY, encoding="utf-8")
    return str(f)


class TestCliBump:
    def test_bump_writes_file(self, plain_file, capsys):
        assert main([plain_file, "bump", "1.1.0", "--date", "2026-07-13"]) == EXIT_OK
        cl = parse_file(plain_file)
        assert cl.latest().version == "1.1.0"
        assert cl.unreleased().entries == []

    def test_bump_bad_date(self, plain_file):
        assert main([plain_file, "bump", "1.1.0", "--date", "nope"]) == EXIT_USAGE

    def test_bump_nothing_to_release(self, plain_file):
        main([plain_file, "bump", "1.1.0"])
        assert main([plain_file, "bump", "1.2.0"]) == EXIT_FAIL


class TestCliFailIfEmpty:
    def test_fails_when_empty(self, plain_file):
        main([plain_file, "bump", "1.1.0"])         # empties [Unreleased]
        assert main([plain_file, "unreleased", "--fail-if-empty"]) == EXIT_FAIL

    def test_passes_with_entries(self, plain_file):
        assert main([plain_file, "unreleased", "--fail-if-empty"]) == EXIT_OK


class TestCliConvert:
    def test_md_to_yaml_and_back(self, plain_file, tmp_path):
        yml = str(tmp_path / "changelog.yml")
        assert main([plain_file, "convert", yml]) == EXIT_OK
        md2 = str(tmp_path / "out.md")
        assert main([yml, "convert", md2]) == EXIT_OK
        assert parse_file(md2).latest().version == "1.0.0"

    def test_unknown_output_extension(self, plain_file, tmp_path):
        assert main([plain_file, "convert", str(tmp_path / "x.toml")]) == EXIT_USAGE


class TestCliFix:
    def test_fix_normalizes_in_place(self, messy_file):
        assert main([messy_file, "fix"]) == EXIT_OK
        cl = parse_file(messy_file)
        assert cl.validate() == []
        assert cl.get_version("1.0.0").release_date == date(2024, 1, 1)

    def test_fix_accepts_trailing_file(self, messy_file):
        # pre-commit style: patchnotes fix CHANGELOG.md
        assert main(["fix", messy_file]) == EXIT_OK
        assert parse_file(messy_file).validate() == []

    def test_validate_accepts_trailing_file(self, plain_file):
        assert main(["validate", plain_file]) == EXIT_OK
