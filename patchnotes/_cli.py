"""
patchnotes._cli
Command-line interface for patchnotes.

Designed to be shell-script and CI friendly:

- Read from a file or stdin (pass ``-`` as the file argument).
- ``--format json`` for machine-readable output on every command.
- ``validate`` subcommand with meaningful exit codes.
- Emits GitHub Actions workflow annotations (::error / ::warning)
  automatically when running inside Actions, or with ``--github``.

Exit codes:
    0  success / changelog valid
    1  validation failed, version not found, or parse error
    2  usage error (bad arguments, file not found)
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from . import __version__, parse
from ._validation import Severity

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_USAGE = 2

#: command name -> number of required positional parameters
COMMANDS = {
    "latest": 0,
    "unreleased": 0,
    "show": 1,
    "diff": 2,
    "breaking": 0,
    "json": 0,
    "validate": 0,
    "bump": 1,
    "convert": 1,
    "fix": 0,
}

#: commands that accept an optional trailing file argument
#: (pre-commit passes matched filenames after the command:
#:  `patchnotes validate CHANGELOG.md`)
_TRAILING_FILE_OK = ("validate", "fix")


def _bind_params(parser, args) -> None:
    """Validate parameter counts and bind them to named attributes."""
    expected = COMMANDS.get(args.command, 0)
    got = len(args.params)
    if args.command in _TRAILING_FILE_OK and got == expected + 1:
        args.file = args.params.pop()
        got -= 1
    if got != expected:
        parser.error(
            f"command {args.command or '(summary)'!s} takes {expected} "
            f"argument(s), got {got}"
        )
    if args.command == "show":
        args.release_version = args.params[0]
    elif args.command == "diff":
        args.from_version, args.to_version = args.params
    elif args.command == "bump":
        args.new_version = args.params[0]
    elif args.command == "convert":
        args.output_path = args.params[0]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="patchnotes",
        description="Parse, query, and validate changelogs "
        "(Keep a Changelog markdown, YAML).",
    )
    parser.add_argument(
        "file",
        nargs="?",
        default="CHANGELOG.md",
        help="Path to changelog file, or '-' to read from stdin "
        "(default: ./CHANGELOG.md)",
    )
    parser.add_argument(
        "--version", action="version", version=f"patchnotes {__version__}"
    )
    parser.add_argument(
        "-f", "--format",
        choices=("text", "json"),
        default="text",
        help="Output format (default: text)",
    )
    parser.add_argument(
        "--input-format",
        choices=("auto", "markdown", "yaml"),
        default="auto",
        help="Changelog input format (default: auto-detect)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as failures (validate) / fail on any "
        "spec violation when parsing",
    )
    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Suppress non-essential output (useful in scripts; "
        "rely on the exit code)",
    )
    parser.add_argument(
        "--github",
        action="store_true",
        help="Emit GitHub Actions ::error/::warning annotations "
        "(auto-enabled when GITHUB_ACTIONS=true)",
    )
    parser.add_argument(
        "--fail-if-empty",
        action="store_true",
        help="With 'unreleased': exit 1 when there are no unreleased "
        "entries (enforce changelog updates in PRs)",
    )
    parser.add_argument(
        "--date",
        metavar="YYYY-MM-DD",
        help="With 'bump': release date (default: today)",
    )
    parser.add_argument(
        "--repo-url",
        metavar="URL",
        help="With 'bump'/'fix'/'convert': regenerate compare-link "
        "footnotes for this repository "
        "(e.g. https://github.com/you/project)",
    )
    parser.add_argument(
        "command",
        nargs="?",
        metavar="COMMAND",
        help="One of: latest, unreleased, show VERSION, diff FROM TO, "
        "breaking, json, validate, fix, bump VERSION, convert OUTPUT "
        "(default: summary of all releases)",
    )
    parser.add_argument(
        "params",
        nargs="*",
        metavar="ARGS",
        help="Arguments for the command (e.g. 'show 2.0.0', 'diff 1.0.0 2.0.0')",
    )

    args = parser.parse_intermixed_args(argv)

    # `file` is optional, so in `patchnotes latest` the command lands in the
    # file slot. Shift positionals when the first one is a known command.
    # (A file genuinely named e.g. 'latest' can be passed as './latest'.)
    if args.file in COMMANDS:
        if args.command is not None:
            args.params = [args.command, *args.params]
        args.command = args.file
        args.file = "CHANGELOG.md"

    if args.command is not None and args.command not in COMMANDS:
        parser.error(
            f"unknown command {args.command!r} "
            f"(choose from {', '.join(sorted(COMMANDS))})"
        )
    _bind_params(parser, args)
    strict = args.strict
    github = args.github or os.environ.get("GITHUB_ACTIONS") == "true"

    # ── Load ──────────────────────────────────────────────────────────────
    filename = None if args.file == "-" else args.file
    try:
        if args.file == "-":
            text = sys.stdin.read()
        else:
            with open(args.file, "r", encoding="utf-8") as fh:
                text = fh.read()
    except FileNotFoundError:
        print(f"Error: file not found: {args.file}", file=sys.stderr)
        return EXIT_USAGE
    except OSError as e:
        print(f"Error reading {args.file}: {e}", file=sys.stderr)
        return EXIT_USAGE

    try:
        cl = parse(text, format=args.input_format, filename=filename)
    except ImportError as e:  # missing optional PyYAML
        print(f"Error: {e}", file=sys.stderr)
        return EXIT_USAGE
    except Exception as e:
        print(f"Error parsing {args.file}: {e}", file=sys.stderr)
        return EXIT_FAIL

    # ── Dispatch ──────────────────────────────────────────────────────────
    if args.command == "validate":
        return _cmd_validate(cl, args, strict=strict, github=github)

    # Outside `validate`/`fix`, --strict means "refuse to operate on a
    # broken file" (ERROR-severity issues; use `validate --strict` to also
    # fail on warnings). `fix` is exempt: repairing broken files is its job.
    if strict and args.command != "fix":
        issues = cl.validate()
        if any(i.severity is Severity.ERROR for i in issues):
            for i in issues:
                _print_issue(i, args.file, github)
            print(
                f"Error: {args.file} failed strict validation "
                f"({len(issues)} issue(s)).",
                file=sys.stderr,
            )
            return EXIT_FAIL

    if args.command is None:
        return _cmd_summary(cl, args)
    if args.command == "latest":
        return _cmd_single(cl.latest(), "No releases found.", args)
    if args.command == "unreleased":
        u = cl.unreleased()
        if args.fail_if_empty and (u is None or not u.entries):
            print(
                "Error: no unreleased changes found — add an entry to the "
                "[Unreleased] section.",
                file=sys.stderr,
            )
            return EXIT_FAIL
        return _cmd_single(u, "No unreleased changes.", args)
    if args.command == "bump":
        return _cmd_bump(cl, args)
    if args.command == "convert":
        return _cmd_convert(cl, args)
    if args.command == "fix":
        return _cmd_fix(cl, args, github=github)
    if args.command == "show":
        r = cl.get_version(args.release_version)
        if not r:
            print(f"Version {args.release_version!r} not found.", file=sys.stderr)
            return EXIT_FAIL
        return _cmd_single(r, "", args)
    if args.command == "diff":
        return _cmd_diff(cl, args)
    if args.command == "breaking":
        return _cmd_breaking(cl, args)
    if args.command == "json":
        print(cl.to_json())
        return EXIT_OK
    return EXIT_USAGE  # pragma: no cover


# ── Commands ──────────────────────────────────────────────────────────────────

def _cmd_summary(cl, args) -> int:
    if args.format == "json":
        print(cl.to_json())
        return EXIT_OK
    print(f"{cl.title}")
    if cl.description:
        print(f"  {cl.description}")
    print()
    for r in cl.releases:
        tag = " [YANKED]" if r.yanked else ""
        tag += " [unreleased]" if r.is_unreleased else ""
        date_str = f"  {r.release_date}" if r.release_date else ""
        print(f"  v{r.version}{date_str}{tag}  ({len(r.entries)} changes)")
    return EXIT_OK


def _cmd_single(release, empty_msg: str, args) -> int:
    if not release:
        if args.format == "json":
            print("null")
        elif not args.quiet:
            print(empty_msg)
        return EXIT_OK
    if args.format == "json":
        print(json.dumps(release.to_dict(), indent=2, default=str))
    else:
        _print_release(release)
    return EXIT_OK


def _cmd_diff(cl, args) -> int:
    try:
        releases = cl.diff(args.from_version, args.to_version)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return EXIT_FAIL
    if args.format == "json":
        print(json.dumps([r.to_dict() for r in releases], indent=2, default=str))
        return EXIT_OK
    if not releases:
        if not args.quiet:
            print("No changes found between those versions.")
        return EXIT_OK
    for r in releases:
        _print_release(r)
        print()
    return EXIT_OK


def _cmd_breaking(cl, args) -> int:
    changes = cl.all_breaking_changes()
    if args.format == "json":
        print(json.dumps(
            [
                {"version": v, **e.to_dict()}
                for v, e in changes
            ],
            indent=2,
        ))
        return EXIT_OK
    if not changes:
        if not args.quiet:
            print("No breaking changes found.")
        return EXIT_OK
    for version, entry in changes:
        print(f"  v{version}  [{entry.change_type.value}]  {entry.text}")
    return EXIT_OK


def _cmd_validate(cl, args, strict: bool, github: bool) -> int:
    issues = cl.validate()
    errors = [i for i in issues if i.severity is Severity.ERROR]
    warnings = [i for i in issues if i.severity is Severity.WARNING]
    failed = bool(errors) or (strict and bool(issues))

    if args.format == "json":
        print(json.dumps(
            {
                "file": args.file,
                "valid": not failed,
                "strict": strict,
                "errors": len(errors),
                "warnings": len(warnings),
                "issues": [i.to_dict() for i in issues],
            },
            indent=2,
        ))
        return EXIT_FAIL if failed else EXIT_OK

    for i in issues:
        _print_issue(i, args.file, github)

    if not args.quiet:
        status = "FAIL" if failed else "OK"
        mode = " (strict)" if strict else ""
        print(
            f"{args.file}: {status}{mode} — "
            f"{len(errors)} error(s), {len(warnings)} warning(s)"
        )
    return EXIT_FAIL if failed else EXIT_OK


def _writer_for(path: str, args):
    """Pick the output renderer (markdown or YAML) for a target path."""
    from ._write import to_markdown, to_yaml

    if path.lower().endswith((".yml", ".yaml")) or (
        path == "-" and args.input_format == "yaml"
    ):
        return lambda cl: to_yaml(cl)
    return lambda cl: to_markdown(cl, repo_url=args.repo_url)


def _cmd_bump(cl, args) -> int:
    import datetime

    if args.file == "-":
        print("Error: 'bump' needs a real file, not stdin.", file=sys.stderr)
        return EXIT_USAGE

    release_date = None
    if args.date:
        try:
            release_date = datetime.date.fromisoformat(args.date)
        except ValueError:
            print(f"Error: invalid --date {args.date!r} (expected YYYY-MM-DD).",
                  file=sys.stderr)
            return EXIT_USAGE

    try:
        release = cl.bump(args.new_version, release_date=release_date)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return EXIT_FAIL

    text = _writer_for(args.file, args)(cl)
    with open(args.file, "w", encoding="utf-8") as fh:
        fh.write(text)
    if not args.quiet:
        print(
            f"Released {release.version} ({release.release_date}) with "
            f"{len(release.entries)} entr{'y' if len(release.entries) == 1 else 'ies'} "
            f"-> {args.file}"
        )
    return EXIT_OK


def _cmd_convert(cl, args) -> int:
    out = args.output_path
    if not out.lower().endswith((".md", ".markdown", ".yml", ".yaml")) and out != "-":
        print(
            f"Error: can't infer output format from {out!r} "
            "(use a .md, .markdown, .yml, or .yaml extension).",
            file=sys.stderr,
        )
        return EXIT_USAGE
    text = _writer_for(out, args)(cl)
    if out == "-":
        sys.stdout.write(text)
        return EXIT_OK
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(text)
    if not args.quiet:
        print(f"Wrote {out} ({len(cl.releases)} releases).")
    return EXIT_OK


def _cmd_fix(cl, args, github: bool) -> int:
    issues = cl.validate()
    fixable = [i for i in issues if i.line is not None]
    remaining = [i for i in issues if i.line is None]

    text = _writer_for(args.file, args)(cl)
    if args.file == "-":
        sys.stdout.write(text)
    else:
        with open(args.file, "w", encoding="utf-8") as fh:
            fh.write(text)

    if not args.quiet:
        for i in fixable:
            print(f"  fixed: {i}", file=sys.stderr)
        for i in remaining:
            print(f"  not auto-fixable: {i}", file=sys.stderr)
        target = "stdout" if args.file == "-" else args.file
        print(
            f"{target}: normalized ({len(fixable)} issue(s) fixed, "
            f"{len(remaining)} remaining)",
            file=sys.stderr,
        )
    return EXIT_OK


# ── Output helpers ────────────────────────────────────────────────────────────

def _print_issue(issue, file: str, github: bool) -> None:
    if github:
        level = "error" if issue.severity is Severity.ERROR else "warning"
        loc = f",line={issue.line}" if issue.line is not None else ""
        # https://docs.github.com/actions/reference/workflow-commands
        print(f"::{level} file={file}{loc},title=patchnotes {issue.code}::{issue.message}")
    else:
        print(f"  {issue}", file=sys.stderr)


def _print_release(r) -> None:
    date_str = f" — {r.release_date}" if r.release_date else ""
    flags = []
    if r.yanked:
        flags.append("YANKED")
    if r.is_unreleased:
        flags.append("UNRELEASED")
    flag_str = f"  [{', '.join(flags)}]" if flags else ""
    print(f"v{r.version}{date_str}{flag_str}")
    print()
    for type_name, entries in r.by_type.items():
        print(f"  {type_name}")
        for e in entries:
            print(f"    - {e.text}")
    print()


if __name__ == "__main__":
    sys.exit(main())
