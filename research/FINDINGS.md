# Ecosystem scan: changelog machine-readability in the PyPI top 500

Corpus: the 500 most-downloaded PyPI packages ([hugovk/top-pypi-packages](https://hugovk.github.io/top-pypi-packages/), 30-day window).
Method: [`ecosystem_scan.py`](ecosystem_scan.py). Raw per-package rows in [`scan_results.json`](scan_results.json), aggregates in [`scan_summary.json`](scan_summary.json).

Both Markdown and reStructuredText changelogs are parsed. No format present in
the corpus at a conventional path is excluded from the analysis.

## Headline

| | packages (n=500) | repos, deduplicated (n=439) |
| --- | ---: | ---: |
| Resolvable source repo | 93.2% | 100% |
| Changelog in Markdown | 32.6% | 33.9% |
| Changelog in reStructuredText | 17.0% | 19.4% |
| **Any changelog at a conventional path** | **49.6%** | **53.3%** |
| Yields a parseable release history | 40.0% | 44.2% |
| Passes strict validation | **4.8%** | 5.5% |

Half of the most-depended-on packages in the Python ecosystem keep a changelog
where a tool would look for one. Of those, four in five yield a release history
a machine can read — but fewer than one in ten does so without the parser
having to recover something along the way.

The gap between "has a changelog" (49.6%) and "validates cleanly" (4.8%) is the
finding. The documentation effort has been made; the structure needed to consume
it mechanically has not.

## reStructuredText changelogs are markedly better structured

| | Markdown (n=163) | reStructuredText (n=85) |
| --- | ---: | ---: |
| Yields a release history | 79.8% | 82.4% |
| Passes strict validation | **3.1%** | **22.4%** |
| Median releases when parseable | 42 | 47 |
| Non-ISO date (PN101) | 57.1% | 5.9% |
| Malformed release header (PN103) | 80.4% | 27.1% |
| Entries outside any release (PN104) | 35.0% | 1.2% |
| Non-standard section heading (PN201) | 52.8% | 37.6% |

This was not the expected direction. rST changelogs are seven times more likely
to validate cleanly, and ten times less likely to carry a malformed date.

The plausible explanation is tooling: rST changelogs in this corpus are
overwhelmingly generated or gated — towncrier fragments assembled at release
time, or the rigidly templated output of AWS's release process. Markdown
changelogs are more often hand-edited, and hand-editing is where the
inconsistency enters. That reading is consistent with which packages come out
clean: `boto3`, `botocore`, `awscli`, `aiobotocore`, `s3transfer` (one release
pipeline), and the Pallets family — `flask`, `jinja2`, `markupsafe`,
`itsdangerous` (towncrier).

It is a correlation across 248 files, not a controlled comparison, and format
choice is confounded with project age, tooling, and organisational scale. But
it inverts the intuition that the newer, more popular format is the better
structured one, and it is directly testable.

## What the parser had to recover

Across all 248 packages with a changelog:

| Code | Meaning | Files affected |
| --- | --- | ---: |
| PN103 | Malformed or unrecognised release header | 62.1% |
| PN201 | Non-standard section heading | 47.6% |
| PN101 | Date not ISO 8601 | 39.5% |
| PN203 | Empty release section | 30.6% |
| PN104 | Entries outside any release block | 23.4% |
| PN207 | Orphaned compare link | 19.4% |
| PN206 | Missing compare link | 19.0% |
| PN204 | Content before the first release | 19.4% |
| PN102 | Duplicate version | 8.5% |

48 of the 248 files (19.4%) parse to **zero releases** — the text is present,
but no release boundary is recoverable. Among them: `click`, `uvicorn`,
`typing-extensions`, `pyarrow`, `tzdata`, and the entire opentelemetry family.

## Corrections to the 120-package pilot

The pilot's numbers were distorted by three bugs, all fixed here.

**Funding links parsed as repositories.** A bare `github.com/(owner)/(repo)`
regex matches `github.com/sponsors/hynek` as owner `sponsors`. Eight of the
pilot's 120 packages resolved that way and were all recorded as having no
changelog — including `attrs`, whose 1,350-line `CHANGELOG.md` sits at repo
root. Fixed with a blocklist of non-repository GitHub paths and a deny-list of
`project_urls` keys.

**Monorepo subdirectories discarded.** `google-auth`'s PyPI URL is
`googleapis/google-cloud-python/tree/main/packages/google-auth`. Dropping the
path resolved four google packages to the umbrella repo and attributed *its*
changelog to all of them — four rows with identical, wrong statistics. The
resolver now captures the subdirectory and searches it first; `google-auth`
resolves to its own changelog with 191 releases.

**rST counted as absence.** The largest correction. The pilot skipped `.rst`
entirely and scored those packages "no changelog found," which turned a format
gap into an apparent documentation gap — and, as the section above shows,
excluded precisely the subpopulation with the *best* structural hygiene. Of the
108 pilot packages that also appear in this corpus, 34 keep an rST changelog:
`boto3`, `cryptography`, `aiohttp`, `jinja2`, `jsonschema` among them.

| | pilot (120) | corrected (500) |
| --- | ---: | ---: |
| Has a changelog | 25% | 49.6% |
| Parseable release history | 13% | 40.0% |
| Strict-clean | 0 | 24 packages (4.8%) |

The direction of the finding survives. None of the magnitudes do.

## Limitations to state in any write-up

1. **Only conventional paths are checked** — `CHANGELOG/CHANGES/HISTORY/NEWS`
   in `.md` or `.rst`, at repo root or `docs/`, on the default branch, plus the
   declared monorepo subdirectory. Projects that keep release notes only in
   GitHub Releases, in a docs site, or under an unconventional name are scored
   as absent. The claim this supports is about **discoverability at conventional
   locations**, not about documentation effort.
2. **The validator defines the metric.** "Strict-clean" means zero patchnotes
   issues, which encodes Keep a Changelog conventions. A project using a
   different but internally consistent format is penalised. PN206/PN207
   (compare-link footnotes) in particular test spec conformance rather than
   machine-readability, and affect ~19% of files each; a two-tier metric
   separating "parseable" from "spec-conformant" would be more defensible.
3. **The rST parser is new and less battle-tested than the Markdown one.** It
   was written for this study, which is a conflict worth disclosing: the same
   tool defines both the measurement and the standard. Its 20 unit tests and the
   248 real files here are the only evidence for its correctness, and a parser
   bug would show up as inflated issue counts for rST projects. It currently
   reports *fewer* issues for rST, so any such bias runs against the reported
   conclusion rather than towards it.
4. **Downloads-ranked, not usage-ranked.** The top of PyPI by download count is
   dominated by CI and cloud-SDK infrastructure pulled by automation. AWS alone
   accounts for five of the 24 strict-clean packages. This is not a random
   sample of scientific software and shouldn't be described as one.
5. **Resolution confidence is recorded, not assumed.** 439/500 resolved at high
   confidence, 27 at medium/low, 34 not at all. Headline figures are reported
   both ways; they differ by under 3 points.

## Reproducing

```bash
python research/ecosystem_scan.py --limit 500
python research/ecosystem_scan.py --limit 500 --no-network   # from cache alone
```

Every HTTP response is cached under `research/cache/` (~300 MB, gitignored), so
re-analysis needs no network. Archive that directory alongside the results to
make the dataset independently checkable.
