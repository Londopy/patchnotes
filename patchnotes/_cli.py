"""
patchnotes._cli
Command-line interface for patchnotes.
"""

import argparse
import sys
import json
from . import parse_file, parse, __version__


def main():
    parser = argparse.ArgumentParser(
        prog="patchnotes",
        description="Parse and query Keep a Changelog formatted CHANGELOG.md files.",
    )
    parser.add_argument("file", nargs="?", default="CHANGELOG.md",
                        help="Path to CHANGELOG.md (default: ./CHANGELOG.md)")
    parser.add_argument("--version", action="version", version=f"patchnotes {__version__}")

    sub = parser.add_subparsers(dest="command")

    # patchnotes latest
    sub.add_parser("latest", help="Show the latest release")

    # patchnotes unreleased
    sub.add_parser("unreleased", help="Show unreleased changes")

    # patchnotes show <version>
    show_p = sub.add_parser("show", help="Show a specific version")
    show_p.add_argument("release_version", metavar="VERSION")

    # patchnotes diff <from> <to>
    diff_p = sub.add_parser("diff", help="Show changes between two versions")
    diff_p.add_argument("from_version", metavar="FROM")
    diff_p.add_argument("to_version", metavar="TO")

    # patchnotes breaking
    sub.add_parser("breaking", help="List all breaking changes across all versions")

    # patchnotes json
    sub.add_parser("json", help="Dump entire changelog as JSON")

    args = parser.parse_args()

    # Load changelog
    try:
        cl = parse_file(args.file)
    except FileNotFoundError:
        print(f"Error: file not found: {args.file}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error parsing {args.file}: {e}", file=sys.stderr)
        sys.exit(1)

    # Default: show summary
    if args.command is None:
        print(f"{cl.title}")
        if cl.description:
            print(f"  {cl.description}")
        print()
        for r in cl.releases:
            tag = " [YANKED]" if r.yanked else ""
            tag += " [unreleased]" if r.is_unreleased else ""
            date_str = f"  {r.release_date}" if r.release_date else ""
            print(f"  v{r.version}{date_str}{tag}  ({len(r.entries)} changes)")
        return

    if args.command == "latest":
        r = cl.latest()
        if not r:
            print("No releases found.")
            return
        _print_release(r)

    elif args.command == "unreleased":
        r = cl.unreleased()
        if not r:
            print("No unreleased changes.")
            return
        _print_release(r)

    elif args.command == "show":
        r = cl.get_version(args.release_version)
        if not r:
            print(f"Version {args.release_version!r} not found.", file=sys.stderr)
            sys.exit(1)
        _print_release(r)

    elif args.command == "diff":
        try:
            releases = cl.diff(args.from_version, args.to_version)
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        if not releases:
            print("No changes found between those versions.")
            return
        for r in releases:
            _print_release(r)
            print()

    elif args.command == "breaking":
        changes = cl.all_breaking_changes()
        if not changes:
            print("No breaking changes found.")
            return
        for version, entry in changes:
            print(f"  v{version}  [{entry.change_type.value}]  {entry.text}")

    elif args.command == "json":
        print(cl.to_json())


def _print_release(r):
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
    main()
