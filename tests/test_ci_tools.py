"""
tests/test_ci_tools.py
Tests for v2.2.0: check-version, fragments, dep diffs, SARIF, badge.
"""

import json

import pytest

from patchnotes import ChangeType, parse, parse_file
from patchnotes._cli import EXIT_FAIL, EXIT_OK, EXIT_USAGE, main
from patchnotes._depdiff import find_github_repo, render_dep_diff

CL = """\
# Proj

## [Unreleased]

### Added
- Pending

## [2.1.0] - 2026-07-13

### Added
- Feature

## [2.0.0] - 2026-06-01

### Breaking
- Renamed foo() to bar()

### Security
- Patched CVE-2026-0001

## [1.9.0] - 2026-05-01

### Fixed
- Small bug
"""


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "CHANGELOG.md").write_text(CL, encoding="utf-8")
    return tmp_path


# ── check-version ─────────────────────────────────────────────────────────────

class TestCheckVersion:
    def test_match_pyproject(self, repo):
        (repo / "pyproject.toml").write_text('[project]\nversion = "2.1.0"\n')
        assert main([str(repo / "CHANGELOG.md"), "check-version"]) == EXIT_OK

    def test_mismatch_fails(self, repo, capsys):
        (repo / "pyproject.toml").write_text('[project]\nversion = "2.0.4"\n')
        assert main([str(repo / "CHANGELOG.md"), "check-version"]) == EXIT_FAIL
        assert "mismatch" in capsys.readouterr().err.lower()

    def test_against_literal_with_v_prefix(self, repo):
        f = str(repo / "CHANGELOG.md")
        assert main([f, "check-version", "--against", "v2.1.0"]) == EXIT_OK
        assert main([f, "check-version", "--against", "v2.0.0"]) == EXIT_FAIL

    def test_against_package_json(self, repo):
        (repo / "package.json").write_text('{"version": "2.1.0"}')
        f = str(repo / "CHANGELOG.md")
        assert main([f, "check-version", "--against", str(repo / "package.json")]) == EXIT_OK

    def test_no_metadata_found(self, repo):
        assert main([str(repo / "CHANGELOG.md"), "check-version"]) == EXIT_USAGE

    def test_bad_against(self, repo):
        f = str(repo / "CHANGELOG.md")
        assert main([f, "check-version", "--against", "nonsense!"]) == EXIT_USAGE


# ── Fragments ─────────────────────────────────────────────────────────────────

class TestFragments:
    def test_add_and_list(self, repo, capsys):
        f = str(repo / "CHANGELOG.md")
        assert main([f, "fragment", "add", "fixed", "Squashed a bug"]) == EXIT_OK
        assert main([f, "fragment", "add", "added", "New knob"]) == EXIT_OK
        capsys.readouterr()
        assert main([f, "fragment", "list"]) == EXIT_OK
        out = capsys.readouterr().out
        assert "Squashed a bug" in out and "[Fixed]" in out

    def test_add_unknown_type(self, repo):
        f = str(repo / "CHANGELOG.md")
        assert main([f, "fragment", "add", "misc", "x"]) == EXIT_USAGE

    def test_bump_collect(self, repo):
        f = str(repo / "CHANGELOG.md")
        main([f, "fragment", "add", "fixed", "Squashed a bug"])
        assert main([f, "bump", "2.2.0", "--collect", "--date", "2026-07-19"]) == EXIT_OK
        cl = parse_file(f)
        r = cl.get_version("2.2.0")
        texts = [e.text for e in r.entries]
        assert "Squashed a bug" in texts and "Pending" in texts
        # fragments consumed
        assert list((repo / "changelog.d").glob("*.md")) == []

    def test_bump_collect_with_empty_unreleased(self, repo):
        f = str(repo / "CHANGELOG.md")
        main([f, "bump", "2.2.0"])                      # empties [Unreleased]
        main([f, "fragment", "add", "added", "From fragment only"])
        assert main([f, "bump", "2.3.0", "--collect"]) == EXIT_OK
        cl = parse_file(f)
        assert [e.text for e in cl.get_version("2.3.0").entries] == ["From fragment only"]

    def test_fail_if_empty_sees_fragments_with_collect(self, repo):
        f = str(repo / "CHANGELOG.md")
        main([f, "bump", "2.2.0"])                      # empties [Unreleased]
        assert main([f, "unreleased", "--fail-if-empty"]) == EXIT_FAIL
        main([f, "fragment", "add", "fixed", "Pending fix"])
        assert main([f, "unreleased", "--fail-if-empty", "--collect"]) == EXIT_OK


