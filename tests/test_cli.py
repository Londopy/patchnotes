"""
tests/test_cli.py
Tests for the CLI: exit codes, JSON output, validate, stdin, GH annotations.
"""

import io
import json

import pytest
from patchnotes._cli import EXIT_FAIL, EXIT_OK, EXIT_USAGE, main

GOOD = """\
# Proj

## [1.1.0] - 2024-02-01

### Added
- New thing

## [1.0.0] - 2024-01-01

### Added
- Initial release
"""

BROKEN = """\
## [1.0.0] - 01-02-2024

### Added
- a

## [1.0.0] - 2024-01-01

### Added
- b
"""

WARNY = """\
## [1.0.0] - 2024-01-01

### Improvements
- faster
"""


@pytest.fixture
def good_file(tmp_path):
    f = tmp_path / "CHANGELOG.md"
    f.write_text(GOOD, encoding="utf-8")
    return str(f)


@pytest.fixture
def broken_file(tmp_path):
    f = tmp_path / "CHANGELOG.md"
    f.write_text(BROKEN, encoding="utf-8")
    return str(f)


@pytest.fixture
def warny_file(tmp_path):
    f = tmp_path / "CHANGELOG.md"
    f.write_text(WARNY, encoding="utf-8")
    return str(f)


class TestExitCodes:
    def test_summary_ok(self, good_file, capsys):
        assert main([good_file]) == EXIT_OK
        assert "1.1.0" in capsys.readouterr().out

    def test_missing_file_is_usage_error(self):
        assert main(["/nonexistent/CHANGELOG.md"]) == EXIT_USAGE

    def test_show_missing_version_fails(self, good_file):
        assert main([good_file, "show", "9.9.9"]) == EXIT_FAIL

    def test_validate_ok(self, good_file):
        assert main([good_file, "validate"]) == EXIT_OK

    def test_validate_broken_fails(self, broken_file):
        assert main([broken_file, "validate"]) == EXIT_FAIL

    def test_validate_warnings_pass_by_default(self, warny_file):
        assert main([warny_file, "validate"]) == EXIT_OK

    def test_validate_strict_fails_on_warnings(self, warny_file):
        assert main([warny_file, "validate", "--strict"]) == EXIT_FAIL

    def test_global_strict_blocks_other_commands(self, broken_file):
        assert main(["--strict", broken_file, "latest"]) == EXIT_FAIL

    def test_global_strict_allows_clean(self, good_file):
        assert main(["--strict", good_file, "latest"]) == EXIT_OK


class TestJsonOutput:
    def test_latest_json(self, good_file, capsys):
        assert main([good_file, "--format", "json", "latest"]) == EXIT_OK
        data = json.loads(capsys.readouterr().out)
        assert data["version"] == "1.1.0"

    def test_validate_json_shape(self, broken_file, capsys):
        main([broken_file, "--format", "json", "validate"])
        data = json.loads(capsys.readouterr().out)
        assert data["valid"] is False
        assert data["errors"] >= 1
        assert isinstance(data["issues"], list)
        assert {"code", "message", "severity", "line"} <= set(data["issues"][0])

    def test_diff_json(self, good_file, capsys):
        assert main([good_file, "--format", "json", "diff", "1.0.0", "1.1.0"]) == EXIT_OK
        data = json.loads(capsys.readouterr().out)
        assert [r["version"] for r in data] == ["1.1.0"]

    def test_breaking_json(self, good_file, capsys):
        assert main([good_file, "--format", "json", "breaking"]) == EXIT_OK
        assert json.loads(capsys.readouterr().out) == []

    def test_summary_json(self, good_file, capsys):
        assert main([good_file, "--format", "json"]) == EXIT_OK
        data = json.loads(capsys.readouterr().out)
        assert len(data["releases"]) == 2


class TestStdin:
    def test_reads_from_dash(self, monkeypatch, capsys):
        monkeypatch.setattr("sys.stdin", io.StringIO(GOOD))
        assert main(["-", "latest"]) == EXIT_OK
        assert "1.1.0" in capsys.readouterr().out

    def test_validate_from_stdin(self, monkeypatch):
        monkeypatch.setattr("sys.stdin", io.StringIO(BROKEN))
        assert main(["-", "validate"]) == EXIT_FAIL


class TestGithubAnnotations:
    def test_github_flag_emits_annotations(self, broken_file, capsys):
        main([broken_file, "--github", "validate"])
        out = capsys.readouterr().out
        assert "::error file=" in out
        assert "line=" in out

    def test_env_var_enables_annotations(self, broken_file, capsys, monkeypatch):
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        main([broken_file, "validate"])
        assert "::error file=" in capsys.readouterr().out

    def test_no_annotations_by_default(self, broken_file, capsys, monkeypatch):
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        main([broken_file, "validate"])
        assert "::error" not in capsys.readouterr().out


class TestQuiet:
    def test_quiet_validate_ok_prints_nothing(self, good_file, capsys):
        assert main([good_file, "--quiet", "validate"]) == EXIT_OK
        assert capsys.readouterr().out == ""
