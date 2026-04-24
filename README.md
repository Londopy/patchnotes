# patchnotes

Parse [Keep a Changelog](https://keepachangelog.com) formatted `CHANGELOG.md` files into structured Python objects. Render to HTML, RSS, or plain text. Fetch directly from GitHub.

**Zero dependencies. Pure Python. Typed.**

```python
import patchnotes

cl = patchnotes.parse_file("CHANGELOG.md")

cl.latest()        # Release(v2.1.0, 2024-11-15, 6 entries)
cl.unreleased()    # Release(vUnreleased, unreleased, 2 entries)

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

# From a file
cl = patchnotes.parse_file("CHANGELOG.md")

# From a string
cl = patchnotes.parse(raw_text)

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
├── to_dict() → dict
├── to_json() → str
├── from_url(url) → Changelog
└── from_github(owner, repo, branch, filename) → Changelog
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