# ── dep ───────────────────────────────────────────────────────────────────────

class TestDep:
    def test_find_github_repo(self, monkeypatch):
        import patchnotes._depdiff as dd
        monkeypatch.setattr(dd, "_get_json", lambda url: {
            "info": {"project_urls": {"Source": "https://github.com/psf/requests"},
                     "home_page": ""}})
        assert find_github_repo("requests") == ("psf", "requests")

    def test_find_github_repo_missing(self, monkeypatch):
        import patchnotes._depdiff as dd
        monkeypatch.setattr(dd, "_get_json", lambda url: {
            "info": {"project_urls": {"Docs": "https://example.com"}, "home_page": ""}})
        with pytest.raises(ValueError, match="GitHub repository"):
            find_github_repo("whatever")

    def test_render_flags_breaking_and_security(self):
        cl = parse(CL)
        text, flagged = render_dep_diff(cl, "proj", "1.9.0", "2.1.0")
        assert flagged == 2
        assert "! [Breaking] Renamed foo() to bar()" in text
        assert "! [Security] Patched CVE-2026-0001" in text
        assert "Small bug" not in text                  # 1.9.0 excluded (from is exclusive)

    def test_render_show_all(self):
        cl = parse(CL)
        text, _ = render_dep_diff(cl, "proj", "1.9.0", "2.1.0", show_all=True)
        assert "- [Added] Feature" in text

    def test_render_empty_range(self):
        cl = parse(CL)
        text, flagged = render_dep_diff(cl, "proj", "2.1.0", "9.9.9")
        assert flagged == 0
        assert "No releases found" in text


# ── SARIF ─────────────────────────────────────────────────────────────────────

BROKEN = "## [1.0.0] - 2026/01/01\n\n### Improvments\n- x\n"


class TestSarif:
    def test_sarif_shape(self, tmp_path, capsys):
        f = tmp_path / "CHANGELOG.md"
        f.write_text(BROKEN, encoding="utf-8")
        rc = main([str(f), "--format", "sarif", "validate"])
        assert rc == EXIT_FAIL
        doc = json.loads(capsys.readouterr().out)
        assert doc["version"] == "2.1.0"
        run = doc["runs"][0]
        assert run["tool"]["driver"]["name"] == "patchnotes"
        levels = {r["level"] for r in run["results"]}
        assert levels == {"error", "warning"}
        assert all("physicalLocation" in r["locations"][0] for r in run["results"])

    def test_sarif_clean(self, repo, capsys):
        rc = main([str(repo / "CHANGELOG.md"), "--format", "sarif", "validate"])
        assert rc == EXIT_OK
        doc = json.loads(capsys.readouterr().out)
        assert doc["runs"][0]["results"] == []

    def test_sarif_rejected_elsewhere(self, repo):
        with pytest.raises(SystemExit):
            main([str(repo / "CHANGELOG.md"), "--format", "sarif", "latest"])


# ── badge ─────────────────────────────────────────────────────────────────────

class TestBadge:
    def test_badge_json(self, repo, capsys):
        assert main([str(repo / "CHANGELOG.md"), "badge"]) == EXIT_OK
        data = json.loads(capsys.readouterr().out)
        assert data == {
            "schemaVersion": 1,
            "label": "changelog",
            "message": "v2.1.0",
            "color": "orange",
        }


# ── RST/setext changelogs (requests-style HISTORY.md) ─────────────────────────

RST_STYLE = """\
Release History
===============

2.32.0 (2024-05-20)
-------------------

### Security
- Fixed cert verification issue

2.31.0 (2023-05-22)
-------------------

### Fixed
- Some bug
"""


class TestSetextHeaders:
    def test_rst_style_parses(self):
        cl = parse(RST_STYLE)
        assert [r.version for r in cl.releases] == ["2.32.0", "2.31.0"]
        r = cl.get_version("2.32.0")
        assert str(r.release_date) == "2024-05-20"
        assert r.entries[0].change_type is ChangeType.SECURITY

    def test_rst_style_reports_warning(self):
        from patchnotes import Severity
        issues = parse(RST_STYLE).validate()
        rst = [i for i in issues if "RST-style" in i.message]
        assert len(rst) == 2
        assert all(i.severity is Severity.WARNING for i in rst)

    def test_dep_diff_over_rst(self):
        cl = parse(RST_STYLE)
        text, flagged = render_dep_diff(cl, "requests", "2.31.0", "2.32.0")
        assert flagged == 1
        assert "Fixed cert verification issue" in text
