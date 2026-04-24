"""
tests/test_parser.py
Comprehensive tests for patchnotes parser.
Run with: pytest tests/
"""

import pytest
from datetime import date
from patchnotes import parse, parse_file, Changelog, Release, Entry, ChangeType

# ── Fixtures ──────────────────────────────────────────────────────────────────

SAMPLE = """\
# My Awesome Library

A library for doing awesome things.

## [Unreleased]

### Added
- Dark mode support
- New `export_csv()` function

## [2.1.0] - 2024-11-15

### Added
- WebSocket support for real-time updates
- New `batch_process()` method for handling multiple items at once
- Configurable retry logic with exponential backoff

### Fixed
- Memory leak in connection pool when connections timeout
- Incorrect timezone handling in `parse_datetime()` for UTC offsets

### Changed
- Improved error messages to include context and suggested fixes

## [2.0.0] - 2024-09-01

### Breaking
- Renamed `connect()` to `open_connection()` — update all call sites
- Removed deprecated `legacy_auth` parameter from `authenticate()`

### Added
- Full async/await support across all public API methods
- Plugin architecture for custom data processors
- Type stubs (.pyi files) for better IDE support

### Removed
- Dropped support for Python 3.8 and 3.9
- Removed `SyncClient` class — use `AsyncClient` with `asyncio.run()`

### Security
- Patched SSRF vulnerability in URL validation logic (CVE-2024-1234)

## [1.4.2] - 2024-06-10

### Fixed
- Crash when input file contains null bytes
- Race condition in multi-threaded download manager
- Off-by-one error in pagination cursor calculation

### Security
- Updated dependencies to address CVE-2024-5678 in requests library

## [1.4.0] - 2024-04-22

### Added
- Support for gzip-compressed responses
- `Changelog.from_url()` class method for remote changelogs

### Changed
- Default timeout increased from 10s to 30s
- Logging now uses structured JSON format

### Deprecated
- `SyncClient` is deprecated and will be removed in v2.0.0
"""

YANKED_SAMPLE = """\
# Test

## [1.2.0] - 2024-01-01 [YANKED]

### Fixed
- Critical bug fix
"""

MINIMAL = """\
## [1.0.0] - 2023-01-01

### Added
- Initial release
"""


@pytest.fixture
def cl():
    return parse(SAMPLE)


# ── Basic parsing ─────────────────────────────────────────────────────────────

class TestBasicParsing:
    def test_title(self, cl):
        assert cl.title == "My Awesome Library"

    def test_description(self, cl):
        assert "doing awesome things" in cl.description

    def test_release_count(self, cl):
        assert len(cl.releases) == 5  # Unreleased + 4 versioned

    def test_release_versions(self, cl):
        versions = [r.version for r in cl.releases]
        assert "Unreleased" in versions
        assert "2.1.0" in versions
        assert "2.0.0" in versions
        assert "1.4.2" in versions
        assert "1.4.0" in versions

    def test_release_dates(self, cl):
        r = cl.get_version("2.1.0")
        assert r.release_date == date(2024, 11, 15)

    def test_unreleased_has_no_date(self, cl):
        r = cl.unreleased()
        assert r.release_date is None

    def test_entry_count(self, cl):
        r = cl.get_version("2.1.0")
        assert len(r.entries) == 6

    def test_entry_text(self, cl):
        r = cl.get_version("2.1.0")
        texts = [e.text for e in r.entries]
        assert "WebSocket support for real-time updates" in texts

    def test_entry_change_type(self, cl):
        r = cl.get_version("2.1.0")
        added = [e for e in r.entries if e.change_type == ChangeType.ADDED]
        assert len(added) == 3

    def test_minimal_changelog(self):
        cl = parse(MINIMAL)
        assert len(cl.releases) == 1
        assert cl.releases[0].version == "1.0.0"

    def test_empty_string(self):
        cl = parse("")
        assert len(cl.releases) == 0
        assert cl.title == "Changelog"


# ── Yanked ────────────────────────────────────────────────────────────────────

class TestYanked:
    def test_yanked_flag(self):
        cl = parse(YANKED_SAMPLE)
        r = cl.get_version("1.2.0")
        assert r is not None
        assert r.yanked is True

    def test_not_yanked_by_default(self, cl):
        r = cl.get_version("2.1.0")
        assert r.yanked is False


# ── Changelog methods ─────────────────────────────────────────────────────────

