#!/usr/bin/env python3
"""
Import a PR from open source Valdi (production or staging) to the internal mobile repo.
Runs Copybara locally with proper Git configuration for line endings.
"""

import argparse
import contextlib
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

# Copybara renames (external path -> internal path under OPEN_SOURCE_PREFIX)
_EXTERNAL_TO_INTERNAL_RENAMES = {
    ".gitignore": ".gitignore.copybara",
    ".gitattributes": ".gitattributes.copybara",
    "README.md": "README.copybara",
    "bzl/additional_dependencies.bzl": "bzl/additional_dependencies.bzl.copybara",
}

# ANSI colors
RED = "\033[0;31m"
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
NC = "\033[0m"  # No Color

SCRIPT_DIR = Path(__file__).resolve().parent
MIRRORING_REFS = ("scripts/mirroring", "scripts\\mirroring")
OPEN_SOURCE_PREFIX = "client/src/open_source/"
# Copybara's default output root; the run-scoped bare mirror of the mobile repo lives
# under here at COPYBARA_CACHE_SUBPATH. Override with --output-root (e.g. in CI, to a
# per-run disposable dir) so the mirror never collides with the fixed $HOME/copybara path.
DEFAULT_OUTPUT_ROOT = Path.home() / "copybara"
COPYBARA_CACHE_SUBPATH = (
    "cache/git_repos/git%40github%2Esc-corp%2Enet%3ASnapchat%2Fmobile%2Egit"
)
MIRROR_TAG = "valdi-last-mirror"
# External-PR lookups always target github.com over plain HTTPS rather than shelling out to
# the gh CLI, because gh is not installed on the SnapCI workers this import runs on. The base
# is hardcoded (not derived from any env) so a stray GH_HOST can't redirect these reads to the
# internal GHE instance, where the PR number means something else.
GITHUB_API_BASE = "https://api.github.com"
# A token is required only for the private staging repo; the public Valdi repo reads without
# one. CI injects GH_TOKEN/GITHUB_TOKEN for the staging path (see ValdiImportPrStep).
_GITHUB_TOKEN_ENV_VARS = ("GH_TOKEN", "GITHUB_TOKEN", "GH_API_TOKEN")


@dataclass(frozen=True)
class ImportConfig:
    """Configuration for a single import (production or staging)."""

    workflow: str
    default_branch: str
    source_url: str
    use_staging: bool


def run(
    cmd: list[str],
    *,
    capture: bool = True,
    cwd: Optional[Path] = None,
    env: Optional[dict[str, str]] = None,
    check: bool = True,
    stdin_text: Optional[str] = None,
) -> subprocess.CompletedProcess:
    full_env = {**os.environ, **(env or {})}
    result = subprocess.run(
        cmd,
        capture_output=capture,
        text=True,
        cwd=cwd,
        env=full_env,
        check=False,
        input=stdin_text,
    )
    if check and result.returncode != 0:
        if not capture and result.stdout:
            print(result.stdout, end="")
        if result.stderr:
            print(result.stderr, file=sys.stderr, end="")
        sys.exit(result.returncode)
    return result


def get_git_root() -> Path:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
    )
    return Path(result.stdout.strip()) if result.returncode == 0 else Path.cwd()


def branch_exists(git_root: Path, branch: str) -> bool:
    return (
        run(
            ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
            cwd=git_root,
            check=False,
        ).returncode
        == 0
    )


def get_mirror_base(git_root: Path) -> str:
    """Return the ref to branch from when creating an import branch.

    Fetches the valdi-last-mirror tag from origin (set by mirror.sh after each outbound
    Copybara run). Falls back to master with a warning if the tag doesn't exist yet.
    """
    result = run(
        [
            "git",
            "fetch",
            "--force",
            "origin",
            f"refs/tags/{MIRROR_TAG}:refs/tags/{MIRROR_TAG}",
        ],
        cwd=git_root,
        check=False,
        capture=True,
    )
    if result.returncode == 0:
        return MIRROR_TAG
    print(
        f"{YELLOW}⚠️  Tag '{MIRROR_TAG}' not found on origin; branching from master instead.\n"
        f"   Run mirror.sh once to establish the baseline tag.{NC}\n"
    )
    return "master"


def get_config(pr_number: str, use_staging: bool) -> ImportConfig:
    if use_staging:
        return ImportConfig(
            workflow="stage_staging_pull_request",
            default_branch=f"valdi_staging_pr_{pr_number}",
            source_url="github.com/Snapchat/valdi_staging",
            use_staging=True,
        )
    return ImportConfig(
        workflow="stage_public_pull_request",
        default_branch=f"valdi_github_pr_{pr_number}",
        source_url="github.com/Snapchat/Valdi",
        use_staging=False,
    )


def check_mirroring_reference(file_path: str, git_root: Path) -> bool:
    """True if file path or symlink target references scripts/mirroring."""
    if any(ref in file_path for ref in MIRRORING_REFS):
        return True
    full_path = (
        Path(file_path) if Path(file_path).is_absolute() else git_root / file_path
    )
    if not full_path.exists():
        return False
    try:
        if full_path.is_symlink():
            target = full_path.resolve()
            if any(ref in str(target) for ref in MIRRORING_REFS):
                return True
    except OSError:
        pass
    return False


def _refs_mirroring(text: str) -> bool:
    return any(ref in text for ref in MIRRORING_REFS)


def path_has_dotfile_or_dotfolder(path: str) -> bool:
    """True if any path component is a dot file or dot folder (e.g. .gitignore, .github/, .dir/foo)."""
    parts = re.split(r"[/\\]", path)
    if any(len(p) > 0 and p[0] == "." and p not in (".", "..") for p in parts):
        return True
    # Catch .github even if normalized without leading dot in some APIs
    return "/.github/" in path or path.startswith(".github/") or "\\.github\\" in path


