"""Command-line entry point for the ePUB → Obsidian converter.

Thin wrapper around the :mod:`epub2obsidian` package so existing commands keep
working. For the graphical app, run ``python launch.py`` (or ``run.bat``).
"""

import argparse
import os
import sys

from epub2obsidian.converter import (
    DEFAULT_METADATA,
    DEFAULT_RESOURCES,
    convert_book,
    convert_to_markdown,
)


def main():
    parser = argparse.ArgumentParser(
        description="Convert an ePUB file into Obsidian-ready Markdown notes."
    )
    parser.add_argument("epub", help="Path to the input ePUB file")
    parser.add_argument(
        "outfile", nargs="?",
        help="Path for the intermediate Markdown output (used with --step-1)",
    )
    parser.add_argument("--metadata", default=DEFAULT_METADATA,
                        help="Path to YAML metadata template")
    parser.add_argument("--resources", default=DEFAULT_RESOURCES,
                        help="Path to resources Markdown template")
    parser.add_argument("--outdir", default="notes",
                        help="Output directory for notes (default: notes)")
    parser.add_argument("--heading-level", default="auto",
                        help="Heading level to split on, or 'auto' (default: auto)")
    parser.add_argument("--book-title", default=None,
                        help="Book title for YAML metadata (default: filename)")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--step-1", action="store_true",
                       help="Only convert the ePUB to a single Markdown file")
    args = parser.parse_args()

    # Windows consoles default to a legacy codepage; force UTF-8 so non-ASCII
    # titles and arrows don't crash printing.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    print("=== ePUB -> Obsidian conversion ===\n")

    if args.step_1:
        outfile = args.outfile or (os.path.splitext(args.epub)[0] + ".md")
        attachments = os.path.join(os.path.dirname(outfile) or ".", "attachments")
        convert_to_markdown(args.epub, attachments, outfile)
        print(f"\nWrote {outfile}")
        return

    summary = convert_book(
        args.epub,
        args.outdir,
        heading_level=args.heading_level,
        metadata_path=args.metadata,
        resources_path=args.resources,
        book_title=args.book_title,
    )
    if summary["count"] == 0:
        print("\nNo notes were created — check the heading level.")
        sys.exit(1)
    print(f"\n=== Done: {summary['count']} note(s) in {summary['output_dir']} ===")


if __name__ == "__main__":
    main()