class TestChangelogMethods:
    def test_latest(self, cl):
        r = cl.latest()
        assert r is not None
        assert r.version == "2.1.0"

    def test_latest_no_releases(self):
        cl = parse("# Test\n\n## [Unreleased]\n\n### Added\n- thing\n")
        assert cl.latest() is None

    def test_unreleased(self, cl):
        r = cl.unreleased()
        assert r is not None
        assert r.is_unreleased is True
        assert r.version == "Unreleased"

    def test_get_version_found(self, cl):
        r = cl.get_version("2.0.0")
        assert r is not None
        assert r.version == "2.0.0"

    def test_get_version_not_found(self, cl):
        assert cl.get_version("99.0.0") is None

    def test_since_version(self, cl):
        results = cl.since_version("1.4.0")
        versions = [r.version for r in results]
        assert "2.1.0" in versions
        assert "2.0.0" in versions
        assert "1.4.2" in versions
        assert "1.4.0" not in versions  # exclusive
        assert "Unreleased" in versions

    def test_since_version_latest(self, cl):
        results = cl.since_version("2.1.0")
        versions = [r.version for r in results]
        assert "Unreleased" in versions
        assert "2.1.0" not in versions

    def test_all_breaking_changes(self, cl):
        breaking = cl.all_breaking_changes()
        assert len(breaking) > 0
        versions = [v for v, _ in breaking]
        assert "2.0.0" in versions

    def test_repr(self, cl):
        assert "5 releases" in repr(cl)


# ── diff() ────────────────────────────────────────────────────────────────────

class TestDiff:
    def test_diff_basic(self, cl):
        releases = cl.diff("1.4.0", "2.1.0")
        versions = [r.version for r in releases]
        assert "2.1.0" in versions
        assert "2.0.0" in versions
        assert "1.4.2" in versions
        assert "1.4.0" not in versions   # from_version excluded
        assert "Unreleased" not in versions

    def test_diff_excludes_from_version(self, cl):
        releases = cl.diff("1.4.2", "2.0.0")
        versions = [r.version for r in releases]
        assert "1.4.2" not in versions
        assert "2.0.0" in versions

    def test_diff_invalid_order(self, cl):
        with pytest.raises(ValueError):
            cl.diff("2.1.0", "1.4.0")

    def test_diff_no_results(self, cl):
        # No releases between 1.4.0 and 1.4.0 (would be same version, raises)
        with pytest.raises(ValueError):
            cl.diff("1.4.0", "1.4.0")


# ── Release properties ────────────────────────────────────────────────────────

class TestReleaseProperties:
    def test_by_type(self, cl):
        r = cl.get_version("2.1.0")
        bt = r.by_type
        assert "Added" in bt
        assert "Fixed" in bt
        assert "Changed" in bt
        assert len(bt["Added"]) == 3

    def test_breaking_changes_includes_breaking(self, cl):
        r = cl.get_version("2.0.0")
        bc = r.breaking_changes
        types = {e.change_type for e in bc}
        assert ChangeType.BREAKING in types

    def test_breaking_changes_includes_removed(self, cl):
        r = cl.get_version("2.0.0")
        bc = r.breaking_changes
        types = {e.change_type for e in bc}
        assert ChangeType.REMOVED in types

    def test_release_repr(self, cl):
        r = cl.get_version("2.1.0")
        assert "2.1.0" in repr(r)
        assert "6 entries" in repr(r)


# ── Serialization ─────────────────────────────────────────────────────────────

class TestSerialization:
    def test_entry_to_dict(self, cl):
        r = cl.get_version("2.1.0")
        d = r.entries[0].to_dict()
        assert "text" in d
        assert "change_type" in d

    def test_release_to_dict(self, cl):
        r = cl.get_version("2.1.0")
        d = r.to_dict()
        assert d["version"] == "2.1.0"
        assert d["release_date"] == "2024-11-15"
        assert isinstance(d["entries"], list)
        assert isinstance(d["by_type"], dict)

    def test_changelog_to_dict(self, cl):
        d = cl.to_dict()
        assert d["title"] == "My Awesome Library"
        assert isinstance(d["releases"], list)
        assert len(d["releases"]) == 5

    def test_to_json_valid(self, cl):
        import json
        j = cl.to_json()
        parsed = json.loads(j)
        assert parsed["title"] == "My Awesome Library"

    def test_to_json_indent(self, cl):
        j = cl.to_json(indent=4)
        assert "    " in j  # 4-space indent


# ── parse_file() ──────────────────────────────────────────────────────────────

class TestParseFile:
    def test_parse_file(self, tmp_path):
        f = tmp_path / "CHANGELOG.md"
        f.write_text(SAMPLE, encoding="utf-8")
        cl = parse_file(str(f))
        assert cl.title == "My Awesome Library"
        assert len(cl.releases) == 5

    def test_parse_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            parse_file("/nonexistent/CHANGELOG.md")
