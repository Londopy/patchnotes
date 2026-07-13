# patchnotes

Parse, query, and validate changelogs in Python and CI.

## [2.1.0] - 2026-07-13

### Added

- Release automation: `Changelog.bump("2.1.0")` and `patchnotes CHANGELOG.md bump 2.1.0` move the [Unreleased] entries into a new dated release, keeping an empty [Unreleased] section and maintaining compare-link footnotes.
- `patchnotes CHANGELOG.md unreleased --fail-if-empty` exits 1 when there are no unreleased entries, so CI can require a changelog entry in every PR.
- Write support: `to_markdown()` (with optional compare-link generation via `repo_url=`) and `to_yaml()` enable round-tripping and format conversion.
- `patchnotes changelog.yml convert CHANGELOG.md` converts between markdown and YAML changelogs in either direction.
- `patchnotes CHANGELOG.md fix` rewrites an off-spec changelog in normalized form, applying every correction the lenient parser already recovers.
- Compare-link footnotes (`[1.2.0]: https://.../compare/v1.1.0...v1.2.0`) are now parsed into `Changelog.links` and validated: missing (PN206) and orphaned (PN207) links are reported as warnings.
- pre-commit hooks (`.pre-commit-hooks.yaml`): `patchnotes-validate`, `patchnotes-validate-strict`, and `patchnotes-fix`.
- `validate` and `fix` accept the file after the command (`patchnotes validate CHANGELOG.md`), matching how pre-commit passes filenames.

## [2.0.1] - 2026-07-13

### Changed

- PyYAML is now a required dependency, so YAML changelog support works out of the box with plain `pip install patchnotes`.
- CI publish workflow installs the package before running tests.

## [2.0.0] - 2026-07-13

### Breaking

- The internal `patchnotes._parser` module was split into `_models`, `_dispatch`, and the `patchnotes.formats` package. All public imports (`patchnotes.parse`, `patchnotes.Changelog`, ...) are unchanged, and `patchnotes._parser` remains as a compatibility shim.
- The parser is now lenient by default and recovers from off-standard input (loose dates, bracket-less headers, unknown section names) instead of silently misparsing it. Recovered constructs are reported via `Changelog.validate()`, so entry counts and dates may differ from 1.x on malformed files.

### Added

- Validation API: `Changelog.validate()`, `Changelog.is_valid()`, `patchnotes.validate()`, and `patchnotes.validate_file()` return structured `ValidationIssue` objects with stable codes, severities, and line numbers.
- Strict mode: `parse(text, strict=True)` and `parse_file(path, strict=True)` raise `ChangelogValidationError` on spec violations — built for CI/CD checks.
- Pluggable format registry: `patchnotes.formats.register_format()` lets third parties add new changelog formats; `format="auto"` detects by extension and content.
- YAML changelog format via the optional extra `pip install patchnotes[yaml]`.
- CLI `validate` subcommand with meaningful exit codes (0 valid, 1 invalid, 2 usage error) and a `--strict` flag that treats warnings as failures.
- CLI `--format json` on every subcommand for shell scripting, `-` to read from stdin, and `--quiet` for exit-code-only usage.
- GitHub Actions workflow annotations (`::error`/`::warning` with file and line) — automatic when running inside Actions, or forced with `--github`.
- Composite GitHub Action (`action.yml`) so workflows can write `uses: Londopy/patchnotes@v2`.
- Common off-spec section aliases ("Bug Fixes", "Features", "Improvements", ...) are mapped to their Keep a Changelog equivalents with a warning.

## [1.1.0] - 2026-05-02

### Added

- `Changelog.from_github()` with automatic `master` branch fallback.
- `to_rss()` renderer.

## [1.0.0] - 2026-03-20

### Added

- Initial release: Keep a Changelog parser, `to_html()`/`to_text()` renderers, and the `patchnotes` CLI.
