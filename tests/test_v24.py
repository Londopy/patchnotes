"""
tests/test_v24.py
Tests for v2.4.0: init, dep --requirements, mkdocs plugin, and the
empty-[Unreleased] validation fix.
"""


import pytest
from patchnotes import _validation as codes
from patchnotes import parse, parse_file
from patchnotes._cli import EXIT_FAIL, EXIT_OK, EXIT_USAGE, main
from patchnotes._depdiff import diff_requirements, parse_requirements

# ── Empty [Unreleased] is spec-normal ─────────────────────────────────────────


class TestEmptyUnreleased:
    def test_empty_unreleased_no_warning(self):
        cl = parse("## [Unreleased]\n\n## [1.0.0] - 2024-01-01\n\n### Added\n- x\n")
        assert not any(i.code == codes.EMPTY_RELEASE for i in cl.validate())

    def test_empty_versioned_release_still_warns(self):
        cl = parse("## [1.1.0] - 2024-02-01\n\n## [1.0.0] - 2024-01-01\n\n### Added\n- x\n")
        assert any(i.code == codes.EMPTY_RELEASE for i in cl.validate())

    def test_strict_validate_after_bump(self, tmp_path):
        f = tmp_path / "CHANGELOG.md"
        f.write_text("## [Unreleased]\n\n### Added\n- x\n", encoding="utf-8")
        assert main([str(f), "bump", "1.0.0"]) == EXIT_OK
        assert main([str(f), "validate", "--strict"]) == EXIT_OK


# ── init ──────────────────────────────────────────────────────────────────────

class TestInit:
    def test_creates_strict_valid_changelog(self, tmp_path):
        f = str(tmp_path / "CHANGELOG.md")
        assert main([f, "init"]) == EXIT_OK
        assert main([f, "validate", "--strict"]) == EXIT_OK
        cl = parse_file(f)
        assert cl.unreleased() is not None
        assert cl.unreleased().entries          # non-empty starter entry

    def test_refuses_overwrite(self, tmp_path):
        f = str(tmp_path / "CHANGELOG.md")
        main([f, "init"])
        assert main([f, "init"]) == EXIT_FAIL

    def test_workflow_scaffold(self, tmp_path):
        f = str(tmp_path / "CHANGELOG.md")
        assert main([f, "init", "--workflow"]) == EXIT_OK
        wf = tmp_path / ".github" / "workflows" / "changelog.yml"
        assert wf.is_file()
        content = wf.read_text(encoding="utf-8")
        assert "Londopy/patchnotes@v2" in content
        assert "CHANGELOG.md" in content

    def test_workflow_is_valid_yaml(self, tmp_path):
        import yaml
        f = str(tmp_path / "CHANGELOG.md")
        main([f, "init", "--workflow"])
        wf = tmp_path / ".github" / "workflows" / "changelog.yml"
        assert yaml.safe_load(wf.read_text(encoding="utf-8"))


# ── dep --requirements ────────────────────────────────────────────────────────

OLD_REQS = """\
# comment
requests==2.30.0
flask[async]==2.3.0
pyyaml>=6.0
click==8.1.0
gone==1.0.0
"""
NEW_REQS = """\
requests==2.32.0
flask[async]==2.3.0
pyyaml>=6.0
click==8.1.7
newpkg==0.1.0
"""