def collect_blocked_files(
    git_root: Path,
    copybara_commit: str,
    copybara_parent: str,
    file_paths: list[str],
    run_fn: Callable[..., subprocess.CompletedProcess],
) -> list[str]:
    """Return list of file paths (or descriptions) that reference scripts/mirroring."""
    blocked = []
    for file_path in file_paths:
        if check_mirroring_reference(file_path, git_root):
            blocked.append(file_path)
            continue
        diff_result = run_fn(
            ["git", "diff", copybara_parent, copybara_commit, "--", file_path],
            cwd=git_root,
            capture=True,
        )
        if _refs_mirroring(diff_result.stdout):
            blocked.append(file_path)
            continue
        ls_tree = run_fn(
            ["git", "ls-tree", "-r", copybara_commit, "--", file_path],
            cwd=git_root,
            capture=True,
        )
        if "120000" not in ls_tree.stdout:
            continue
        show_result = run_fn(
            ["git", "show", f"{copybara_commit}:{file_path}"],
            cwd=git_root,
            capture=True,
            check=False,
        )
        symlink_target = (show_result.stdout or "").strip()
        if symlink_target and _refs_mirroring(symlink_target):
            blocked.append(f"{file_path} (symlink target: {symlink_target})")
    return blocked


def _blob_id(
    git_root: Path,
    rev: str,
    file_path: str,
    run_fn: Callable[..., subprocess.CompletedProcess],
) -> Optional[str]:
    """Return the blob id of file_path at rev, or None if it does not exist there."""
    result = run_fn(
        ["git", "rev-parse", f"{rev}:{file_path}"],
        cwd=git_root,
        capture=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def collect_drifted_files(
    git_root: Path,
    copybara_parent: str,
    file_paths: list[str],
    run_fn: Callable[..., subprocess.CompletedProcess],
) -> list[str]:
    """Return files whose internal content has moved on from the external base.

    Copybara's parent commit is the external tree the PR branched from. Where the internal
    file no longer matches it, the internal side carries changes the external PR never saw
    (a master merge into the import branch, or a maintainer fixup). Overwriting such a file
    wholesale is what silently reverts internal work, so these files must be merged rather
    than replaced.
    """
    drifted = []
    for file_path in file_paths:
        internal_blob = _blob_id(git_root, "HEAD", file_path, run_fn)
        base_blob = _blob_id(git_root, copybara_parent, file_path, run_fn)
        if internal_blob is None or base_blob is None:
            # Added on one side only; there is no internal delta to lose.
            continue
        if internal_blob != base_blob:
            drifted.append(file_path)
    return drifted


def apply_files_three_way(
    git_root: Path,
    copybara_parent: str,
    copybara_commit: str,
    file_paths: list[str],
    run_fn: Callable[..., subprocess.CompletedProcess],
) -> list[str]:
    """Apply Copybara's diff for file_paths as a three-way merge and stage the result.

    Returns the paths that could not be merged. Replacing files wholesale (git checkout
    <commit> -- <path>) discards anything the internal side added, so the diff is merged
    instead.

    A conflict is deliberately left in the index and working tree: resolving it is the whole
    point of the manual run the caller hands off to, and restoring the paths would leave the
    operator nothing to resolve. Markers still cannot reach a commit because the caller exits
    before committing.
    """
    diff = run_fn(
        [
            "git",
            "diff",
            "--binary",
            copybara_parent,
            copybara_commit,
            "--",
            *file_paths,
        ],
        cwd=git_root,
        capture=True,
    )
    if not diff.stdout.strip():
        return []

    result = run_fn(
        ["git", "apply", "--3way", "--index", "-"],
        cwd=git_root,
        capture=True,
        check=False,
        stdin_text=diff.stdout,
    )
    if result.returncode == 0:
        return []

    unmerged = run_fn(
        ["git", "diff", "--name-only", "--diff-filter=U"],
        cwd=git_root,
        capture=True,
        check=False,
    )
    conflicts = [f for f in unmerged.stdout.splitlines() if f]
    if not conflicts:
        # The patch did not apply at all; surface every path so the failure is actionable.
        conflicts = list(file_paths)
        if result.stderr:
            print(result.stderr, file=sys.stderr, end="")

    return conflicts


def _stage_paths(
    git_root: Path,
    file_paths: list[str],
    run_fn: Callable[..., subprocess.CompletedProcess],
) -> None:
    """Stage file_paths, skipping the ones git can no longer match.

    A path the import deleted is gone from both the index and the working tree by this point,
    and its deletion is already staged. Passing it to git add anyway fails the whole command
    with "pathspec did not match any files", which would abort an otherwise clean import.
    """
    present = [f for f in file_paths if (git_root / f).exists()]
    if present:
        run_fn(["git", "add", "--all", "--"] + present, cwd=git_root, capture=False)


def stage_imported_files(
    git_root: Path,
    copybara_parent: str,
    copybara_commit: str,
    file_paths: list[str],
    allow_clobber: bool,
    run_fn: Callable[..., subprocess.CompletedProcess] = run,
    manual_command: Optional[str] = None,
) -> None:
    """Stage the imported files, exiting if the import cannot be applied safely.

    manual_command is the invocation to re-run by hand, quoted back to the operator when a
    merge conflicts. A conflict needs a human, so an automated run has to hand off rather
    than guess.
    """
    if allow_clobber:
        print(
            f"{YELLOW}⚠️  --allow-clobber: replacing files wholesale. Any internal-only "
            f"changes in them will be discarded.{NC}\n"
        )
        for file_path in file_paths:
            if _blob_id(git_root, copybara_commit, file_path, run_fn) is None:
                # Deleted by the PR: checkout has nothing to restore from and would leave the
                # internal file in place, silently reverting the deletion.
                run_fn(
                    [
                        "git",
                        "rm",
                        "--quiet",
                        "--force",
                        "--ignore-unmatch",
                        "--",
                        file_path,
                    ],
                    cwd=git_root,
                    capture=True,
                    check=False,
                )
                continue
            run_fn(
                ["git", "checkout", copybara_commit, "--", file_path],
                cwd=git_root,
                capture=True,
                check=False,
            )
        _stage_paths(git_root, file_paths, run_fn)
        return

    drifted = collect_drifted_files(git_root, copybara_parent, file_paths, run_fn)
    if drifted:
        print(
            f"{YELLOW}────────────────────────────────────────────────────────────────{NC}"
        )
        print(
            f"{YELLOW} ℹ️  {len(drifted)} file(s) changed internally since the external "
            f"PR branched:{NC}"
        )
        print(
            f"{YELLOW}────────────────────────────────────────────────────────────────{NC}"
        )
        print()
        for file_path in drifted:
            print(f"  {file_path}")
        print()
        print(
            "Their internal changes are preserved by merging the PR's diff instead of\n"
            "overwriting the files. Review the result if the merge looks surprising."
        )
        print()

    conflicts = apply_files_three_way(
        git_root, copybara_parent, copybara_commit, file_paths, run_fn
    )
    if conflicts:
        print(
            f"{RED}════════════════════════════════════════════════════════════════{NC}"
        )
        print(
            f"{RED} Import BLOCKED: the PR's changes conflict with the internal tree{NC}"
        )
        print(
            f"{RED}════════════════════════════════════════════════════════════════{NC}"
        )
        print("\nCould not merge:")
        for file_path in conflicts:
            print(f"  {file_path}")
        print(
            "\nNothing was committed. This import cannot be finished automatically:\n"
            "resolving a conflict needs a human decision about which side wins."
        )
        print(
            "\nThe conflict markers are left in the working tree, so the merge can be fixed by\n"
            "hand from here. Run the import locally if you are not already there:\n"
        )
        print("  cd client/src/open_source/scripts/mirroring")
        print(f"  {manual_command or './import_pr.py <PR_NUMBER>'}")
        print(
            "\nThen resolve the conflicting file(s), commit, and push the import branch.\n"
            "To abandon the attempt instead: git reset --hard HEAD && git clean -fd\n"
            "Alternatively ask the PR author to merge the upstream default branch into their\n"
            "branch, which usually removes the conflict, and re-run the import.\n"
            "Re-run with --allow-clobber only to take the PR's version of every file and\n"
            "discard the internal changes."
        )
        sys.exit(1)

    _stage_paths(git_root, file_paths, run_fn)


def block_mirroring_in_args(pr_number: str, target_branch: Optional[str]) -> None:
    for ref in MIRRORING_REFS:
        if ref in pr_number:
            print(
                f"{RED}Error: Reference to scripts/mirroring not allowed in PR_NUMBER{NC}"
            )
            sys.exit(1)
        if target_branch and ref in target_branch:
            print(
                f"{RED}Error: Reference to scripts/mirroring not allowed in TARGET_BRANCH{NC}"
            )
            sys.exit(1)


def _is_safe_path(git_root: Path, file_path: str) -> bool:
    """Return True if file_path resolves safely under git_root with OPEN_SOURCE_PREFIX.

    Guards against path traversal sequences (e.g. client/src/open_source/../../../other)
    and symlinks that escape the repository root.
    """
    try:
        resolved = (git_root / file_path).resolve()
        git_root_resolved = git_root.resolve()
        rel = resolved.relative_to(git_root_resolved)
        return str(rel).startswith(OPEN_SOURCE_PREFIX)
    except (ValueError, OSError):
        return False


def _external_path_to_internal(filename: str) -> str:
    """Map external repo path to internal path (client/src/open_source/...)."""
    normalized = filename.replace("\\", "/")
    internal_name = _EXTERNAL_TO_INTERNAL_RENAMES.get(normalized, normalized)
    return OPEN_SOURCE_PREFIX + internal_name


def get_external_pr_info(
    pr_number: str, use_staging: bool
) -> Optional[tuple[str, str]]:
    """Fetch title and author login of the external PR. Returns (title, author_login) or None."""
    repo = "valdi_staging" if use_staging else "Valdi"
    data = _github_api_json(f"/repos/Snapchat/{repo}/pulls/{pr_number}")
    if not isinstance(data, dict):
        return None
    title = data.get("title", "")
    author = (data.get("user") or {}).get("login", "")
    return (title, author) if title or author else None


def get_pr_changed_files(pr_number: str, use_staging: bool) -> Optional[set[str]]:
    """Fetch list of files changed in the external PR; return set of internal paths, or None on failure.

    A rename has two paths: `filename` (the new one) and `previous_filename` (the one being
    deleted). Both belong in the set. Dropping the old one filters the delete half of the
    rename out of the import, which lands the file at both paths.
    """
    repo = "valdi_staging" if use_staging else "Valdi"
    files = _github_api_json(
        f"/repos/Snapchat/{repo}/pulls/{pr_number}/files", paginate=True
    )
    if not isinstance(files, list):
        return None
    internal = set()
    for entry in files:
        if not isinstance(entry, dict):
            continue
        for key in ("filename", "previous_filename"):
            name = entry.get(key)
            if name:
                internal.add(_external_path_to_internal(name))
    return internal if internal else None


def _github_token() -> Optional[str]:
    """Return a github.com API token from the environment, or None (public reads need none)."""
    for var in _GITHUB_TOKEN_ENV_VARS:
        token = os.environ.get(var)
        if token:
            return token
    return None


def _http_get_json(url: str) -> object:
    """GET a github.com REST URL and return the parsed JSON body.

    Raises on any transport or decode error; callers translate that to None.
    """
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "valdi-import-pr",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = _github_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode())


