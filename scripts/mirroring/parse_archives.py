#!/usr/bin/env python3
"""
Parse open_source_archives.bzl (Starlark) and output path|url for entries
whose key starts with src/open_source. Used by repo_archiver_update.sh.
"""

import json
import re
import sys
from pathlib import Path


def bzl_to_json(content: str) -> str:
    """Strip ARCHIVES = prefix and trailing commas to make valid JSON."""
    content = re.sub(r"^\s*ARCHIVES\s*=\s*", "", content)
    # Remove trailing commas before } or ] (valid in Starlark, invalid in JSON)
    content = re.sub(r",(\s*[}\]])", r"\1", content)
    return content


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: parse_archives.py <open_source_archives.bzl>", file=sys.stderr)
        return 1

    bzl_path = Path(sys.argv[1])
    if not bzl_path.exists():
        print(f"Error: file not found: {bzl_path}", file=sys.stderr)
        return 1

    content = bzl_path.read_text()
    try:
        data = json.loads(bzl_to_json(content))
    except json.JSONDecodeError as e:
        print(f"Error: failed to parse {bzl_path}: {e}", file=sys.stderr)
        return 1

    prefix = "src/open_source"
    for path, entry in data.items():
        if not path.startswith(prefix):
            continue
        if not isinstance(entry, dict):
            continue
        url = entry.get("url")
        if url:
            print(f"{path}|{url}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
