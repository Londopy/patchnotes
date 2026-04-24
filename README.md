# patchnotes

Parse [Keep a Changelog](https://keepachangelog.com) formatted `CHANGELOG.md` files into structured Python objects.

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

## Usage

### Parse

```python
import patchnotes

# From a file
cl = patchnotes.parse_file("CHANGELOG.md")

# From a string
cl = patchnotes.parse(raw_text)

# From a URL (e.g. raw GitHub)
cl = patchnotes.Changelog.from_url(
    "https://raw.githubusercontent.com/user/repo/main/CHANGELOG.md"
)
```

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

### Serialize

```python
cl.to_dict()     # plain Python dict, JSON-safe
cl.to_json()     # JSON string (indent=2 by default)
cl.to_json(indent=4)
```

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
└── from_url(url) → Changelog
```

`ChangeType` values: `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, `Security`, `Breaking`

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

## License

MIT