def _github_api_json(path: str, paginate: bool = False) -> Optional[object]:
    """Fetch api.github.com{path} and return parsed JSON, or None on any failure.

    Replaces the former `gh api` shell-out so the import runs on hosts with no gh binary
    (the SnapCI workers). Set paginate=True for list endpoints (e.g. a PR's files) to follow
    pages of 100 until a short page ends the run.
    """
    try:
        if not paginate:
            return _http_get_json(f"{GITHUB_API_BASE}{path}")
        separator = "&" if "?" in path else "?"
        results: list = []
        page = 1
        while True:
            chunk = _http_get_json(
                f"{GITHUB_API_BASE}{path}{separator}per_page=100&page={page}"
            )
            if not isinstance(chunk, list) or not chunk:
                break
            results.extend(chunk)
            if len(chunk) < 100:
                break
            page += 1
        return results
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return None


def get_stale_pr_files(pr_number: str, use_staging: bool) -> Optional[set[str]]:
    """Return the PR's files that its base branch has changed since the PR branched.

    These are the files where the PR carries a stale view of the tree, so importing it has
    to merge rather than take the PR's copy wholesale. Paths come back in internal form.

    Returns None when the comparison cannot be made (no gh, API error), so callers skip the
    check instead of blocking on it. GitHub caps a compare response at 300 files, so a very
    large base-branch delta can under-report.
    """
    repo = "valdi_staging" if use_staging else "Valdi"
    pr_files = get_pr_changed_files(pr_number, use_staging)
    if not pr_files:
        return None

    pr_data = _github_api_json(f"/repos/Snapchat/{repo}/pulls/{pr_number}")
    if not isinstance(pr_data, dict):
        return None
    try:
        base_ref = pr_data["base"]["ref"]
        head_sha = pr_data["head"]["sha"]
    except (KeyError, TypeError):
        return None

    head_compare = _github_api_json(
        f"/repos/Snapchat/{repo}/compare/{base_ref}...{head_sha}"
    )
    if not isinstance(head_compare, dict):
        return None
    merge_base = (
        (head_compare.get("merge_base_commit") or {}).get("sha") or ""
    ).strip()
    if not merge_base:
        return None

    base_compare = _github_api_json(
        f"/repos/Snapchat/{repo}/compare/{merge_base}...{base_ref}"
    )
    if not isinstance(base_compare, dict):
        return None

    moved_on_base = {
        _external_path_to_internal(entry["filename"])
        for entry in (base_compare.get("files") or [])
        if isinstance(entry, dict) and entry.get("filename")
    }
    return pr_files & moved_on_base


