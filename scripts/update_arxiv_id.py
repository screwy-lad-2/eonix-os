#!/usr/bin/env python3
"""
Post-arXiv-submission helper.
Run once you receive your arXiv paper ID (e.g. 2603.12345).

Usage:
    python scripts/update_arxiv_id.py 2603.12345

This script updates every occurrence of the placeholder '2603.XXXXX'
in README.md, docs/arxiv-paper.md, and docs/arxiv-paper.tex with the
real arXiv ID, then prints a git command you can copy-paste.
"""
import argparse
import pathlib
import re
import sys

PLACEHOLDER = "2603.XXXXX"
REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

FILES_TO_PATCH = [
    REPO_ROOT / "README.md",
    REPO_ROOT / "docs" / "arxiv-paper.md",
    REPO_ROOT / "docs" / "arxiv-paper.tex",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Replace arXiv placeholder with real ID")
    parser.add_argument("arxiv_id", help="The real arXiv ID, e.g. 2603.12345")
    args = parser.parse_args()

    arxiv_id = args.arxiv_id.strip()
    if not re.match(r"^\d{4}\.\d{4,5}(v\d+)?$", arxiv_id):
        print(f"ERROR: '{arxiv_id}' doesn't look like a valid arXiv ID (expected e.g. 2603.12345)")
        sys.exit(1)

    total = 0
    for fpath in FILES_TO_PATCH:
        if not fpath.exists():
            print(f"  SKIP  {fpath.relative_to(REPO_ROOT)} (not found)")
            continue
        text = fpath.read_text(encoding="utf-8")
        count = text.count(PLACEHOLDER)
        if count == 0:
            print(f"  SKIP  {fpath.relative_to(REPO_ROOT)} (no placeholder found)")
            continue
        new_text = text.replace(PLACEHOLDER, arxiv_id)
        fpath.write_text(new_text, encoding="utf-8")
        print(f"  DONE  {fpath.relative_to(REPO_ROOT)} — {count} replacement(s)")
        total += count

    if total == 0:
        print("\nNo placeholders found. Already updated?")
    else:
        print(f"\n✅ Replaced {total} occurrence(s) of '{PLACEHOLDER}' → '{arxiv_id}'")
        print(f"\nNext steps:")
        print(f"  git add -A")
        print(f"  git commit -m \"docs: update arXiv ID to {arxiv_id}\"")
        print(f"  git push origin master")


if __name__ == "__main__":
    main()
