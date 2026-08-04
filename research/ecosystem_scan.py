"""
Ecosystem scan: how many widely-used Python packages keep a changelog that a
machine can actually read?

For each package on the PyPI top-downloads list this resolves the source
repository, looks for a changelog at conventional locations, parses it with
patchnotes, and records what the validator had to recover.

Design notes, in the order they matter for the validity of the result:

1. REPO RESOLUTION IS THE WEAKEST LINK. A naive `github.com/(owner)/(repo)`
   regex over every PyPI project URL silently matches funding links
   (`github.com/sponsors/hynek` -> owner "sponsors") and umbrella monorepos
   (`google-auth` -> `googleapis/google-cloud-python`). Both produce wrong
   rows that look plausible: the first as a false "no changelog", the second
   as a real changelog belonging to a different project. So resolution is
   priority-ordered by project_urls *key*, filtered against a blocklist of
   non-repository GitHub paths, and every row carries a confidence level so
   low-confidence rows can be excluded from headline numbers.

2. ABSENCE IS NOT ONE THING. "No changelog" conflates "none exists", "it's in
   docs/", "it's reStructuredText", and "it's only GitHub Releases". rST files
   are detected and reported as their own category rather than counted as
   misses, because patchnotes has no rST parser and folding them into "no
   changelog" would overstate the finding.

3. PACKAGES ARE NOT PROJECTS. Six opentelemetry distributions share one
   changelog. Package-level rates double-count them; repo-level rates don't.
   Both are reported.

Every network response is cached to disk so the analysis can be re-run, and
so the corpus can be archived alongside the results as a citable dataset.

Usage:
    python research/ecosystem_scan.py --limit 500
    python research/ecosystem_scan.py --limit 500 --no-network   # cache only
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import patchnotes
from patchnotes._validation import Severity

HERE = Path(__file__).resolve().parent
#: Response cache. Override with PATCHNOTES_SCAN_CACHE when the repo lives on
#: a slow or network-mounted filesystem — the scan writes tens of thousands of
#: small files and disk latency, not bandwidth, is the bottleneck.
CACHE = Path(os.environ.get("PATCHNOTES_SCAN_CACHE") or (HERE / "cache"))
UA = {"User-Agent": "patchnotes-ecosystem-scan/2.0 (research; +https://github.com/Londopy/patchnotes)"}

CORPUS_URL = "https://hugovk.github.io/top-pypi-packages/top-pypi-packages.min.json"

#: Markdown changelogs patchnotes can parse.
MARKDOWN_NAMES = ("CHANGELOG.md", "CHANGES.md", "HISTORY.md", "NEWS.md")
#: Changelogs that exist but that patchnotes has no parser for. Detected so
#: they form their own reported category instead of inflating "not found".
RST_NAMES = ("CHANGELOG.rst", "CHANGES.rst", "HISTORY.rst", "NEWS.rst")
#: Directories projects commonly hide a changelog in. Kept deliberately
#: narrow: over the first 166 packages, `doc/` and `CHANGELOG.markdown`
#: produced zero hits, and every extra location multiplies the request
#: cost of the ~35% of packages that have no changelog at all.
SUBDIRS = ("", "docs/")

BRANCHES = ("main", "master")

#: GitHub paths that are not repositories. `sponsors` is the one that silently
#: poisoned the pilot scan; the rest are here so the same class of bug can't
#: recur as the corpus grows.
NOT_OWNERS = frozenset({
    "sponsors", "orgs", "users", "apps", "marketplace", "features", "about",
    "pricing", "security", "topics", "collections", "readme", "login",
    "settings", "notifications", "explore", "trending", "events", "enterprise",
    "site", "contact", "join", "search", "new", "organizations", "account",
})
#: Second path segments that mean we matched a URL *inside* a repo, not the repo.
NOT_REPOS = frozenset({"issues", "pulls", "blob", "tree", "releases", "wiki",
                       "actions", "discussions", "commits", "compare", "raw"})

#: project_urls keys, most trustworthy first. A key explicitly naming the
#: source is worth far more than a homepage, which is often a docs site, or a
#: funding link, which is never the repo.
URL_KEY_PRIORITY = (
    ("source", 3), ("repository", 3), ("repo", 3), ("code", 3),
    ("github", 3), ("source code", 3), ("issues", 2), ("tracker", 2),
    ("bug", 2), ("changelog", 2), ("release notes", 2), ("homepage", 1),
    ("home", 1), ("documentation", 1), ("docs", 1),
)
#: Never resolve from these — funding links are the sponsors/ trap.
URL_KEY_DENY = ("funding", "sponsor", "donate", "twitter", "mastodon", "chat",
                "discord", "slack", "gitter", "forum", "mailing")

#: Captures the optional `/tree/<branch>/<subdir>` tail as well as owner/repo.
#: Monorepos (google-auth lives at google-cloud-python/tree/main/packages/
#: google-auth) declare the subdirectory in their PyPI URL, and the package's
#: real changelog sits inside it. Throwing the path away is what made the
#: pilot attribute the umbrella repo's changelog to four google packages.
GITHUB_URL = re.compile(
    r"https?://(?:www\.)?github\.com/(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+)"
    r"(?:/tree/[^/]+/(?P<subdir>[\w./-]+?))?/?(?:[#?]|$)",
    re.IGNORECASE,
)


# ── plumbing ──────────────────────────────────────────────────────────────────

def _cache_path(kind: str, key: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", key)[:180]
    return CACHE / kind / safe


def fetch(url: str, kind: str, key: str, network: bool = True) -> Optional[str]:
    """Fetch a URL, caching the body (and 404s) on disk.

    Misses are cached too — an empty marker file — so that a re-run doesn't
    re-request the ~80% of (repo, filename) pairs that don't exist.
    """
    path = _cache_path(kind, key)
    miss = path.with_suffix(path.suffix + ".miss")
    if path.exists():
        return path.read_text(encoding="utf-8", errors="replace")
    if miss.exists():
        return None
    if not network:
        return None

    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=25) as r:
            body = r.read().decode("utf-8", errors="replace")
        path.write_text(body, encoding="utf-8")
        return body
    except urllib.error.HTTPError as e:
        if e.code in (404, 451):
            miss.write_text("")
        return None
    except Exception:
        return None


# ── resolution ────────────────────────────────────────────────────────────────

def _normalize(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _key_weight(key: str) -> int:
    k = key.lower().strip()
    if any(d in k for d in URL_KEY_DENY):
        return -1
    for frag, weight in URL_KEY_PRIORITY:
        if frag in k:
            return weight
    return 1


def resolve_repo(package: str, meta: dict) -> dict:
    """Resolve a package to a GitHub repo, with a confidence level.

    Returns owner/repo plus:
      confidence  "high"   repo name matches the package name
                  "medium" came from a key that explicitly names the source
                  "low"    fell out of a homepage or docs link
      candidates  every distinct repo seen, so ambiguity is auditable
    """
    info = meta.get("info") or {}
    project_urls = info.get("project_urls") or {}

    scored: list[tuple[int, str, str, str, str]] = []

    def add(weight: int, key: str, url: Any) -> None:
        if not isinstance(url, str):
            return
        m = GITHUB_URL.search(url)
        if m:
            scored.append((weight, key, m.group("owner"),
                           m.group("repo").removesuffix(".git"),
                           m.group("subdir") or ""))

    for key, url in project_urls.items():
        w = _key_weight(key)
        if w >= 0:
            add(w, key, url)
    for field in ("home_page", "download_url"):
        add(1, field, info.get(field))

    valid = [
        t for t in scored
        if t[2].lower() not in NOT_OWNERS and t[3].lower() not in NOT_REPOS
    ]
    candidates = sorted({f"{o}/{r}" + (f"/{s}" if s else "") for _, _, o, r, s in valid})
    rejected = sorted({f"{o}/{r}" for _, _, o, r, _ in scored if o.lower() in NOT_OWNERS})

    if not valid:
        return {"owner": None, "repo": None, "subdir": "", "confidence": None,
                "candidates": [], "rejected_paths": rejected,
                "status": "no-github-repo"}

    pkg = _normalize(package)

    def matches(repo: str, subdir: str) -> bool:
        """Does this candidate actually correspond to the package?

        Either the repo is named after the package, or — for a monorepo — the
        declared subdirectory is. The subdir test is what makes google-auth
        resolve to packages/google-auth rather than the umbrella repo.
        """
        leaf = _normalize(subdir.rsplit("/", 1)[-1]) if subdir else ""
        return (
            _normalize(repo) == pkg or leaf == pkg
            or pkg in _normalize(repo) or _normalize(repo) in pkg
            or (bool(leaf) and (pkg in leaf or leaf in pkg))
        )

    named = [t for t in valid if matches(t[3], t[4])]
    if named:
        w, key, owner, repo, subdir = max(named, key=lambda t: t[0])
        confidence = "high"
    else:
        w, key, owner, repo, subdir = max(valid, key=lambda t: t[0])
        confidence = "medium" if w >= 3 else "low"

    return {"owner": owner, "repo": repo, "subdir": subdir,
            "confidence": confidence, "source_key": key,
            "candidates": candidates, "rejected_paths": rejected,
            "status": "ok"}


# ── scanning ──────────────────────────────────────────────────────────────────

def default_branch(owner: str, repo: str, network: bool = True) -> Optional[str]:
    """Which of main/master exists, probed once and cached.

    Without this, every miss costs ~90 requests (2 branches x 5 dirs x 9
    filenames). Probing a file that essentially every repo has collapses the
    search to a single branch.
    """
    for probe in ("README.md", "README.rst", "setup.py", "pyproject.toml", ".gitignore"):
        for branch in BRANCHES:
            url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{probe}"
            if fetch(url, "probe", f"{owner}__{repo}__{branch}__{probe}", network) is not None:
                return branch
    return None


def find_changelog(owner: str, repo: str, subdir: str = "",
                   network: bool = True) -> dict:
    """Look for a changelog, distinguishing markdown from rST from absent.

    A monorepo subdirectory is searched first: the package's own changelog
    beats the umbrella repo's, and preferring the latter silently attributes
    one project's release history to another.
    """
    subdirs = SUBDIRS
    if subdir:
        pre = subdir.rstrip("/") + "/"
        subdirs = (pre, pre + "docs/") + SUBDIRS
    branch = default_branch(owner, repo, network)
    if branch is None:
        return {"path": None, "branch": None, "text": None, "kind": None,
                "repo_reachable": False}
    for _b in (branch,):
        for sub in subdirs:
            for name in MARKDOWN_NAMES:
                p = f"{sub}{name}"
                url = f"https://raw.githubusercontent.com/{owner}/{repo}/{_b}/{p}"
                body = fetch(url, "changelog", f"{owner}__{repo}__{_b}__{p}", network)
                if body and body.strip():
                    return {"path": p, "branch": _b, "text": body, "kind": "markdown", "repo_reachable": True}
    for _b in (branch,):
        for sub in subdirs:
            for name in RST_NAMES:
                p = f"{sub}{name}"
                url = f"https://raw.githubusercontent.com/{owner}/{repo}/{_b}/{p}"
                body = fetch(url, "changelog", f"{owner}__{repo}__{_b}__{p}", network)
                if body and body.strip():
                    return {"path": p, "branch": _b, "text": body, "kind": "rst", "repo_reachable": True}
    return {"path": None, "branch": None, "text": None, "kind": None, "repo_reachable": True}


def scan_one(package: str, rank: int, network: bool = True) -> dict:
    row: dict[str, Any] = {
        "package": package, "rank": rank, "repo": None, "confidence": None,
        "resolution_candidates": [], "rejected_paths": [],
        "subdir": "", "changelog": None, "changelog_kind": None, "branch": None,
        "parsed": None, "releases": 0, "errors": 0, "warnings": 0,
        "codes": [], "strict_clean": None, "status": None,
    }

    raw = fetch(f"https://pypi.org/pypi/{package}/json", "pypi", package, network)
    if raw is None:
        row["status"] = "pypi-unavailable"
        return row
    try:
        meta = json.loads(raw)
    except json.JSONDecodeError:
        row["status"] = "pypi-unparseable"
        return row

    res = resolve_repo(package, meta)
    row["resolution_candidates"] = res["candidates"]
    row["rejected_paths"] = res["rejected_paths"]
    if res["status"] != "ok":
        row["status"] = "no-github-repo"
        return row

    owner, repo = res["owner"], res["repo"]
    row["repo"] = f"{owner}/{repo}"
    row["subdir"] = res.get("subdir", "")
    row["confidence"] = res["confidence"]

    found = find_changelog(owner, repo, row["subdir"], network)
    if not found["path"]:
        row["status"] = ("repo-unreachable" if not found.get("repo_reachable")
                         else "no-changelog-found")
        return row

    row["changelog"] = found["path"]
    row["changelog_kind"] = found["kind"]
    row["branch"] = found["branch"]

    try:
        cl = patchnotes.parse(found["text"], filename=found["path"])
    except Exception as e:
        row["status"] = f"parse-exception:{type(e).__name__}"
        return row

    issues = cl.validate()
    row["releases"] = len(cl.releases)
    row["errors"] = sum(1 for i in issues if i.severity is Severity.ERROR)
    row["warnings"] = sum(1 for i in issues if i.severity is Severity.WARNING)
    row["codes"] = sorted({i.code for i in issues})
    row["parsed"] = row["releases"] > 0
    row["strict_clean"] = not issues
    row["status"] = "ok"
    return row


# ── corpus + driver ───────────────────────────────────────────────────────────

def load_corpus(limit: int, network: bool = True) -> list[str]:
    raw = fetch(CORPUS_URL, "corpus", "top-pypi-packages", network)
    if raw is None:
        raise SystemExit("could not load the corpus (and it is not cached)")
    data = json.loads(raw)
    rows = data.get("rows") or data.get("data") or []
    names = []
    for r in rows:
        n = r.get("project") or r.get("package") or r.get("name")
        if n:
            names.append(n)
    return names[:limit]


def run(limit: int, workers: int, network: bool,
        partial: Optional[Path] = None, budget: Optional[float] = None) -> list[dict]:
    """Scan the corpus, appending each row to a JSONL file as it completes.

    Resumable by design: packages already present in the partial file are
    skipped, and a wall-clock budget lets the scan run in slices without
    losing work. Combined with the on-disk response cache, a re-run costs
    almost nothing for everything already seen.
    """
    names = load_corpus(limit, network)
    ranks = {n: i for i, n in enumerate(names, 1)}

    done_rows: dict[str, dict] = {}
    if partial and partial.exists():
        for line in partial.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    r = json.loads(line)
                    done_rows[r["package"]] = r
                except json.JSONDecodeError:
                    continue

    todo = [n for n in names if n not in done_rows]
    print(f"  {len(done_rows)} cached, {len(todo)} to scan",
          file=sys.stderr, flush=True)

    t0 = time.time()
    fh = partial.open("a", encoding="utf-8") if partial else None
    completed = 0
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(scan_one, n, ranks[n], network): n for n in todo}
            for fut in concurrent.futures.as_completed(futures):
                row = fut.result()
                done_rows[row["package"]] = row
                completed += 1
                if fh:
                    fh.write(json.dumps(row) + "\n")
                    fh.flush()
                if completed % 20 == 0:
                    print(f"  +{completed}/{len(todo)}  ({time.time() - t0:.0f}s)",
                          file=sys.stderr, flush=True)
                if budget and time.time() - t0 > budget:
                    print("  budget reached, stopping early (re-run to resume)",
                          file=sys.stderr, flush=True)
                    for f in futures:
                        f.cancel()
                    break
    finally:
        if fh:
            fh.close()

    results = [r for r in done_rows.values() if r["package"] in ranks]
    results.sort(key=lambda r: r["rank"])
    return results


# ── analysis ──────────────────────────────────────────────────────────────────

def summarize(rows: list[dict]) -> dict:
    n = len(rows)
    high = [r for r in rows if r["confidence"] in ("high", "medium")]

    def pct(k, d):
        return round(100.0 * k / d, 1) if d else 0.0

    # Repo-level: collapse packages sharing one repo+file (monorepos).
    by_repo: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        if r["repo"]:
            by_repo[(r["repo"], r["changelog"])].append(r)
    repo_rows = [v[0] for v in by_repo.values()]

    def block(sample, label):
        m = len(sample)
        with_repo = [r for r in sample if r["repo"]]
        with_md = [r for r in sample if r["changelog_kind"] == "markdown"]
        with_rst = [r for r in sample if r["changelog_kind"] == "rst"]
        with_any = with_md + with_rst
        parseable = [r for r in with_any if r["parsed"]]
        clean = [r for r in with_any if r["strict_clean"]]
        return {
            "label": label, "n": m,
            "resolvable_repo": len(with_repo), "resolvable_repo_pct": pct(len(with_repo), m),
            "markdown_changelog": len(with_md), "markdown_changelog_pct": pct(len(with_md), m),
            "rst_changelog": len(with_rst), "rst_changelog_pct": pct(len(with_rst), m),
            "any_changelog_pct": pct(len(with_md) + len(with_rst), m),
            "parseable": len(parseable), "parseable_pct": pct(len(parseable), m),
            "parseable_of_files_pct": pct(len(parseable), len(with_any)),
            "parseable_md": sum(1 for r in with_md if r["parsed"]),
            "parseable_rst": sum(1 for r in with_rst if r["parsed"]),
            "clean_md": sum(1 for r in with_md if r["strict_clean"]),
            "clean_rst": sum(1 for r in with_rst if r["strict_clean"]),
            "strict_clean": len(clean), "strict_clean_pct": pct(len(clean), m),
            "zero_release_files": len(with_any) - len(parseable),
        }

    files = [r for r in rows if r["changelog_kind"]]
    codes = Counter(c for r in files for c in r["codes"])
    code_pct = {c: pct(k, len(files)) for c, k in codes.most_common()}
    by_kind = {}
    for kind in ("markdown", "rst"):
        sub = [r for r in rows if r["changelog_kind"] == kind]
        ck = Counter(c for r in sub for c in r["codes"])
        by_kind[kind] = {"n": len(sub),
                         "code_pct": {c: pct(k, len(sub)) for c, k in ck.most_common()}}

    return {
        "packages": block(rows, "package-level (all)"),
        "packages_confident": block(high, "package-level (confidence >= medium)"),
        "repos": block(repo_rows, "repo-level (deduplicated)"),
        "status_counts": dict(Counter(r["status"] for r in rows)),
        "confidence_counts": dict(Counter(str(r["confidence"]) for r in rows)),
        "code_frequency_pct_of_markdown": code_pct,
        "code_counts": dict(codes.most_common()),
        "by_format": by_kind,
        "n_packages": n,
        "n_distinct_repo_changelogs": len(by_repo),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=500)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--no-network", action="store_true")
    ap.add_argument("--out", default=str(HERE / "scan_results.json"))
    ap.add_argument("--partial", default=str(HERE / "scan_partial.jsonl"),
                    help="JSONL scratch file; makes the scan resumable")
    ap.add_argument("--budget", type=float, default=None,
                    help="stop after N seconds and exit cleanly (resume by re-running)")
    args = ap.parse_args()

    t0 = time.time()
    rows = run(args.limit, args.workers, network=not args.no_network,
               partial=Path(args.partial), budget=args.budget)
    if len(rows) < args.limit:
        print(f"\nINCOMPLETE: {len(rows)}/{args.limit} scanned - re-run to resume",
              file=sys.stderr)
    summary = summarize(rows)

    Path(args.out).write_text(json.dumps(rows, indent=1), encoding="utf-8")
    Path(args.out).with_name("scan_summary.json").write_text(
        json.dumps(summary, indent=1), encoding="utf-8")

    for key in ("packages", "packages_confident", "repos"):
        b = summary[key]
        print(f"\n{b['label']}  (n={b['n']})")
        print(f"  resolvable repo      {b['resolvable_repo']:4d}  {b['resolvable_repo_pct']:5.1f}%")
        print(f"  markdown changelog   {b['markdown_changelog']:4d}  {b['markdown_changelog_pct']:5.1f}%")
        print(f"  rST changelog        {b['rst_changelog']:4d}  {b['rst_changelog_pct']:5.1f}%")
        print(f"  parseable history    {b['parseable']:4d}  {b['parseable_pct']:5.1f}%")
        print(f"  strict-clean         {b['strict_clean']:4d}  {b['strict_clean_pct']:5.1f}%")
    print(f"\nelapsed {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