def get_pr_author_identity(
    pr_number: str, use_staging: bool
) -> Optional[tuple[str, str]]:
    """Fetch the PR author's git identity (name, email) from the first commit.

    Copybara's pass_thru authoring uses the HEAD commit's git author, which
    is wrong when a maintainer merges the base branch into the PR. This
    function returns the first commit's author as the source of truth.
    """
    repo = "valdi_staging" if use_staging else "Valdi"
    commits = _github_api_json(f"/repos/Snapchat/{repo}/pulls/{pr_number}/commits")
    if not isinstance(commits, list) or not commits:
        return None
    first = commits[0]
    if not isinstance(first, dict):
        return None
    git_author = (first.get("commit") or {}).get("author") or {}
    name = git_author.get("name", "")
    email = git_author.get("email", "")
    return (name, email) if name and email else None


def _create_pr_with_gh(
    git_root: Path, target_branch: str, pr_title: str, body_parts: list[str]
) -> None:
    """Open the internal PR with the gh CLI — the local-maintainer path.

    Unlike `gh api`, `gh pr create` is repo-aware: it targets github.sc-corp.net via the
    checkout's remote, so it needs gh authenticated to GHE. CI has no such auth and passes
    --no-create-pr, opening the PR through pybuild's GHE client instead.
    """
    print("\n────────────────────────────────────────────────────────────────")
    print(" Creating PR")
    print("────────────────────────────────────────────────────────────────")
    try:
        pr_result = subprocess.run(
            [
                "gh",
                "pr",
                "create",
                "--base",
                "master",
                "--head",
                target_branch,
                "--title",
                pr_title,
                "--body",
                "\n".join(body_parts),
            ],
            cwd=git_root,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if pr_result.returncode == 0:
            print(f"{GREEN}✅ PR created: {pr_result.stdout.strip()}{NC}")
            return
        reason = f"gh pr create failed: {pr_result.stderr.strip()}"
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        reason = f"Could not create PR automatically: {exc}"

    print(f"{YELLOW}⚠️  {reason}{NC}")
    compare_url = (
        f"https://github.sc-corp.net/Snapchat/mobile/compare/{target_branch}?expand=1"
    )
    print(f"   Create manually: {compare_url}")
    print(f"\n   Title:  {pr_title}")
    print("\n   Body (copy exactly to preserve attribution labels):")
    for line in body_parts:
        print(f"   {line}" if line else "")


def _write_pr_metadata(
    path: str,
    *,
    branch: str,
    branch_existed: bool,
    pushed: bool,
    title: str,
    body: str,
) -> None:
    """Write the branch name and computed PR fields as JSON for a caller to consume.

    The attribution labels (ORIGINAL_AUTHOR / COPYBARA_AUTHOR / GitOrigin-RevId /
    ExternalPR) stay derived in one place — a caller that opens the PR itself reads them
    from here rather than reconstructing them.

    `pushed` is what tells the caller whether there is anything to review: title and body
    are always populated, including for a re-import onto an existing branch, so that a
    caller can open a fresh PR when the previous one was closed.
    """
    payload = {
        "branch": branch,
        "branch_existed": branch_existed,
        "pushed": pushed,
        "title": title,
        "body": body,
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
    print(f"\n{GREEN}✅ Wrote PR metadata to {path}{NC}")


def run_detect_impersonation(git_root: Path, parent: str, commit: str) -> bool:
    """Return True if validation passed."""
    script = SCRIPT_DIR / "detect_impersonation.py"
    result = subprocess.run(
        [sys.executable, str(script), "--commit-range", f"{parent}..{commit}"],
        cwd=git_root,
        check=False,
    )
    return result.returncode == 0


@contextlib.contextmanager
def copybara_log_file():
    """Yield path to a temp log file; unlink on exit."""
    fd, path = tempfile.mkstemp(suffix=".log")
    os.close(fd)
    try:
        yield path
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(path)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import a PR from open source Valdi to the internal mobile repo",
    )
    parser.add_argument("pr_number", nargs="?", help="PR number to import")
    parser.add_argument(
        "--staging", action="store_true", help="Import from staging repo"
    )
    parser.add_argument("--target-branch", metavar="BRANCH", help="Custom branch name")
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview PR changes without applying"
    )
    parser.add_argument(
        "--repo-timeout",
        metavar="DURATION",
        default="3600s",
        help=(
            "Copybara git fetch/push timeout (default: 3600s). Raise this if the "
            "initial cold fetch of the mobile repo times out on a fresh cache."
        ),
    )
    parser.add_argument(
        "--output-root",
        metavar="DIR",
        default=str(DEFAULT_OUTPUT_ROOT),
        help=(
            "Copybara output root, which holds the bare mirror of the mobile repo "
            f"(default: {DEFAULT_OUTPUT_ROOT}). In CI, point this at a per-run "
            "disposable dir so the mirror never collides with the fixed $HOME path "
            "or the nightly outbound mirror job."
        ),
    )
    parser.add_argument(
        "--no-create-pr",
        action="store_true",
        help=(
            "Push the import branch but do not open the internal PR. CI passes this and "
            "opens the PR through pybuild's GHE client, which is authenticated where the "
            "gh CLI is not."
        ),
    )
    parser.add_argument(
        "--pr-metadata-out",
        metavar="FILE",
        help=(
            "Write the branch name and computed PR title/body to FILE as JSON, so a "
            "caller can open the PR without re-deriving the attribution labels."
        ),
    )
    parser.add_argument(
        "--allow-clobber",
        action="store_true",
        help="Replace files wholesale instead of merging, discarding internal-only changes",
    )
    args = parser.parse_args()

    if not args.pr_number:
        parser.print_help()
        print("\nExamples:")
        print("  import_pr.py 123                    # Import production PR #123")
        print("  import_pr.py 1 --staging            # Import staging PR #1")
        print("  import_pr.py 123 --dry-run          # Preview without applying")
        print(
            "  import_pr.py 123 --repo-timeout 5400s  # Raise fetch timeout for a cold cache"
        )
        print(
            "  import_pr.py 123 --output-root /scratch/copybara-run-42  # Per-run mirror dir (CI)"
        )
        sys.exit(1)

    block_mirroring_in_args(args.pr_number, args.target_branch)
    git_root = get_git_root()
    config = get_config(args.pr_number, args.staging)
    target_branch = args.target_branch or config.default_branch
    # resolve() so a relative --output-root doesn't split between Copybara (run with
    # cwd=config_dir) and the cache read-back / git fetch (run from git_root).
    output_root = Path(args.output_root).expanduser().resolve()
    copybara_cache_dir = output_root / COPYBARA_CACHE_SUBPATH
    copybara_config = SCRIPT_DIR / "copy.bara.sky"

    if not copybara_config.exists():
        print(f"{RED}⚠️  Copybara config not found: {copybara_config}{NC}")
        sys.exit(1)

    # Require clean working tree
    if (
        run(
            ["git", "diff-index", "--quiet", "HEAD", "--"], cwd=git_root, check=False
        ).returncode
        != 0
    ):
        print(
            f"{RED}════════════════════════════════════════════════════════════════{NC}"
        )
        print(f"{RED} ⚠️  Error: You have uncommitted changes{NC}")
        print(
            f"{RED}════════════════════════════════════════════════════════════════{NC}"
        )
        print("\nPlease commit or stash your changes before running this script.")
        print("  git status   /   git stash")
        sys.exit(1)

    current_branch = run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=git_root, capture=True
    ).stdout.strip()

    # Header
    kind = "Staging" if config.use_staging else "Production"
    if args.dry_run:
        title = f"Dry Run: Previewing {kind} PR #{args.pr_number}"
    else:
        title = f"Importing {kind} PR #{args.pr_number}"
    print("════════════════════════════════════════════════════════════════")
    print(f" {title}")
    print("════════════════════════════════════════════════════════════════")
    print(f"\n  Source: {config.source_url} PR #{args.pr_number}")
    if not args.dry_run:
        print(f"  Target: Internal branch '{target_branch}'")
    print()

    # Quoted back verbatim if a merge conflicts, so whoever reads the log (often in CI,
    # where nothing can be resolved) knows exactly what to re-run locally.
    manual_import_command = f"./import_pr.py {args.pr_number}"
    if config.use_staging:
        manual_import_command += " --staging"
    if args.target_branch:
        manual_import_command += f" --target-branch {args.target_branch}"

    # Tell the maintainer up front if the PR is working from a stale tree, since that is
    # what makes an import need to merge rather than simply take the PR's files.
    stale_files = get_stale_pr_files(args.pr_number, config.use_staging)
    if stale_files:
        print("────────────────────────────────────────────────────────────────")
        print(
            f"{YELLOW} ℹ️  The PR branch is behind on {len(stale_files)} file(s) it "
            f"touches:{NC}"
        )
        print("────────────────────────────────────────────────────────────────")
        print()
        for file_path in sorted(stale_files):
            print(f"  {file_path}")
        print()
        print(
            "Those files changed upstream after the PR branched. The import merges its diff\n"
            "rather than overwriting them, and will stop if a merge conflicts. Asking the\n"
            "author to merge the upstream default branch avoids resolving it here."
        )
        print()

    # Git config
    print("────────────────────────────────────────────────────────────────")
    print(" Configuring Git for line ending handling")
    print("────────────────────────────────────────────────────────────────")
    run(["git", "config", "--global", "core.autocrlf", "false"])
    print("✅ Git config set: core.autocrlf = false\n")

    # Build Copybara
    print("────────────────────────────────────────────────────────────────")
    print(" Building Copybara")
    print("────────────────────────────────────────────────────────────────")
    client_dir = git_root / "client"
    run(
        ["bzl", "build", "@valdi_mirroring_bin//:copybara_bin"],
        cwd=client_dir,
        capture=False,
    )
    bazel_bin = run(
        ["bzl", "info", "bazel-bin"], cwd=client_dir, capture=True
    ).stdout.strip()
    copybara_bin = (
        Path(bazel_bin)
        / "external/+snap_dependencies_extension+valdi_mirroring_bin/copybara_bin"
    )
    if not copybara_bin.is_absolute():
        copybara_bin = (client_dir / copybara_bin).resolve()
    print("✅ Copybara built\n")

    # Run Copybara
    print("────────────────────────────────────────────────────────────────")
    print(" Running Copybara to fetch and transform PR")
    print("────────────────────────────────────────────────────────────────")
    config_dir = copybara_config.parent
    config_file = copybara_config.name
    copybara_env = {
        **os.environ,
        "GIT_LFS_SKIP_SMUDGE": "1",
        "GIT_ATTR_NOSYSTEM": "1",
        "GIT_CONFIG_COUNT": "2",
        "GIT_CONFIG_KEY_0": "core.fsync",
        "GIT_CONFIG_VALUE_0": "none",
        "GIT_CONFIG_KEY_1": "core.autocrlf",
        "GIT_CONFIG_VALUE_1": "false",
    }

    with copybara_log_file() as log_path:
        proc = subprocess.Popen(
            [
                str(copybara_bin),
                "migrate",
                config_file,
                config.workflow,
                args.pr_number,
                "--nogit-destination-rebase",
                "--git-no-verify",
                "--ignore-noop",
                f"--repo-timeout={args.repo_timeout}",
                f"--output-root={output_root}",
            ],
            cwd=config_dir,
            env=copybara_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        with open(log_path, "w", encoding="utf-8") as log_f:
            for line in proc.stdout or []:
                print(line, end="")
                log_f.write(line)
        proc.wait()
        if proc.returncode != 0:
            print(
                f"\n{RED}⚠️  Copybara failed!{NC}\nCheck the error above for details."
            )
            sys.exit(1)

        with open(log_path, encoding="utf-8") as f:
            log_content = f.read()

    branch_match = re.search(r"Pushing to.*refs/heads/(\S+)", log_content)
    copybara_branch = branch_match.group(1) if branch_match else None
    push_failed = "remote rejected" in log_content

    if not copybara_branch:
        print(f"\n{RED}⚠️  Could not determine which branch Copybara created{NC}")
        print("The PR may have no changes or already be merged")
        sys.exit(1)

    print()
    if push_failed:
        print(
            f"{YELLOW}⚠️  Copybara created commit locally but push to remote failed{NC}"
        )
        print(
            f"{YELLOW}   Working with local commit instead (common with server-side hook issues){NC}"
        )
    else:
        print(f"{GREEN}✅ Copybara successfully created branch: {copybara_branch}{NC}")
    print()

    if not copybara_cache_dir.is_dir():
        print(f"{RED}⚠️  Could not find Copybara cache directory{NC}")
        print(f"   Expected at: {copybara_cache_dir}")
        sys.exit(1)

    print("────────────────────────────────────────────────────────────────")
    print(" Fetching Copybara commit from local cache")
    print("────────────────────────────────────────────────────────────────")
    run(
        ["git", "fetch", str(copybara_cache_dir), "HEAD"],
        cwd=git_root,
        capture=True,
        check=False,
    )
    rev = run(
        ["git", "rev-parse", "FETCH_HEAD"], cwd=git_root, capture=True, check=False
    )
    copybara_commit = rev.stdout.strip() if rev.returncode == 0 else ""

    if not copybara_commit and not push_failed:
        run(
            ["git", "fetch", "origin", copybara_branch],
            cwd=git_root,
            capture=True,
            check=False,
        )
        rev = run(
            ["git", "rev-parse", "FETCH_HEAD"], cwd=git_root, capture=True, check=False
        )
        copybara_commit = rev.stdout.strip() if rev.returncode == 0 else ""

    if not copybara_commit:
        print(f"{RED}⚠️  Could not find Copybara commit{NC}")
        sys.exit(1)

    parent_rev = run(
        ["git", "rev-parse", f"{copybara_commit}^"],
        cwd=git_root,
        capture=True,
        check=False,
    )
    copybara_parent = parent_rev.stdout.strip() if parent_rev.returncode == 0 else ""
    if not copybara_parent:
        print(f"{RED}⚠️  Could not find parent commit for Copybara commit{NC}")
        sys.exit(1)

    # Impersonation check
    if not run_detect_impersonation(git_root, copybara_parent, copybara_commit):
        print(
            f"\n{RED}════════════════════════════════════════════════════════════════{NC}"
        )
        print(f"{RED} Import BLOCKED: Potential impersonation attempt{NC}")
        print(
            f"{RED}════════════════════════════════════════════════════════════════{NC}"
        )
        print("\nThis commit will NOT be applied to your branch.")
        sys.exit(1)
    print()

    # Files changed in Copybara commit (full diff from staging/production tree).
    # --no-renames splits a rename into its delete and add halves. With rename detection on,
    # git reports only the new path, so the old one never reaches the file list and the
    # import leaves a stale copy behind. No --diff-filter either, so deletes stay visible.
    diff_result = run(
        [
            "git",
            "diff",
            "--name-status",
            "--no-renames",
            copybara_parent,
            copybara_commit,
        ],
        cwd=git_root,
        capture=True,
    )
    names_result = run(
        [
            "git",
            "diff",
            "--name-only",
            "--no-renames",
            copybara_parent,
            copybara_commit,
        ],
        cwd=git_root,
        capture=True,
    )
    all_changed_in_copybara = [
        n for n in names_result.stdout.splitlines() if _is_safe_path(git_root, n)
    ]

    copybara_msg = run(
        ["git", "log", "--format=%B", "-1", copybara_commit], cwd=git_root, capture=True
    ).stdout.strip()
    copybara_author = run(
        ["git", "log", "--format=%an <%ae>", "-1", copybara_commit],
        cwd=git_root,
        capture=True,
    ).stdout.strip()
    git_origin_match = re.search(r"GitOrigin-RevId: (\S+)", copybara_msg, re.MULTILINE)
    git_origin_rev_id = git_origin_match.group(1) if git_origin_match else None
    original_author_match = re.search(
        r"^ORIGINAL_AUTHOR=.+$", copybara_msg, re.MULTILINE
    )

    # Override Copybara's author with the actual PR author from GitHub.
    # Copybara's pass_thru authoring uses the HEAD commit's git author,
    # which is wrong when a maintainer merges the base branch into the PR.
    pr_author_identity = get_pr_author_identity(args.pr_number, config.use_staging)
    if pr_author_identity:
        author_name, author_email = pr_author_identity
        copybara_author = f"{author_name} <{author_email}>"
        original_author_line = f"ORIGINAL_AUTHOR={copybara_author}"
    elif original_author_match:
        original_author_line = original_author_match.group(0)
    else:
        original_author_line = None

    # Fetch external PR metadata (title, author) so the commit message subject
    # uses the proper PR title (the push hook auto-creates the PR from it).
    ext_pr_info = get_external_pr_info(args.pr_number, config.use_staging)

    kind = "staging " if config.use_staging else ""
    title_suffix = f": {ext_pr_info[0]}" if ext_pr_info and ext_pr_info[0] else ""
    import_subject = (
        f"[Client][Valdi] Import {kind}PR #{args.pr_number} "
        f"from {config.source_url}{title_suffix}"
    )
    import_msg_parts = [import_subject, ""]
    if original_author_line:
        import_msg_parts.append(original_author_line)
    if copybara_author:
        import_msg_parts.append(f"COPYBARA_AUTHOR={copybara_author}")
    if git_origin_rev_id:
        import_msg_parts.append(f"GitOrigin-RevId: {git_origin_rev_id}")
    import_msg_parts.append(
        f"ExternalPR: https://{config.source_url}/pull/{args.pr_number}"
    )
    import_msg = "\n".join(import_msg_parts)

    # Computed before the branch fork, so a re-import whose PR was closed still has them
    # available for a caller to open a fresh PR with (--pr-metadata-out reports them).
    pr_title_suffix = f" — {ext_pr_info[0]}" if ext_pr_info and ext_pr_info[0] else ""
    pr_title = (
        f"[Client][Valdi] Import {kind}PR #{args.pr_number} "
        f"from {config.source_url}{pr_title_suffix}"
    )
    ext_url = f"https://{config.source_url}/pull/{args.pr_number}"
    author_line = f" by @{ext_pr_info[1]}" if ext_pr_info and ext_pr_info[1] else ""
    change_desc = (
        ext_pr_info[0]
        if ext_pr_info and ext_pr_info[0]
        else "See external PR for details."
    )
    # PR body uses the repo template format with attribution labels
    # after ### Test Plan so they survive cool-tool's squash commit.
    body_parts = [
        "### Background",
        "",
        f"Import of {ext_url}{author_line}",
        "",
        "### Change",
        "",
        change_desc,
        "",
        "### Test Plan",
        "",
        "Validated by import script security checks.",
        "",
    ]
    if original_author_line:
        body_parts.append(original_author_line)
    if copybara_author:
        body_parts.append(f"COPYBARA_AUTHOR={copybara_author}")
    if git_origin_rev_id:
        body_parts.append(f"GitOrigin-RevId: {git_origin_rev_id}")
    body_parts.append(f"ExternalPR: {ext_url}")
    pr_body = "\n".join(body_parts)

    # Restrict to files actually changed in the external PR (avoids blocking on out-of-date staging tree)
    pr_files_internal = get_pr_changed_files(args.pr_number, config.use_staging)
    if pr_files_internal is not None:
        imported_files = [f for f in all_changed_in_copybara if f in pr_files_internal]
        print(
            f"{GREEN}✅ Found {len(imported_files)} file(s) from PR (of {len(all_changed_in_copybara)} in Copybara diff){NC}\n"
        )
    else:
        imported_files = all_changed_in_copybara
        print(
            f"{GREEN}✅ Found {len(imported_files)} file(s) changed in {OPEN_SOURCE_PREFIX.rstrip('/')}{NC}\n"
        )
        print(
            f"{YELLOW}   (Could not fetch PR file list from GitHub. Run 'gh auth login' "
            "to restrict to PR-touched files only.){NC}\n"
        )

    # Validate no scripts/mirroring references (only in PR-touched files)
    print("────────────────────────────────────────────────────────────────")
    print(" Validating imported files for scripts/mirroring references")
    print("────────────────────────────────────────────────────────────────")
    blocked = collect_blocked_files(
        git_root, copybara_commit, copybara_parent, imported_files, run
    )

    if blocked:
        print(
            f"{RED}════════════════════════════════════════════════════════════════{NC}"
        )
        print(
            f"{RED} Import BLOCKED: References to scripts/mirroring directory detected{NC}"
        )
        print(
            f"{RED}════════════════════════════════════════════════════════════════{NC}"
        )
        print(
            "\nThe following files contain references to scripts/mirroring directory:"
        )
        for f in blocked:
            print(f"  {f}")
        print("This import will NOT be applied.")
        sys.exit(1)

    print(f"{GREEN}✅ No references to scripts/mirroring directory found{NC}\n")

    # Warn if PR touches any dot file or dot folder
    dot_paths = [f for f in imported_files if path_has_dotfile_or_dotfolder(f)]
    if dot_paths:
        print(
            f"{YELLOW}────────────────────────────────────────────────────────────────{NC}"
        )
        print(f"{YELLOW} ⚠️  Warning: PR touches dot file(s) or dot folder(s){NC}")
        print(
            f"{YELLOW}────────────────────────────────────────────────────────────────{NC}"
        )
        print()
        for p in dot_paths:
            print(f"  {p}")
        print()
        print(
            "Please review these changes; dot files are often tooling or local config."
        )
        print()

    # Show changed files (only those in the PR)
    print("════════════════════════════════════════════════════════════════")
    print(
        f" Files modified in {'staging' if config.use_staging else 'production'} PR #{args.pr_number}:"
    )
    print("════════════════════════════════════════════════════════════════")
    imported_set = set(imported_files)
    for line in diff_result.stdout.splitlines():
        if OPEN_SOURCE_PREFIX not in line:
            continue
        # name-status format: "M\tpath", "A\tpath" or "D\tpath"
        path = line.split("\t", 1)[1].strip() if "\t" in line else line.strip()
        if path not in imported_set:
            continue
        line = re.sub(r"^A\s+", "  [ADDED]    ", line)
        line = re.sub(r"^M\s+", "  [MODIFIED] ", line)
        line = re.sub(r"^D\s+", "  [DELETED]  ", line)
        print(line)
    print()

    if args.dry_run:
        print("════════════════════════════════════════════════════════════════")
        print(" Next Steps:")
        print("════════════════════════════════════════════════════════════════")
        print(f"\nThe PR changes are now in the remote branch '{copybara_branch}'")
        print("\nTo import the full PR (creates/updates branch):")
        print(
            f"  {sys.argv[0]} {args.pr_number}"
            + (" --staging" if config.use_staging else "")
        )
        if not push_failed:
            print(
                f"\nTo delete the temp branch: git push origin --delete {copybara_branch}"
            )
        print()
        run(["git", "checkout", current_branch], cwd=git_root, capture=False)
        print(
            f"{GREEN}════════════════════════════════════════════════════════════════{NC}"
        )
        print(f"{GREEN} Dry run completed successfully! 🎉{NC}")
        print(
            f"{GREEN}════════════════════════════════════════════════════════════════{NC}"
        )
        return 0

    target_branch_existed = branch_exists(git_root, target_branch)
    mirror_base = get_mirror_base(git_root)

    # Second impersonation check when updating existing branch
    if target_branch_existed:
        print("────────────────────────────────────────────────────────────────")
        print(" Checking for internal Snapchat email addresses")
        print("────────────────────────────────────────────────────────────────")
        if not run_detect_impersonation(git_root, copybara_parent, copybara_commit):
            print(
                f"\n{RED}════════════════════════════════════════════════════════════════{NC}"
            )
            print(f"{RED} Import BLOCKED: Potential impersonation attempt{NC}")
            print(
                f"{RED}════════════════════════════════════════════════════════════════{NC}"
            )
            sys.exit(1)
        print()

    files_to_update_result = run(
        [
            "git",
            "diff",
            "--name-only",
            "--no-renames",
            copybara_parent,
            copybara_commit,
        ],
        cwd=git_root,
        capture=True,
    )
    pr_filter = set(pr_files_internal) if pr_files_internal is not None else None
    files_to_update = [
        f
        for f in files_to_update_result.stdout.splitlines()
        if _is_safe_path(git_root, f) and (pr_filter is None or f in pr_filter)
    ]

    # Warn if any file we're about to apply is under a dot file/folder (e.g. .github/)
    dot_in_update = [f for f in files_to_update if path_has_dotfile_or_dotfolder(f)]
    if dot_in_update:
        print(
            f"{YELLOW}────────────────────────────────────────────────────────────────{NC}"
        )
        print(
            f"{YELLOW} ⚠️  Warning: The following dot file(s) or dot folder(s) will be applied:{NC}"
        )
        print(
            f"{YELLOW}────────────────────────────────────────────────────────────────{NC}"
        )
        print()
        for p in dot_in_update:
            print(f"  {p}")
        print()
        print(
            "Please review these changes; dot files are often tooling or local config."
        )
        print()

    print("────────────────────────────────────────────────────────────────")
    print(
        f" {'Updating' if target_branch_existed else 'Creating'} branch '{target_branch}'"
    )
    print("────────────────────────────────────────────────────────────────")
    print()

    # True once the import branch has a commit on origin, either path. A caller opening the
    # PR itself needs this: title/body are always set, so they can't signal "nothing landed".
    pushed = False

    if target_branch_existed:
        if current_branch != target_branch:
            print("Checking out existing branch...")
            run(["git", "checkout", target_branch], cwd=git_root, capture=False)
        else:
            print("Already on the target branch...")

        if files_to_update:
            blocked_update = collect_blocked_files(
                git_root, copybara_commit, copybara_parent, files_to_update, run
            )
            if blocked_update:
                print(
                    f"{RED}Import BLOCKED: References to scripts/mirroring directory detected{NC}"
                )
                for f in blocked_update:
                    print(f"  {f}")
                sys.exit(1)
            stage_imported_files(
                git_root,
                copybara_parent,
                copybara_commit,
                files_to_update,
                args.allow_clobber,
                manual_command=manual_import_command,
            )
            commit_cmd = ["git", "commit", "-m", import_msg]
            if copybara_author:
                commit_cmd += ["--author", copybara_author]
            run(commit_cmd, cwd=git_root, capture=False)
            print(f"{GREEN}✅ Updated branch '{target_branch}' with PR changes{NC}")
            print("\n────────────────────────────────────────────────────────────────")
            print(" Pushing updated branch to origin")
            print("────────────────────────────────────────────────────────────────")
            git_user_update = (
                run(
                    ["git", "config", "user.email"],
                    cwd=git_root,
                    capture=True,
                    check=False,
                )
                .stdout.strip()
                .split("@")[0]
            )
            run(
                ["git", "push", "origin", target_branch, "--force"],
                cwd=git_root,
                capture=False,
                env={
                    "PRECOMMIT_BRANCH": target_branch,
                    "PRECOMMIT_USER": git_user_update,
                },
            )
            pushed = True
            print(f"\n{GREEN}✅ Successfully pushed to origin/{target_branch}{NC}")
        else:
            print(
                f"{YELLOW}⚠️  No files to update in {OPEN_SOURCE_PREFIX.rstrip('/')}{NC}"
            )
    else:
        print("Preparing to create new branch...")
        run(["git", "checkout", mirror_base], cwd=git_root, capture=True, check=False)
        run(["git", "reset", "--hard", "HEAD"], cwd=git_root, capture=True, check=False)
        run(["git", "clean", "-fd"], cwd=git_root, capture=True, check=False)
        run(
            ["git", "checkout", "-b", target_branch, mirror_base],
            cwd=git_root,
            capture=False,
        )

        if files_to_update:
            blocked_new = collect_blocked_files(
                git_root, copybara_commit, copybara_parent, files_to_update, run
            )
            if blocked_new:
                print(
                    f"{RED}Import BLOCKED: References to scripts/mirroring directory detected{NC}"
                )
                for f in blocked_new:
                    print(f"  {f}")
                sys.exit(1)
            stage_imported_files(
                git_root,
                copybara_parent,
                copybara_commit,
                files_to_update,
                args.allow_clobber,
                manual_command=manual_import_command,
            )
            commit_cmd = ["git", "commit", "-m", import_msg]
            if copybara_author:
                commit_cmd += ["--author", copybara_author]
            run(commit_cmd, cwd=git_root, capture=False)
            print(
                f"{GREEN}✅ Created branch '{target_branch}' and applied PR changes{NC}"
            )

            print("\n────────────────────────────────────────────────────────────────")
            print(" Pushing branch to origin")
            print("────────────────────────────────────────────────────────────────")
            git_user = (
                run(
                    ["git", "config", "user.email"],
                    cwd=git_root,
                    capture=True,
                    check=False,
                )
                .stdout.strip()
                .split("@")[0]
            )
            run(
                ["git", "push", "origin", target_branch, "--force"],
                cwd=git_root,
                capture=False,
                env={"PRECOMMIT_BRANCH": target_branch, "PRECOMMIT_USER": git_user},
            )
            pushed = True

            if args.no_create_pr:
                print(
                    "\n────────────────────────────────────────────────────────────────"
                )
                print(" Skipping PR creation (--no-create-pr)")
                print(
                    "────────────────────────────────────────────────────────────────"
                )
                print(f"   Branch pushed: {target_branch}")
            else:
                _create_pr_with_gh(git_root, target_branch, pr_title, body_parts)
        else:
            print(
                f"{YELLOW}⚠️  No files to update in {OPEN_SOURCE_PREFIX.rstrip('/')}{NC}"
            )

    if args.pr_metadata_out:
        _write_pr_metadata(
            args.pr_metadata_out,
            branch=target_branch,
            branch_existed=target_branch_existed,
            pushed=pushed,
            title=pr_title,
            body=pr_body,
        )

    # Summary
    print("\n════════════════════════════════════════════════════════════════")
    print(" Next Steps:")
    print("════════════════════════════════════════════════════════════════")
    if target_branch_existed:
        print("\nYour branch has been updated and pushed automatically.")
    else:
        print(
            f"\n  https://github.sc-corp.net/Snapchat/mobile/compare/{target_branch}?expand=1"
        )
    print(f"\n  git log --oneline {target_branch} ^{mirror_base}")
    print(
        f"  git diff {mirror_base} {target_branch} -- {OPEN_SOURCE_PREFIX.rstrip('/')}"
    )
    if not push_failed:
        print(f"\n  git push origin --delete {copybara_branch}")
    else:
        print(
            f"\n{YELLOW}Note: Copybara's push failed; commit was created locally and is in your branch.{NC}"
        )
    print()

    run(["git", "checkout", current_branch], cwd=git_root, capture=False)
    print(
        f"{GREEN}════════════════════════════════════════════════════════════════{NC}"
    )
    print(f"{GREEN} Import completed successfully! 🎉{NC}")
    print(
        f"{GREEN}════════════════════════════════════════════════════════════════{NC}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
