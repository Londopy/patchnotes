# patchnotes

[![PyPI](https://img.shields.io/pypi/v/patchnotes)](https://pypi.org/project/patchnotes/)
[![Python versions](https://img.shields.io/pypi/pyversions/patchnotes)](https://pypi.org/project/patchnotes/)
[![Publish to PyPI](https://github.com/Londopy/patchnotes/actions/workflows/publish.yml/badge.svg)](https://github.com/Londopy/patchnotes/actions/workflows/publish.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Keep a Changelog](https://img.shields.io/badge/changelog-keep--a--changelog-orange)](https://keepachangelog.com)

Parse [Keep a Changelog](https://keepachangelog.com) formatted `CHANGELOG.md` files — and YAML changelogs — into structured Python objects. Query, diff, validate, and render to HTML, RSS, or plain text. Built for use in Python code, shell scripts, and CI/CD.

**Pure Python. Fully typed. YAML support included.**

```python
import patchnotes

cl = patchnotes.parse_file("CHANGELOG.md")

cl.latest()        # Release(v2.1.0, 2024-11-15, 6 entries)
cl.unreleased()    # Release(vUnreleased, unreleased, 2 entries)
cl.validate()      # [] — or a list of issues with line numbers

# What broke between 1.4.0 and 2.1.0?
for r in cl.diff("1.4.0", "2.1.0"):
    for entry in r.breaking_changes:
        print(f"v{r.version}: {entry.text}")
```

## Install

```bash
pip install patchnotes
```

Requires Python 3.10+.

---

## Usage

### Parse

```python
import patchnotes

# From a file (format auto-detected from extension/content)
cl = patchnotes.parse_file("CHANGELOG.md")
cl = patchnotes.parse_file("changelog.yml")     # YAML works out of the box

# From a string
cl = patchnotes.parse(raw_text)
cl = patchnotes.parse(raw_yaml, format="yaml")

# From any URL
cl = patchnotes.Changelog.from_url(
    "https://raw.githubusercontent.com/user/repo/main/CHANGELOG.md"
)

# From a GitHub repo — just owner + repo name, no URL needed
cl = patchnotes.Changelog.from_github("Londopy", "patchnotes")

# Different branch or filename
cl = patchnotes.Changelog.from_github(
    "psf", "requests",
    branch="main",
    filename="HISTORY.md"   # also works with CHANGES.md, NEWS.md, etc.
)
```

`from_github` automatically falls back to the `master` branch if `main` returns a 404.

---

### Validation and strict mode

The parser is **lenient by default**: off-standard input (a `2024/01/01` date, a `## 1.2.0` header without brackets, a `### Improvements` section) is recovered with the most sensible interpretation and recorded as an issue instead of crashing or silently misparsing.

```python
cl = patchnotes.parse_file("CHANGELOG.md")

for issue in cl.validate():
    print(issue)
    # [ERROR] PN101 line 12: date '2024/01/01' is not ISO 8601 ...
    # [WARNING] PN201 line 30: non-standard section 'Improvements' ...

cl.is_valid()              # True if no ERROR-severity issues
cl.is_valid(strict=True)   # True only if there are zero issues
```

**Strict mode** raises instead — useful when a malformed changelog should stop the pipeline:

```python
from patchnotes import ChangelogValidationError

try:
    cl = patchnotes.parse_file("CHANGELOG.md", strict=True)
except ChangelogValidationError as e:
    for issue in e.issues:
        print(issue)
    raise
```

Issue codes are stable (grep-able in CI logs): `PN1xx` are errors (data was lost or guessed — bad dates, duplicate versions, malformed headers), `PN2xx` are warnings (recoverable style problems — unknown section names, out-of-order or empty releases), `PN3xx` are YAML schema problems.

---

### Formats

Formats are pluggable. `markdown` (Keep a Changelog) and `yaml` are built in; `format="auto"` picks by file extension, then content.

YAML changelog schema:

```yaml
title: My Project
description: What the project does.
releases:
  - version: "2.0.0"
    date: 2024-06-01
    changes:
      breaking:
        - Renamed foo() to bar()
      added:
        - New thing
  - unreleased: true
    changes:
      fixed:
        - Pending fix
```

Adding your own format (no core changes needed):

```python
from patchnotes import Changelog, FormatParser, register_format

class MyFormat(FormatParser):
    name = "myformat"
    extensions = (".mycl",)

    def parse(self, text: str) -> Changelog:
        ...  # lenient: record problems on changelog.issues, never raise

register_format(MyFormat())
cl = patchnotes.parse(text, format="myformat")
```

---

### Access releases

```python
cl.latest()               # highest versioned release
cl.unreleased()           # [Unreleased] block, or None
cl.get_version("2.0.0")   # specific version, or None
cl.releases               # all Release objects, in file order
```

### Query entries

```python
r = cl.get_version("2.0.0")

r.entries          # all Entry objects
r.by_type          # dict: {"Breaking": [...], "Added": [...], ...}
r.breaking_changes # shortcut: Breaking + Removed entries
r.yanked           # bool
r.release_date     # datetime.date or None
```

### Diff and history

```python
# All releases strictly between 1.4.0 (exclusive) and 2.1.0 (inclusive)
releases = cl.diff("1.4.0", "2.1.0")

# All releases newer than a version (includes Unreleased)
releases = cl.since_version("1.4.0")

# Every breaking change across the entire changelog
for version, entry in cl.all_breaking_changes():
    print(f"v{version}: {entry.text}")
```

### Serialize to JSON

```python
cl.to_dict()        # plain Python dict, JSON-safe
cl.to_json()        # JSON string (indent=2 by default)
cl.to_json(indent=4)
```

### Write it back out

Parsing is only half the trip — `to_markdown()` and `to_yaml()` render a
Changelog back to text, so you can modify programmatically and save:

```python
cl = patchnotes.parse_file("CHANGELOG.md")

md = patchnotes.to_markdown(cl)

# Generate the spec's compare-link footnotes while you're at it:
# [2.1.0]: https://github.com/you/project/compare/v2.0.1...v2.1.0
md = patchnotes.to_markdown(cl, repo_url="https://github.com/you/project")

yml = patchnotes.to_yaml(cl)      # round-trips through the YAML format
```

### Release automation

`bump()` moves the `[Unreleased]` entries into a new dated release — the
manual step everyone forgets on release day:

```python
cl = patchnotes.parse_file("CHANGELOG.md")
cl.bump("2.1.0")                       # date defaults to today
with open("CHANGELOG.md", "w") as f:
    f.write(patchnotes.to_markdown(cl))
```

It keeps an empty `[Unreleased]` section on top, refuses to release an
empty section or a duplicate version, and updates compare-link footnotes
if the changelog uses them.

---

## Rendering

### HTML

```python
# Full standalone HTML page
html = patchnotes.to_html(cl)
with open("changelog.html", "w") as f:
    f.write(html)

# Bare <div> fragment for embedding in your own page
fragment = patchnotes.to_html(cl, full_page=False)
```

### RSS

```python
rss = patchnotes.to_rss(cl, project_url="https://github.com/you/project")
with open("changelog.rss", "w") as f:
    f.write(rss)
```

Each versioned release becomes an `<item>`. Unreleased entries are skipped.

### Plain text

```python
# Full summary
print(patchnotes.to_text(cl))

# Only the 3 most recent releases
print(patchnotes.to_text(cl, max_releases=3))
```

---

## CLI

```bash
# Summary of all releases
patchnotes CHANGELOG.md

# Latest release
patchnotes CHANGELOG.md latest

# Unreleased changes
patchnotes CHANGELOG.md unreleased

# Specific version
patchnotes CHANGELOG.md show 2.0.0

# Diff between versions
patchnotes CHANGELOG.md diff 1.4.0 2.1.0

# All breaking changes
patchnotes CHANGELOG.md breaking

# Dump as JSON
patchnotes CHANGELOG.md json

# Release day: move [Unreleased] into a new dated release
patchnotes CHANGELOG.md bump 2.1.0

# Convert between formats (either direction)
patchnotes changelog.yml convert CHANGELOG.md
patchnotes CHANGELOG.md convert changelog.yml

# Rewrite an off-spec changelog in normalized form
patchnotes CHANGELOG.md fix
```

### Shell scripting

Every command accepts `--format json` for machine-readable output, and `-` reads from stdin:

```bash
# Latest version number, nothing else
patchnotes CHANGELOG.md --format json latest | jq -r .version

# Pipe from anywhere
curl -s https://raw.githubusercontent.com/user/repo/main/CHANGELOG.md \
  | patchnotes - latest

# Exit-code-only check in a script
if ! patchnotes CHANGELOG.md --quiet validate; then
    echo "changelog is broken" >&2
    exit 1
fi
```

Exit codes: `0` success/valid · `1` validation failed, version not found, or parse error · `2` usage error (bad arguments, missing file).

### Validation in CI

```bash
patchnotes CHANGELOG.md validate            # fail on errors only
patchnotes CHANGELOG.md validate --strict   # fail on warnings too

# Require a changelog entry in every PR
patchnotes CHANGELOG.md unreleased --fail-if-empty
```

Inside GitHub Actions, `validate` automatically emits `::error`/`::warning` annotations with file and line, so problems show up inline on the PR diff. (Force this locally with `--github`.)

### Example: catching a broken changelog in a PR

Say a teammate opens a PR with this edit to `CHANGELOG.md`:

```markdown
## [2.1.0] - 2026/08/02

### Improvments
- Faster parsing
```

Two problems: the date isn't ISO 8601, and `Improvments` isn't a Keep a Changelog section (it's also misspelled). Locally, `validate` reports both with line numbers:

```console
$ patchnotes CHANGELOG.md validate --strict
  [ERROR] PN101 line 3: date '2026/08/02' is not ISO 8601 (expected YYYY-MM-DD); interpreted as 2026-08-02
  [WARNING] PN201 line 5: unknown change type 'Improvments'; entries filed under 'Changed'
CHANGELOG.md: FAIL (strict) — 1 error(s), 1 warning(s)
$ echo $?
1
```

In a GitHub Actions run, the same command emits workflow annotations instead:

```
::error file=CHANGELOG.md,line=3,title=patchnotes PN101::date '2026/08/02' is not ISO 8601 (expected YYYY-MM-DD); interpreted as 2026-08-02
::warning file=CHANGELOG.md,line=5,title=patchnotes PN201::unknown change type 'Improvments'; entries filed under 'Changed'
```

GitHub renders these as error/warning boxes pinned to lines 3 and 5 in the PR's "Files changed" tab, the check fails, and (with branch protection) the PR can't merge until the changelog is fixed. Note that lenient parsing still recovered both problems — `parse()` would happily return the release with the date read as 2026-08-02 — strict mode is what turns recovery into rejection.

---

## GitHub Actions

Use the bundled composite action:

```yaml
# .github/workflows/validate-changelog.yml
name: Validate changelog
on:
  pull_request:
    paths: ["CHANGELOG.md"]

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: Londopy/patchnotes@v2
        with:
          file: CHANGELOG.md
          strict: "true"
```

Or plain shell (works on any CI):

```yaml
      - run: |
          pip install patchnotes
          patchnotes CHANGELOG.md validate --strict
```

The action also exposes the latest version as an output:

```yaml
      - uses: Londopy/patchnotes@v2
        id: changelog
      - run: echo "Latest release is ${{ steps.changelog.outputs.latest-version }}"
```

See [`examples/workflows/`](examples/workflows/) for complete workflows, including publishing GitHub Releases from changelog notes.

---

## pre-commit

Validate (or auto-fix) the changelog on every commit:

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/Londopy/patchnotes
    rev: v2.1.0
    hooks:
      - id: patchnotes-validate        # or patchnotes-validate-strict / patchnotes-fix
```

---

## Data model

```
Changelog
├── title: str
├── description: str
├── releases: list[Release]
│   ├── version: str
│   ├── release_date: date | None
│   ├── is_unreleased: bool
│   ├── yanked: bool
│   ├── entries: list[Entry]
│   │   ├── text: str
│   │   └── change_type: ChangeType
│   ├── by_type → dict[str, list[Entry]]
│   └── breaking_changes → list[Entry]
├── latest() → Release | None
├── unreleased() → Release | None
├── get_version(v) → Release | None
├── since_version(v) → list[Release]
├── diff(from, to) → list[Release]
├── all_breaking_changes() → list[tuple[str, Entry]]
├── validate() → list[ValidationIssue]
├── is_valid(strict=False) → bool
├── to_dict() → dict
├── to_json() → str
├── from_url(url) → Changelog
└── from_github(owner, repo, branch, filename) → Changelog

ValidationIssue
├── code: str          # stable, e.g. "PN101"
├── message: str
├── severity: "error" | "warning"
└── line: int | None
```

`ChangeType` values: `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, `Security`, `Breaking`

---

## Changelog format

`patchnotes` parses the [Keep a Changelog](https://keepachangelog.com) spec:

```markdown
# Project Name

## [Unreleased]

### Added
- New feature

## [1.2.0] - 2024-11-15

### Breaking
- Renamed `foo()` to `bar()`

### Fixed
- Some bug

## [1.1.0] - 2024-09-01 [YANKED]

### Security
- Patched CVE-2024-1234
```

---

## License

MIT
