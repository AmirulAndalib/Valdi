#!/usr/bin/env python3
"""
Validate that external contributors are not using @snapchat.com, @snap.com, or @c.snap.com
email addresses. Prevents impersonation of Snapchat employees.
Validates commits in the current git repository.
"""

import argparse
import subprocess
import sys
from typing import Optional

# ANSI colors
RED = "\033[0;31m"
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
NC = "\033[0m"  # No Color

INTERNAL_DOMAINS = ("@snapchat.com", "@snap.com", "@c.snap.com")


def is_internal_email(email: str) -> bool:
    """Check if an email is from an internal Snapchat domain."""
    return any(domain in email for domain in INTERNAL_DOMAINS)


def get_commits_in_range(commit_range: str) -> Optional[list[tuple[str, str, str, str]]]:
    """Return list of (hash, author_name, author_email, subject) for commits in range, or None on failure."""
    result = subprocess.run(
        [
            "git",
            "log",
            "--pretty=format:%H|%an|%ae|%s",
            commit_range,
            "--no-merges",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None

    commits = []
    for line in (result.stdout or "").strip().splitlines():
        parts = line.split("|", 3)
        if len(parts) >= 4:
            commits.append((parts[0], parts[1], parts[2], parts[3]))
    return commits


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate commits for internal Snapchat email addresses"
    )
    parser.add_argument(
        "--commit-range",
        required=True,
        metavar="RANGE",
        help="Git commit range (e.g. 'HEAD~5..HEAD' or 'abc123..def456')",
    )
    args = parser.parse_args()

    print("────────────────────────────────────────────────────────────────")
    print(" Checking for internal Snapchat email addresses")
    print("────────────────────────────────────────────────────────────────")
    print()
    print(f"  Commit range: {args.commit_range}")
    print()

    commits = get_commits_in_range(args.commit_range)
    if commits is None:
        print(f"{RED}Error: git log failed{NC}", file=sys.stderr)
        return 1

    if not commits:
        print(f"{YELLOW}⚠️  No commits found to validate{NC}")
        return 0

    internal_commits = []
    for hash_val, author_name, author_email, subject in commits:
        if is_internal_email(author_email):
            internal_commits.append(f"{hash_val}: {author_name} <{author_email}> - {subject}")
            print(f"{RED}  ❌ Commit {hash_val}: Internal email detected: {author_name} <{author_email}>{NC}")
        else:
            print(f"{GREEN}  ✅ Commit {hash_val}: External author: {author_name} <{author_email}>{NC}")

    print()
    print(f"  Checked {len(commits)} commit(s)")
    print()

    if internal_commits:
        print(f"{RED}════════════════════════════════════════════════════════════════{NC}")
        print(f"{RED} ❌ Validation FAILED{NC}")
        print(f"{RED}════════════════════════════════════════════════════════════════{NC}")
        print()
        print("The following commits contain internal Snapchat email addresses (@snapchat.com, @snap.com, or @c.snap.com):")
        print()
        for info in internal_commits:
            print(f"  - {info}")
        print()
        print("External contributors cannot use Snapchat employee email addresses.")
        return 1

    print(f"{GREEN}✅ Email validation passed - no internal Snapchat addresses found{NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
