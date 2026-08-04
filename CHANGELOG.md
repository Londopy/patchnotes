# patchnotes

Parse, query, and validate changelogs in Python and CI.

## [Unreleased]

## [2.6.0] - 2026-08-04

### Added

- reStructuredText changelog parser (`patchnotes.parse(text, format="rst")`, or automatic for `.rst` files). Learns the document's own heading hierarchy from section adornments, skips directives and comments, and reduces inline rST markup to plain text. Issue codes match the markdown parser's, so quality is comparable across formats.
- `research/`: an ecosystem scan over the 500 most-downloaded PyPI packages, measuring how many keep a changelog a machine can read. Results and method in `research/FINDINGS.md`.

### Changed

- `.rst` files now parse with the reStructuredText parser. Previously the extension matched no format and fell through to the markdown parser, which recovered setext-underlined headers but little else — so `parse_file("CHANGES.rst")` may now return more releases, different entries, and different issue codes than it did in 2.5.x. Setext-underlined *markdown* is unaffected: the two shapes are ambiguous, so rST is auto-detected only on content markdown cannot produce.
- CI now dogfoods the badge: `ci.yml` publishes patchnotes' own changelog badge to the `gh-pages` branch on every push to main, and skips publishing on pull requests so fork PRs don't need a write token.
- The sdist no longer ships `research/`, `examples/`, or `.github/`. The wheel was already scoped to the package; the sdist was picking up everything untracked by `.gitignore`, including ~220 KB of ecosystem-scan data.

### Fixed

- `__version__` now matches the released version. It was left at `2.5.0` when 2.5.1 shipped, so `patchnotes --version` and `patchnotes.__version__` under-reported by a patch release. The `check-version` command compares the changelog against `pyproject.toml`, which was correct, so nothing caught it — `patchnotes/__init__.py` is now part of the release checklist.

## [2.5.1] - 2026-08-04

### Fixed

- Version ordering now follows the precedence rules in the Semantic Versioning specification (section 11). Pre-release suffixes were previously discarded, so `1.0.0-rc.1` and `1.0.0` compared equal and `latest()` could return the release candidate instead of the final release. Pre-release identifiers now compare field by field, numeric identifiers order below alphanumeric ones, and build metadata is ignored for precedence.
- Corrected the release dates recorded for 1.0.0 and 1.1.0, which predated the repository's own first commit. Both were published on 2026-04-23.

### Changed

- The source now passes `mypy --strict`, which `pyproject.toml` had declared but the code did not satisfy. The check is clean whether or not the optional `mkdocs` extra is installed. Annotation-only change; no runtime behaviour differs.
- Corrected the "zero dependencies" claim in the README: PyYAML has been a required dependency since 2.0.1.

### Added

- Citation metadata (`CITATION.cff`, `.zenodo.json`) and a contributor guide (`CONTRIBUTING.md`), so releases are archived to Zenodo with a citable DOI.

## [2.5.0] - 2026-08-02

### Added

- The `badge` command now reports validation state as well as version: green for a clean parse, yellow with a warning count, red for errors, grey when nothing is released yet. `--label` sets the left-hand text and `--no-version` reports state alone.
- GitHub Action can publish the badge JSON itself — `badge: gist` (any repo, needs `badge-gist-id` and a `badge-token`) or `badge: gh-pages` (commits to a branch using the built-in token). New `badge-json` output exposes the generated JSON.

### Changed

- `badge` is now exempt from the global `--strict` guard and always exits `0`, so a broken changelog produces a red badge instead of aborting the step. Under `--strict` it treats warnings as invalid.

## [2.4.0] - 2026-07-19

### Added

- `patchnotes init` scaffolds a spec-compliant starter CHANGELOG.md (strict-validation clean out of the box); `--workflow` also writes a ready-made `.github/workflows/changelog.yml` PR check.
- `dep --requirements old.txt new.txt` diffs two requirements files and runs the breaking/security analysis for every changed pin at once — built for reviewing lockfile bump PRs. With `--strict`, flagged changes fail CI.
- mkdocs plugin: add `patchnotes` to `plugins:` in mkdocs.yml and a `<!-- patchnotes -->` marker in any docs page renders the styled changelog at build time (`pip install patchnotes[mkdocs]`).

### Fixed

- An empty [Unreleased] section no longer triggers a PN203 warning — it's the normal state right after a release (and what `bump` leaves behind). Empty *versioned* releases still warn.

## [2.3.0] - 2026-07-19

### Added

- CI workflow (`.github/workflows/ci.yml`) that dogfoods patchnotes: the repo's own changelog is strict-validated by the bundled action (`uses: ./` installed from source), version-synced against `pyproject.toml`, and uploaded as SARIF to GitHub code scanning on every push.

### Changed

- The publish workflow now uses the bundled action for validation, tag/changelog version sync, and GitHub Release creation with changelog notes — every release exercises the full feature set.

## [2.2.0] - 2026-07-19

### Added

- `check-version` command: fails CI when the latest changelog version doesn't match `pyproject.toml`, `package.json`, `Cargo.toml`, or a literal version/tag (`--against "$GITHUB_REF_NAME"`). Auto-discovers the metadata file next to the changelog.
- Changelog fragments: `patchnotes fragment add fixed "..."` writes a snippet to `changelog.d/`, ending [Unreleased] merge conflicts. `fragment list` shows pending entries; `bump --collect` folds them into the release and deletes the files; `unreleased --fail-if-empty --collect` counts fragments as unreleased changes.
- `dep` command: `patchnotes dep requests 2.30.0 2.32.0` resolves a PyPI package to its GitHub repo, fetches its changelog, and flags every breaking/removed/security/deprecated change between two versions — built for reviewing Dependabot bumps.
- SARIF output: `validate --format sarif` emits SARIF 2.1.0 for GitHub code scanning upload.
- `badge` command prints a shields.io endpoint JSON for a "latest changelog version" badge.
- GitHub Action: new `check-version` input runs the version sync check, and `release: "true"` creates a GitHub Release with the latest changelog section as notes.

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

## [1.1.0] - 2026-04-23

### Added

- `Changelog.from_github()` with automatic `master` branch fallback.
- `to_rss()` renderer.

## [1.0.0] - 2026-04-23

### Added

- Initial release: Keep a Changelog parser, `to_html()`/`to_text()` renderers, and the `patchnotes` CLI.
