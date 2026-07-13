"""
tests/test_validation.py
Tests for lenient parsing, strict mode, and cl.validate().
"""

import pytest

from patchnotes import (
    ChangelogValidationError,
    Severity,
    parse,
    validate,
)
from patchnotes import _validation as codes

GOOD = """\
# Good Project

## [1.1.0] - 2024-02-01

### Added
- Something

## [1.0.0] - 2024-01-01

### Added
- Initial release
"""

BAD_DATE = """\
## [1.0.0] - 2024/01/01

### Added
- Thing
"""

UNKNOWN_SECTION = """\
## [1.0.0] - 2024-01-01

### Improvements
- Faster startup
"""

DUPLICATE = """\
## [1.0.0] - 2024-01-01

### Added
- a

## [1.0.0] - 2024-01-02

### Fixed
- b
"""

OUT_OF_ORDER = """\
## [1.0.0] - 2024-01-01

### Added
- a

## [2.0.0] - 2024-06-01

### Added
- b
"""

BARE_HEADER = """\
## 1.0.0 - 2024-01-01

### Added
- a
"""

ORPHAN_BULLET = """\
# Title

- floating bullet

## [1.0.0] - 2024-01-01

### Added
- a
"""

EMPTY_RELEASE = """\
## [1.1.0] - 2024-02-01

## [1.0.0] - 2024-01-01

### Added
- a
"""


class TestLenientParsing:
    def test_clean_changelog_has_no_issues(self):
        assert validate(GOOD) == []

    def test_bad_date_recovers_and_reports(self):
        cl = parse(BAD_DATE)
        r = cl.get_version("1.0.0")
        assert r is not None
        assert r.release_date is not None  # recovered from 2024/01/01
        assert r.release_date.isoformat() == "2024-01-01"
        assert any(i.code == codes.BAD_DATE for i in cl.validate())

    def test_unknown_section_maps_to_changed(self):
        cl = parse(UNKNOWN_SECTION)
        r = cl.get_version("1.0.0")
        assert len(r.entries) == 1
        issues = cl.validate()
        assert any(i.code == codes.UNKNOWN_CHANGE_TYPE for i in issues)
        assert all(i.severity is Severity.WARNING for i in issues)

    def test_known_alias_maps_correctly(self):
        cl = parse("## [1.0.0] - 2024-01-01\n\n### Bug Fixes\n- x\n")
        r = cl.get_version("1.0.0")
        assert r.entries[0].change_type.value == "Fixed"

    def test_duplicate_version_is_error(self):
        issues = validate(DUPLICATE)
        dups = [i for i in issues if i.code == codes.DUPLICATE_VERSION]
        assert len(dups) == 1
        assert dups[0].severity is Severity.ERROR

    def test_out_of_order_warning(self):
        issues = validate(OUT_OF_ORDER)
        assert any(i.code == codes.VERSIONS_OUT_OF_ORDER for i in issues)

    def test_bare_header_parses_with_warning(self):
        cl = parse(BARE_HEADER)
        assert cl.get_version("1.0.0") is not None
        assert any(i.code == codes.MALFORMED_HEADER for i in cl.validate())

    def test_orphan_bullet_skipped_with_warning(self):
        cl = parse(ORPHAN_BULLET)
        assert len(cl.get_version("1.0.0").entries) == 1
        assert any(i.code == codes.ENTRY_OUTSIDE_RELEASE for i in cl.validate())

    def test_empty_release_warning(self):
        issues = validate(EMPTY_RELEASE)
        assert any(i.code == codes.EMPTY_RELEASE for i in issues)

    def test_empty_document_warns_no_releases(self):
        issues = validate("")
        assert any(i.code == codes.NO_RELEASES for i in issues)

    def test_issue_line_numbers(self):
        cl = parse(BAD_DATE)
        issue = [i for i in cl.validate() if i.code == codes.BAD_DATE][0]
        assert issue.line == 1


class TestStrictMode:
    def test_strict_ok_on_clean(self):
        cl = parse(GOOD, strict=True)
        assert cl.latest().version == "1.1.0"

    def test_strict_raises_on_error(self):
        with pytest.raises(ChangelogValidationError) as exc:
            parse(DUPLICATE, strict=True)
        assert any(i.code == codes.DUPLICATE_VERSION for i in exc.value.issues)

    def test_strict_tolerates_warnings(self):
        # Warnings (unknown section) should not raise in strict parse
        cl = parse(UNKNOWN_SECTION, strict=True)
        assert cl.get_version("1.0.0") is not None

    def test_strict_raises_on_bad_date(self):
        with pytest.raises(ChangelogValidationError):
            parse(BAD_DATE, strict=True)


class TestValidateApi:
    def test_is_valid(self):
        assert parse(GOOD).is_valid()
        assert parse(UNKNOWN_SECTION).is_valid()          # warnings ok
        assert not parse(UNKNOWN_SECTION).is_valid(strict=True)
        assert not parse(DUPLICATE).is_valid()

    def test_issue_to_dict(self):
        issue = validate(BAD_DATE)[0]
        d = issue.to_dict()
        assert set(d) == {"code", "message", "severity", "line"}

    def test_issue_str_contains_code_and_line(self):
        issue = [i for i in validate(BAD_DATE) if i.code == codes.BAD_DATE][0]
        s = str(issue)
        assert codes.BAD_DATE in s
        assert "line 1" in s