class TestRequirementsDiff:
    def test_parse_pins(self):
        pins = parse_requirements(OLD_REQS)
        assert pins == {"requests": "2.30.0", "flask": "2.3.0",
                        "click": "8.1.0", "gone": "1.0.0"}

    def test_diff(self):
        changed, added, removed = diff_requirements(OLD_REQS, NEW_REQS)
        assert changed == [("click", "8.1.0", "8.1.7"),
                           ("requests", "2.30.0", "2.32.0")]
        assert added == ["newpkg"]
        assert removed == ["gone"]

    def test_cli_requirements_mode(self, tmp_path, capsys, monkeypatch):
        from datetime import date

        import patchnotes._depdiff as dd
        from patchnotes import Changelog, ChangeType, Entry, Release

        fake = Changelog(releases=[
            Release("2.32.0", date(2024, 5, 20), False,
                    [Entry("Security fix", ChangeType.SECURITY)]),
            Release("2.31.0", date(2023, 5, 22), False,
                    [Entry("Minor fix", ChangeType.FIXED)]),
            Release("8.1.7", date(2023, 8, 17), False,
                    [Entry("Patch", ChangeType.FIXED)]),
        ])
        monkeypatch.setattr(dd, "find_github_repo", lambda pkg: ("o", "r"))
        monkeypatch.setattr(dd, "fetch_dep_changelog", lambda o, r: fake)

        old_f, new_f = tmp_path / "old.txt", tmp_path / "new.txt"
        old_f.write_text(OLD_REQS); new_f.write_text(NEW_REQS)

        rc = main(["dep", "--requirements", str(old_f), str(new_f)])
        out = capsys.readouterr().out
        assert rc == EXIT_OK
        assert "Security fix" in out
        assert "New dependencies: newpkg" in out
        assert "Removed dependencies: gone" in out

    def test_cli_requirements_strict_fails_on_flagged(self, tmp_path, monkeypatch):
        from datetime import date

        import patchnotes._depdiff as dd
        from patchnotes import Changelog, ChangeType, Entry, Release
        fake = Changelog(releases=[
            Release("2.32.0", date(2024, 5, 20), False,
                    [Entry("Breaking change", ChangeType.BREAKING)]),
        ])
        monkeypatch.setattr(dd, "find_github_repo", lambda pkg: ("o", "r"))
        monkeypatch.setattr(dd, "fetch_dep_changelog", lambda o, r: fake)
        old_f, new_f = tmp_path / "old.txt", tmp_path / "new.txt"
        old_f.write_text("requests==2.30.0\n"); new_f.write_text("requests==2.32.0\n")
        assert main(["--strict", "dep", "--requirements", str(old_f), str(new_f)]) == EXIT_FAIL

    def test_cli_requirements_wrong_params(self, tmp_path):
        f = tmp_path / "old.txt"; f.write_text("a==1\n")
        assert main(["dep", "--requirements", str(f)]) == EXIT_USAGE

    def test_resolution_failure_is_reported_not_fatal(self, tmp_path, capsys, monkeypatch):
        import patchnotes._depdiff as dd

        def boom(pkg): raise ValueError("no repo")
        monkeypatch.setattr(dd, "find_github_repo", boom)
        old_f, new_f = tmp_path / "old.txt", tmp_path / "new.txt"
        old_f.write_text("mystery==1.0\n"); new_f.write_text("mystery==2.0\n")
        assert main(["dep", "--requirements", str(old_f), str(new_f)]) == EXIT_OK
        assert "couldn't analyze" in capsys.readouterr().out


# ── mkdocs plugin ─────────────────────────────────────────────────────────────

mkdocs = pytest.importorskip("mkdocs", reason="mkdocs not installed")


class TestMkdocsPlugin:
    def _plugin(self, changelog_path):
        from patchnotes.mkdocs_plugin import PatchnotesPlugin
        plugin = PatchnotesPlugin()
        plugin.config = {"file": str(changelog_path)}
        return plugin

    def test_marker_replaced(self, tmp_path):
        cl = tmp_path / "CHANGELOG.md"
        cl.write_text("## [1.0.0] - 2024-01-01\n\n### Added\n- Shiny thing\n")
        plugin = self._plugin(cl)
        out = plugin.on_page_markdown("# Changelog\n\n<!-- patchnotes -->\n")
        assert "pn-changelog" in out
        assert "Shiny thing" in out
        assert "<style>" in out
        assert "<!-- patchnotes -->" not in out

    def test_no_marker_untouched(self, tmp_path):
        cl = tmp_path / "CHANGELOG.md"
        cl.write_text("## [1.0.0] - 2024-01-01\n\n### Added\n- x\n")
        plugin = self._plugin(cl)
        assert plugin.on_page_markdown("# Docs page\n") == "# Docs page\n"

    def test_missing_changelog_raises_helpfully(self, tmp_path):
        plugin = self._plugin(tmp_path / "nope.md")
        with pytest.raises(FileNotFoundError, match="file"):
            plugin.on_page_markdown("<!-- patchnotes -->")

    def test_registered_as_entry_point(self):
        # entry point declared in pyproject (verified after install in CI);
        # here just confirm the class importable at the declared path
        from patchnotes.mkdocs_plugin import PatchnotesPlugin  # ruff:ignore[unused-import]
