"""Tests for import_pr.py helper functions."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from import_pr import (
    OPEN_SOURCE_PREFIX,
    _create_pr_with_gh,
    _external_path_to_internal,
    _github_token,
    _is_safe_path,
    _refs_mirroring,
    _write_pr_metadata,
    apply_files_three_way,
    collect_blocked_files,
    collect_drifted_files,
    get_external_pr_info,
    get_pr_author_identity,
    get_pr_changed_files,
    get_stale_pr_files,
    path_has_dotfile_or_dotfolder,
    run,
    stage_imported_files,
)

# ---------------------------------------------------------------------------
# path_has_dotfile_or_dotfolder
# ---------------------------------------------------------------------------


class TestPathHasDotfileOrDotfolder:
    def test_regular_path(self):
        assert not path_has_dotfile_or_dotfolder("client/src/open_source/README.md")

    def test_dotfile_at_root(self):
        assert path_has_dotfile_or_dotfolder(".gitignore")

    def test_dotfolder(self):
        assert path_has_dotfile_or_dotfolder(".github/workflows/ci.yml")

    def test_dotfile_in_subdirectory(self):
        assert path_has_dotfile_or_dotfolder("client/src/.hidden/file.txt")

    def test_github_prefix(self):
        assert path_has_dotfile_or_dotfolder(".github/CODEOWNERS")

    def test_github_in_middle(self):
        assert path_has_dotfile_or_dotfolder("client/.github/workflows/test.yml")

    def test_dot_and_dotdot_not_flagged(self):
        # Single/double dot path components are not dotfiles
        assert not path_has_dotfile_or_dotfolder("./client/src/file.py")
        assert not path_has_dotfile_or_dotfolder("../client/file.py")

    def test_windows_separator(self):
        assert path_has_dotfile_or_dotfolder(".github\\workflows\\ci.yml")

    def test_deep_nested_normal_path(self):
        assert not path_has_dotfile_or_dotfolder(
            "client/src/open_source/bzl/build_defs.bzl"
        )


# ---------------------------------------------------------------------------
# _external_path_to_internal
# ---------------------------------------------------------------------------


class TestExternalPathToInternal:
    def test_regular_file(self):
        assert (
            _external_path_to_internal("src/foo.ts")
            == f"{OPEN_SOURCE_PREFIX}src/foo.ts"
        )

    def test_gitignore_renamed(self):
        assert (
            _external_path_to_internal(".gitignore")
            == f"{OPEN_SOURCE_PREFIX}.gitignore.copybara"
        )

    def test_gitattributes_renamed(self):
        assert (
            _external_path_to_internal(".gitattributes")
            == f"{OPEN_SOURCE_PREFIX}.gitattributes.copybara"
        )

    def test_readme_renamed(self):
        assert (
            _external_path_to_internal("README.md")
            == f"{OPEN_SOURCE_PREFIX}README.copybara"
        )

    def test_additional_dependencies_renamed(self):
        assert (
            _external_path_to_internal("bzl/additional_dependencies.bzl")
            == f"{OPEN_SOURCE_PREFIX}bzl/additional_dependencies.bzl.copybara"
        )

    def test_windows_backslash_normalized(self):
        result = _external_path_to_internal("src\\foo\\bar.ts")
        assert result == f"{OPEN_SOURCE_PREFIX}src/foo/bar.ts"


# ---------------------------------------------------------------------------
# _refs_mirroring
# ---------------------------------------------------------------------------


class TestRefsMirroring:
    def test_unix_path(self):
        assert _refs_mirroring("scripts/mirroring/import_pr.py")

    def test_windows_path(self):
        assert _refs_mirroring("scripts\\mirroring\\import_pr.py")

    def test_unrelated(self):
        assert not _refs_mirroring("src/components/Button.tsx")

    def test_partial_match(self):
        assert _refs_mirroring("see scripts/mirroring for details")


# ---------------------------------------------------------------------------
# _is_safe_path
# ---------------------------------------------------------------------------


class TestIsSafePath:
    def test_valid_open_source_path(self, tmp_path):
        (tmp_path / "client" / "src" / "open_source" / "src").mkdir(parents=True)
        assert _is_safe_path(tmp_path, "client/src/open_source/src/foo.ts")

    def test_path_traversal_blocked(self, tmp_path):
        assert not _is_safe_path(tmp_path, "client/src/open_source/../../../etc/passwd")

    def test_outside_open_source_blocked(self, tmp_path):
        (tmp_path / "android" / "app").mkdir(parents=True)
        assert not _is_safe_path(tmp_path, "android/app/build.gradle")

    def test_nonexistent_path_still_checked(self, tmp_path):
        # Path doesn't need to exist — just needs to resolve under open_source
        result = _is_safe_path(tmp_path, "client/src/open_source/new_file.ts")
        assert result is True


# ---------------------------------------------------------------------------
# get_external_pr_info
# ---------------------------------------------------------------------------


class TestGetExternalPrInfo:
    def test_returns_title_and_author(self):
        with patch(
            "import_pr._github_api_json",
            return_value={"title": "Fix bug", "user": {"login": "clholgat"}},
        ):
            result = get_external_pr_info("42", use_staging=False)
        assert result == ("Fix bug", "clholgat")

    def test_null_user_returns_empty_author(self):
        with patch(
            "import_pr._github_api_json",
            return_value={"title": "Fix bug", "user": None},
        ):
            result = get_external_pr_info("42", use_staging=False)
        assert result == ("Fix bug", "")

    def test_missing_user_key(self):
        with patch("import_pr._github_api_json", return_value={"title": "Fix bug"}):
            result = get_external_pr_info("42", use_staging=False)
        assert result == ("Fix bug", "")

    def test_api_failure_returns_none(self):
        with patch("import_pr._github_api_json", return_value=None):
            result = get_external_pr_info("42", use_staging=False)
        assert result is None

    def test_non_dict_response_returns_none(self):
        with patch("import_pr._github_api_json", return_value=["unexpected"]):
            result = get_external_pr_info("42", use_staging=False)
        assert result is None

    def test_staging_uses_valdi_staging_repo(self):
        with patch(
            "import_pr._github_api_json",
            return_value={"title": "T", "user": {"login": "u"}},
        ) as api:
            get_external_pr_info("1", use_staging=True)
        assert "valdi_staging" in api.call_args[0][0]

    def test_production_uses_valdi_repo(self):
        with patch(
            "import_pr._github_api_json",
            return_value={"title": "T", "user": {"login": "u"}},
        ) as api:
            get_external_pr_info("1", use_staging=False)
        assert "/Valdi/" in api.call_args[0][0]


# ---------------------------------------------------------------------------
# get_pr_changed_files
# ---------------------------------------------------------------------------


class TestGetPrChangedFiles:
    def test_maps_files_to_internal_paths(self):
        files = [{"filename": "src/foo.ts"}, {"filename": "README.md"}]
        with patch("import_pr._github_api_json", return_value=files):
            result = get_pr_changed_files("1", use_staging=True)
        assert result == {
            f"{OPEN_SOURCE_PREFIX}src/foo.ts",
            f"{OPEN_SOURCE_PREFIX}README.copybara",
        }

    def test_api_failure_returns_none(self):
        with patch("import_pr._github_api_json", return_value=None):
            result = get_pr_changed_files("1", use_staging=False)
        assert result is None

    def test_empty_file_list_returns_none(self):
        with patch("import_pr._github_api_json", return_value=[]):
            result = get_pr_changed_files("1", use_staging=False)
        assert result is None

    def test_rename_keeps_both_paths(self):
        """A renamed file carries filename + previous_filename, so both paths land in the set.

        Without the old path the delete half of the rename is dropped, and the import lands
        the file at both locations.
        """
        files = [
            {"filename": "src/foo.spec.ts", "previous_filename": "test/foo.spec.ts"}
        ]
        with patch("import_pr._github_api_json", return_value=files):
            result = get_pr_changed_files("1", use_staging=False)
        assert result == {
            f"{OPEN_SOURCE_PREFIX}test/foo.spec.ts",
            f"{OPEN_SOURCE_PREFIX}src/foo.spec.ts",
        }

    def test_requests_paginated_files_endpoint(self):
        with patch(
            "import_pr._github_api_json", return_value=[{"filename": "src/foo.ts"}]
        ) as api:
            get_pr_changed_files("1", use_staging=False)
        assert api.call_args[0][0].endswith("/pulls/1/files")
        assert api.call_args.kwargs.get("paginate") is True


# ---------------------------------------------------------------------------
# get_pr_author_identity
# ---------------------------------------------------------------------------


class TestGetPrAuthorIdentity:
    def test_returns_first_commit_author(self):
        commits = [
            {
                "commit": {
                    "author": {
                        "name": "Catalin Miron",
                        "email": "mironcatalin@gmail.com",
                    }
                }
            },
            {
                "commit": {
                    "author": {"name": "Carson Holgate", "email": "clholgat@ncsu.edu"}
                }
            },
        ]
        with patch("import_pr._github_api_json", return_value=commits):
            result = get_pr_author_identity("21", use_staging=False)
        assert result == ("Catalin Miron", "mironcatalin@gmail.com")

    def test_single_commit(self):
        commits = [
            {"commit": {"author": {"name": "Jane Doe", "email": "jane@example.com"}}},
        ]
        with patch("import_pr._github_api_json", return_value=commits):
            result = get_pr_author_identity("42", use_staging=False)
        assert result == ("Jane Doe", "jane@example.com")

    def test_empty_commits_returns_none(self):
        with patch("import_pr._github_api_json", return_value=[]):
            result = get_pr_author_identity("1", use_staging=False)
        assert result is None

    def test_missing_author_fields_returns_none(self):
        commits = [{"commit": {"author": {"name": "", "email": ""}}}]
        with patch("import_pr._github_api_json", return_value=commits):
            result = get_pr_author_identity("1", use_staging=False)
        assert result is None

    def test_null_commit_field_returns_none(self):
        commits = [{"commit": None}]
        with patch("import_pr._github_api_json", return_value=commits):
            result = get_pr_author_identity("1", use_staging=False)
        assert result is None

    def test_api_failure_returns_none(self):
        with patch("import_pr._github_api_json", return_value=None):
            result = get_pr_author_identity("1", use_staging=False)
        assert result is None

    def test_staging_uses_valdi_staging_repo(self):
        commits = [{"commit": {"author": {"name": "A", "email": "a@b.com"}}}]
        with patch("import_pr._github_api_json", return_value=commits) as api:
            get_pr_author_identity("1", use_staging=True)
        assert "valdi_staging" in api.call_args[0][0]

    def test_production_uses_valdi_repo(self):
        commits = [{"commit": {"author": {"name": "A", "email": "a@b.com"}}}]
        with patch("import_pr._github_api_json", return_value=commits) as api:
            get_pr_author_identity("1", use_staging=False)
        assert "/Valdi/" in api.call_args[0][0]


# ---------------------------------------------------------------------------
# collect_blocked_files
# ---------------------------------------------------------------------------


class TestCollectBlockedFiles:
    def _run_fn(self, responses: dict):
        """Return a fake run_fn that returns canned responses keyed by cmd[0:2]."""

        def fake_run(cmd, **kwargs):
            key = tuple(cmd[:3])
            result = MagicMock(spec=subprocess.CompletedProcess)
            result.returncode = 0
            result.stdout = responses.get(key, "")
            return result

        return fake_run

    def test_path_containing_mirroring_blocked(self, tmp_path):
        blocked = collect_blocked_files(
            tmp_path,
            "abc",
            "def",
            ["scripts/mirroring/import_pr.py"],
            self._run_fn({}),
        )
        assert "scripts/mirroring/import_pr.py" in blocked

    def test_diff_containing_mirroring_reference_blocked(self, tmp_path):
        responses = {
            ("git", "diff", "def"): "+# see scripts/mirroring for details",
            ("git", "ls-tree", "-r"): "",
        }
        blocked = collect_blocked_files(
            tmp_path,
            "abc",
            "def",
            ["src/foo.ts"],
            self._run_fn(responses),
        )
        assert "src/foo.ts" in blocked

    def test_clean_file_not_blocked(self, tmp_path):
        responses = {
            ("git", "diff", "def"): "+export const foo = 1;",
            ("git", "ls-tree", "-r"): "",
        }
        blocked = collect_blocked_files(
            tmp_path,
            "abc",
            "def",
            ["src/foo.ts"],
            self._run_fn(responses),
        )
        assert blocked == []

    def test_symlink_to_mirroring_blocked(self, tmp_path):
        responses = {
            ("git", "diff", "def"): "",
            ("git", "ls-tree", "-r"): "120000 blob abc\tsrc/link",
            ("git", "show", "abc:src/link"): "scripts/mirroring/copy.bara.sky",
        }
        blocked = collect_blocked_files(
            tmp_path,
            "abc",
            "def",
            ["src/link"],
            self._run_fn(responses),
        )
        assert any("src/link" in b for b in blocked)


# ---------------------------------------------------------------------------
# import_msg construction (regex extraction from copybara_msg)
# ---------------------------------------------------------------------------


class TestImportMsgConstruction:
    """Test the regex patterns and message construction used in main()."""

    def _build_import_msg(
        self,
        copybara_msg: str,
        source_url: str,
        pr_number: str,
        api_author: tuple[str, str] | None = None,
        ext_pr_title: str = "",
        copybara_author: str = "",
    ):
        """Replicate the import_msg construction logic from main()."""
        git_origin_match = re.search(
            r"GitOrigin-RevId: (\S+)", copybara_msg, re.MULTILINE
        )
        git_origin_rev_id = git_origin_match.group(1) if git_origin_match else None
        original_author_match = re.search(
            r"^ORIGINAL_AUTHOR=.+$", copybara_msg, re.MULTILINE
        )
        if api_author:
            original_author_line = f"ORIGINAL_AUTHOR={api_author[0]} <{api_author[1]}>"
            copybara_author = f"{api_author[0]} <{api_author[1]}>"
        elif original_author_match:
            original_author_line = original_author_match.group(0)
        else:
            original_author_line = None
        title_suffix = f": {ext_pr_title}" if ext_pr_title else ""
        import_subject = (
            f"[Client][Valdi] Import PR #{pr_number} "
            f"from {source_url}{title_suffix}"
        )
        parts = [import_subject, ""]
        if original_author_line:
            parts.append(original_author_line)
        if copybara_author:
            parts.append(f"COPYBARA_AUTHOR={copybara_author}")
        if git_origin_rev_id:
            parts.append(f"GitOrigin-RevId: {git_origin_rev_id}")
        parts.append(f"ExternalPR: https://{source_url}/pull/{pr_number}")
        return "\n".join(parts)

    def test_subject_uses_pr_title_format(self):
        copybara_msg = (
            "Remove test symlink\n\n"
            "ORIGINAL_AUTHOR=Carson Holgate <clholgat@ncsu.edu>\n"
            "GitOrigin-RevId: 000c6a4b8a2a71b4c541b14558a868c083fcde09"
        )
        msg = self._build_import_msg(
            copybara_msg,
            "github.com/Snapchat/valdi_staging",
            "1",
            ext_pr_title="Remove test symlink",
            copybara_author="Carson Holgate <clholgat@ncsu.edu>",
        )
        assert msg.startswith("[Client][Valdi] Import PR #1")
        assert ": Remove test symlink" in msg.splitlines()[0]
        assert "ORIGINAL_AUTHOR=Carson Holgate <clholgat@ncsu.edu>" in msg
        assert "COPYBARA_AUTHOR=Carson Holgate <clholgat@ncsu.edu>" in msg
        assert "GitOrigin-RevId: 000c6a4b8a2a71b4c541b14558a868c083fcde09" in msg
        assert "ExternalPR: https://github.com/Snapchat/valdi_staging/pull/1" in msg

    def test_no_ext_pr_title_omits_suffix(self):
        msg = self._build_import_msg(
            "Some commit with no labels",
            "github.com/Snapchat/valdi_staging",
            "5",
        )
        assert msg.startswith("[Client][Valdi] Import PR #5")
        assert "ExternalPR: https://github.com/Snapchat/valdi_staging/pull/5" in msg

    def test_only_git_origin_no_original_author(self):
        copybara_msg = "Fix typo\n\nGitOrigin-RevId: deadbeef"
        msg = self._build_import_msg(copybara_msg, "github.com/Snapchat/Valdi", "99")
        assert msg.startswith("[Client][Valdi] Import PR #99")
        assert "GitOrigin-RevId: deadbeef" in msg
        assert "ORIGINAL_AUTHOR" not in msg
        assert "ExternalPR: https://github.com/Snapchat/Valdi/pull/99" in msg

    def test_original_author_preserved_verbatim(self):
        copybara_msg = (
            "x\n\nORIGINAL_AUTHOR=Jane Doe <jane@example.com>\nGitOrigin-RevId: abc"
        )
        msg = self._build_import_msg(copybara_msg, "github.com/Snapchat/Valdi", "7")
        assert msg.startswith("[Client][Valdi] Import PR #7")
        assert "ORIGINAL_AUTHOR=Jane Doe <jane@example.com>" in msg

    def test_api_author_overrides_copybara_author(self):
        """When a maintainer merges main into a PR, Copybara picks up the
        merge commit author. The API override should correct it."""
        copybara_msg = (
            "Merge branch 'main' into patch-1\n\n"
            "ORIGINAL_AUTHOR=Carson Holgate <clholgat@ncsu.edu>\n"
            "GitOrigin-RevId: abc123"
        )
        msg = self._build_import_msg(
            copybara_msg,
            "github.com/Snapchat/Valdi",
            "21",
            api_author=("Catalin Miron", "mironcatalin@gmail.com"),
        )
        assert "ORIGINAL_AUTHOR=Catalin Miron <mironcatalin@gmail.com>" in msg
        assert "COPYBARA_AUTHOR=Catalin Miron <mironcatalin@gmail.com>" in msg
        assert "Carson Holgate" not in msg

    def test_api_author_none_falls_back_to_copybara(self):
        copybara_msg = (
            "Fix typo\n\n"
            "ORIGINAL_AUTHOR=Jane Doe <jane@example.com>\n"
            "GitOrigin-RevId: abc"
        )
        msg = self._build_import_msg(
            copybara_msg,
            "github.com/Snapchat/Valdi",
            "7",
            api_author=None,
        )
        assert "ORIGINAL_AUTHOR=Jane Doe <jane@example.com>" in msg

    def test_suggested_body_contains_attribution_labels(self):
        """The PR body must use the PR template format and place attribution
        labels AFTER ### Test Plan so they survive cool-tool's squash."""
        copybara_msg = (
            "Fix\n\n"
            "ORIGINAL_AUTHOR=Alice <alice@example.com>\n"
            "GitOrigin-RevId: cafebabe"
        )
        git_origin_match = re.search(
            r"GitOrigin-RevId: (\S+)", copybara_msg, re.MULTILINE
        )
        git_origin_rev_id = git_origin_match.group(1) if git_origin_match else None
        original_author_match = re.search(
            r"^ORIGINAL_AUTHOR=.+$", copybara_msg, re.MULTILINE
        )
        original_author_line = (
            original_author_match.group(0) if original_author_match else None
        )
        copybara_author = "Alice <alice@example.com>"

        ext_url = "https://github.com/Snapchat/valdi_staging/pull/3"
        body_parts = [
            "### Background",
            "",
            f"Import of {ext_url} by @alice",
            "",
            "### Change",
            "",
            "Fix something",
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

        body = "\n".join(body_parts)
        assert "ORIGINAL_AUTHOR=Alice <alice@example.com>" in body
        assert "COPYBARA_AUTHOR=Alice <alice@example.com>" in body
        assert "GitOrigin-RevId: cafebabe" in body
        assert f"ExternalPR: {ext_url}" in body
        assert "### Background" in body
        test_plan_idx = body.index("### Test Plan")
        assert body.index("ORIGINAL_AUTHOR=") > test_plan_idx
        assert body.index("COPYBARA_AUTHOR=") > test_plan_idx
        assert body.index("ExternalPR:") > test_plan_idx


# ---------------------------------------------------------------------------
# github.com host pinning
# ---------------------------------------------------------------------------


class TestGithubApiTransport:
    """External-PR reads must hit api.github.com over HTTPS and never shell out to gh, which
    is not installed on the SnapCI workers this import runs on. The base is hardcoded so a
    stray GH_HOST can't redirect a read to the internal GHE instance.
    """

    def _json_urlopen(self, payload, captured):
        def fake_urlopen(request, timeout=None):
            captured["url"] = request.full_url
            captured["auth"] = request.get_header("Authorization")
            response = MagicMock()
            response.__enter__.return_value.read.return_value = json.dumps(
                payload
            ).encode()
            return response

        return fake_urlopen

    def test_hits_api_github_com_and_never_shells_out(self):
        captured: dict = {}
        with patch(
            "import_pr.urllib.request.urlopen",
            side_effect=self._json_urlopen(
                {"title": "T", "user": {"login": "u"}}, captured
            ),
        ), patch(
            "import_pr.subprocess.run",
            side_effect=AssertionError("external-PR reads must not shell out to gh"),
        ):
            result = get_external_pr_info("1", use_staging=False)
        assert result == ("T", "u")
        assert captured["url"].startswith(
            "https://api.github.com/repos/Snapchat/Valdi/pulls/1"
        )

    def test_sends_bearer_token_when_present(self):
        captured: dict = {}
        with patch("import_pr._github_token", return_value="sekret"), patch(
            "import_pr.urllib.request.urlopen",
            side_effect=self._json_urlopen({"title": "T"}, captured),
        ):
            get_external_pr_info("1", use_staging=False)
        assert captured["auth"] == "Bearer sekret"

    def test_no_auth_header_without_token(self):
        captured: dict = {}
        with patch("import_pr._github_token", return_value=None), patch(
            "import_pr.urllib.request.urlopen",
            side_effect=self._json_urlopen({"title": "T"}, captured),
        ):
            get_external_pr_info("1", use_staging=False)
        assert captured["auth"] is None


class TestGithubToken:
    def test_prefers_gh_token(self):
        with patch.dict(
            "import_pr.os.environ",
            {"GH_TOKEN": "a", "GITHUB_TOKEN": "b", "GH_API_TOKEN": "c"},
            clear=True,
        ):
            assert _github_token() == "a"

    def test_falls_back_through_the_list(self):
        with patch.dict("import_pr.os.environ", {"GH_API_TOKEN": "c"}, clear=True):
            assert _github_token() == "c"

    def test_none_when_unset(self):
        with patch.dict("import_pr.os.environ", {}, clear=True):
            assert _github_token() is None


# ---------------------------------------------------------------------------
# _write_pr_metadata
# ---------------------------------------------------------------------------


class TestWritePrMetadata:
    """CI reads this file to open the PR, so the attribution labels must survive it."""

    def test_writes_all_fields(self, tmp_path):
        out = tmp_path / "pr_metadata.json"
        body = "\n".join(
            [
                "### Test Plan",
                "",
                "ORIGINAL_AUTHOR=Alice <alice@example.com>",
                "COPYBARA_AUTHOR=Alice <alice@example.com>",
                "GitOrigin-RevId: cafebabe",
                "ExternalPR: https://github.com/Snapchat/Valdi/pull/7",
            ]
        )
        _write_pr_metadata(
            str(out),
            branch="valdi_github_pr_7",
            branch_existed=False,
            pushed=True,
            title="[Client][Valdi] Import PR #7",
            body=body,
        )
        payload = json.loads(out.read_text())
        assert payload["branch"] == "valdi_github_pr_7"
        assert payload["branch_existed"] is False
        assert payload["title"] == "[Client][Valdi] Import PR #7"
        # Labels must round-trip byte-for-byte, newlines included.
        assert payload["body"] == body
        assert "ORIGINAL_AUTHOR=Alice <alice@example.com>" in payload["body"]
        assert "GitOrigin-RevId: cafebabe" in payload["body"]

    def test_existing_branch_still_carries_title_and_body(self, tmp_path):
        # Re-import: the PR may have been closed, so a caller still needs these to open one.
        out = tmp_path / "pr_metadata.json"
        _write_pr_metadata(
            str(out),
            branch="valdi_staging_pr_38",
            branch_existed=True,
            pushed=True,
            title="[Client][Valdi] Import staging PR #38",
            body="### Background\n\nImport of ...",
        )
        payload = json.loads(out.read_text())
        assert payload["branch_existed"] is True
        assert payload["pushed"] is True
        assert payload["title"] == "[Client][Valdi] Import staging PR #38"
        assert payload["body"].startswith("### Background")

    def test_nothing_pushed_is_reported(self, tmp_path):
        # Nothing to apply: title/body are still set, so `pushed` is the only signal.
        out = tmp_path / "pr_metadata.json"
        _write_pr_metadata(
            str(out),
            branch="valdi_github_pr_9",
            branch_existed=False,
            pushed=False,
            title="[Client][Valdi] Import PR #9",
            body="body",
        )
        payload = json.loads(out.read_text())
        assert payload["pushed"] is False
        assert payload["title"]


# ---------------------------------------------------------------------------
# _create_pr_with_gh
# ---------------------------------------------------------------------------


class TestCreatePrWithGh:
    """The local path. gh pr create is repo-aware, so it needs no --hostname pin."""

    def _make_result(self, returncode, stdout="", stderr=""):
        result = MagicMock(spec=subprocess.CompletedProcess)
        result.returncode = returncode
        result.stdout = stdout
        result.stderr = stderr
        return result

    def test_invokes_gh_pr_create_with_title_and_body(self):
        body_parts = ["### Background", "", "ExternalPR: https://x/pull/1"]
        with patch("import_pr.subprocess.run") as mock_run:
            mock_run.return_value = self._make_result(0, "https://ghe/pull/9")
            _create_pr_with_gh(Path("/repo"), "valdi_github_pr_1", "Title", body_parts)
            cmd = mock_run.call_args[0][0]
        assert cmd[:3] == ["gh", "pr", "create"]
        assert cmd[cmd.index("--base") + 1] == "master"
        assert cmd[cmd.index("--head") + 1] == "valdi_github_pr_1"
        assert cmd[cmd.index("--title") + 1] == "Title"
        assert cmd[cmd.index("--body") + 1] == "\n".join(body_parts)

    def test_failure_falls_back_without_raising(self, capsys):
        with patch("import_pr.subprocess.run") as mock_run:
            mock_run.return_value = self._make_result(1, stderr="no auth for GHE")
            _create_pr_with_gh(Path("/repo"), "valdi_github_pr_1", "Title", ["body"])
        out = capsys.readouterr().out
        assert "gh pr create failed" in out
        # The maintainer needs the compare URL and the body to finish by hand.
        assert "compare/valdi_github_pr_1?expand=1" in out
        assert "body" in out

    def test_missing_gh_binary_falls_back_without_raising(self, capsys):
        with patch("import_pr.subprocess.run", side_effect=FileNotFoundError("gh")):
            _create_pr_with_gh(Path("/repo"), "valdi_github_pr_1", "Title", ["body"])
        out = capsys.readouterr().out
        assert "Could not create PR automatically" in out
        assert "compare/valdi_github_pr_1?expand=1" in out


# Applying an import without reverting internal changes
# ---------------------------------------------------------------------------

BUILD_PATH = f"{OPEN_SOURCE_PREFIX}valdi/BUILD.bazel"

# The external tree the PR branched from.
BASE_BUILD = """\
target(
    name = "valdi_java",
)

target(
    name = "valdi_android_support",
)
"""

# What the PR itself changes: one added dep.
EXTERNAL_BUILD = """\
target(
    name = "valdi_java",
    deps = ["//valdi_standalone"],
)

target(
    name = "valdi_android_support",
)
"""

# A target added internally after the PR branched, which must survive the import.
INTERNAL_ONLY_TARGET = """\

target(
    name = "valdi_android_test_support",
)
"""


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "core.hooksPath=/dev/null",
            *args,
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )


def _write(repo: Path, rel_path: str, contents: str) -> None:
    target = repo / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(contents, encoding="utf-8")


def _commit_all(repo: Path, message: str) -> str:
    _git(repo, "add", "--all")
    _git(repo, "commit", "-m", message)
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


@pytest.fixture(name="import_repo")
def import_repo_fixture(tmp_path):
    """Build a repo shaped like a re-import.

    Returns (repo, parent, commit): `parent` is the external base, `commit` is Copybara's
    version of the PR, and HEAD carries an internal-only change on top of the same base --
    the situation a master merge into the import branch creates.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "--quiet", "-b", "main")

    _write(repo, BUILD_PATH, BASE_BUILD)
    parent = _commit_all(repo, "external base")

    # Copybara's commit: the PR's content on top of the base it branched from.
    _git(repo, "checkout", "--quiet", "-b", "copybara", parent)
    _write(repo, BUILD_PATH, EXTERNAL_BUILD)
    commit = _commit_all(repo, "copybara import")

    # The internal branch moves on independently.
    _git(repo, "checkout", "--quiet", "main")
    _write(repo, BUILD_PATH, BASE_BUILD + INTERNAL_ONLY_TARGET)
    _commit_all(repo, "internal: add test support target")

    return repo, parent, commit


def _stage_with_pr_deletion(repo: Path, allow_clobber: bool) -> None:
    """Run stage_imported_files on a PR that deletes a file, and assert the deletion lands.

    The file is present in the external base and internally, and deleted by the PR, so both
    the merge path and --allow-clobber have to carry the deletion through to the index.
    """
    doomed_path = f"{OPEN_SOURCE_PREFIX}valdi/Doomed.ts"

    _git(repo, "checkout", "--quiet", "-B", "deletion-base", "HEAD")
    _write(repo, doomed_path, "export const doomed = true;\n")
    base = _commit_all(repo, "external base with doomed file")

    _git(repo, "checkout", "--quiet", "-b", "copybara-delete", base)
    (repo / doomed_path).unlink()
    commit = _commit_all(repo, "copybara: delete file")

    _git(repo, "checkout", "--quiet", "-B", "internal-delete", base)

    stage_imported_files(
        repo, base, commit, [BUILD_PATH, doomed_path], allow_clobber, run
    )

    assert not (repo / doomed_path).exists()
    staged = _git(repo, "diff", "--cached", "--name-status").stdout.split()
    assert "D" in staged and doomed_path in staged


class TestCollectDriftedFiles:
    def test_reports_file_changed_internally(self, import_repo):
        repo, parent, _ = import_repo
        assert collect_drifted_files(repo, parent, [BUILD_PATH], run) == [BUILD_PATH]

    def test_ignores_file_matching_the_external_base(self, import_repo):
        repo, parent, _ = import_repo
        _write(repo, BUILD_PATH, BASE_BUILD)
        _commit_all(repo, "internal: revert to base")
        assert collect_drifted_files(repo, parent, [BUILD_PATH], run) == []

    def test_ignores_file_absent_on_one_side(self, import_repo):
        repo, parent, _ = import_repo
        new_path = f"{OPEN_SOURCE_PREFIX}valdi/NEW.bazel"
        assert collect_drifted_files(repo, parent, [new_path], run) == []


class TestApplyFilesThreeWay:
    def test_keeps_internal_changes_while_applying_the_pr(self, import_repo):
        repo, parent, commit = import_repo

        assert apply_files_three_way(repo, parent, commit, [BUILD_PATH], run) == []

        merged = (repo / BUILD_PATH).read_text(encoding="utf-8")
        # The PR's change landed...
        assert '"//valdi_standalone"' in merged
        # ...and the internally-added target was not reverted.
        assert "valdi_android_test_support" in merged
        assert "<<<<<<<" not in merged

        staged = _git(repo, "diff", "--cached", "--name-only").stdout.split()
        assert staged == [BUILD_PATH]

    def test_applies_cleanly_when_there_is_no_internal_drift(self, import_repo):
        repo, parent, commit = import_repo
        _write(repo, BUILD_PATH, BASE_BUILD)
        _commit_all(repo, "internal: revert to base")

        assert apply_files_three_way(repo, parent, commit, [BUILD_PATH], run) == []
        assert (repo / BUILD_PATH).read_text(encoding="utf-8") == EXTERNAL_BUILD

    def test_applies_a_new_file(self, import_repo):
        repo, parent, _ = import_repo
        added_path = f"{OPEN_SOURCE_PREFIX}valdi/Added.ts"
        _git(repo, "checkout", "--quiet", "copybara")
        _write(repo, added_path, "export const added = true;\n")
        commit = _commit_all(repo, "copybara: add file")
        _git(repo, "checkout", "--quiet", "main")

        assert apply_files_three_way(repo, parent, commit, [added_path], run) == []
        assert (repo / added_path).exists()

    def test_applies_a_deletion(self, import_repo):
        repo, parent, _ = import_repo
        doomed_path = f"{OPEN_SOURCE_PREFIX}valdi/Doomed.ts"

        # Present in the base, so both sides start with it.
        _git(repo, "checkout", "--quiet", parent)
        _write(repo, doomed_path, "export const doomed = true;\n")
        base_with_file = _commit_all(repo, "external base with doomed file")
        _git(repo, "checkout", "--quiet", "-b", "copybara-delete", base_with_file)
        (repo / doomed_path).unlink()
        commit = _commit_all(repo, "copybara: delete file")
        _git(repo, "checkout", "--quiet", "-B", "internal-delete", base_with_file)

        assert (
            apply_files_three_way(repo, base_with_file, commit, [doomed_path], run)
            == []
        )
        assert not (repo / doomed_path).exists()

    def test_reports_conflict_and_leaves_it_for_a_human(self, import_repo):
        repo, parent, commit = import_repo
        # Touch the very line the PR changes, so the merge cannot resolve it.
        conflicting = BASE_BUILD.replace(
            'name = "valdi_java",',
            'name = "valdi_java",\n    deps = ["//internal_only"],',
        )
        _write(repo, BUILD_PATH, conflicting)
        _commit_all(repo, "internal: edit the same target")

        assert apply_files_three_way(repo, parent, commit, [BUILD_PATH], run) == [
            BUILD_PATH
        ]

        # The conflict is resolvable by hand: markers in the tree, path unmerged in the index.
        assert "<<<<<<<" in (repo / BUILD_PATH).read_text(encoding="utf-8")
        unmerged = _git(repo, "diff", "--name-only", "--diff-filter=U").stdout.split()
        assert unmerged == [BUILD_PATH]

    def test_conflict_alongside_an_added_file_still_leaves_the_markers(
        self, import_repo
    ):
        """A path the PR adds must not derail the conflict handling.

        `git checkout HEAD -- <paths>` aborts wholesale on a path absent from HEAD, so a
        rollback here used to restore nothing and leave a half-applied tree.
        """
        repo, parent, _ = import_repo
        added_path = f"{OPEN_SOURCE_PREFIX}valdi/Added.ts"
        _git(repo, "checkout", "--quiet", "copybara")
        _write(repo, added_path, "export const added = true;\n")
        commit = _commit_all(repo, "copybara: add file")
        _git(repo, "checkout", "--quiet", "main")

        conflicting = BASE_BUILD.replace(
            'name = "valdi_java",',
            'name = "valdi_java",\n    deps = ["//internal_only"],',
        )
        _write(repo, BUILD_PATH, conflicting)
        _commit_all(repo, "internal: edit the same target")

        conflicts = apply_files_three_way(
            repo, parent, commit, [BUILD_PATH, added_path], run
        )

        assert conflicts == [BUILD_PATH]
        assert "<<<<<<<" in (repo / BUILD_PATH).read_text(encoding="utf-8")


class TestStageImportedFiles:
    def test_preserves_internal_changes_by_default(self, import_repo, capsys):
        repo, parent, commit = import_repo

        stage_imported_files(repo, parent, commit, [BUILD_PATH], False, run)

        merged = (repo / BUILD_PATH).read_text(encoding="utf-8")
        assert "valdi_android_test_support" in merged
        assert '"//valdi_standalone"' in merged
        # The maintainer is told the file had diverged.
        assert BUILD_PATH in capsys.readouterr().out

    def test_allow_clobber_takes_the_external_version(self, import_repo):
        repo, parent, commit = import_repo

        stage_imported_files(repo, parent, commit, [BUILD_PATH], True, run)

        assert (repo / BUILD_PATH).read_text(encoding="utf-8") == EXTERNAL_BUILD

    def test_exits_on_conflict(self, import_repo):
        repo, parent, commit = import_repo
        conflicting = BASE_BUILD.replace(
            'name = "valdi_java",',
            'name = "valdi_java",\n    deps = ["//internal_only"],',
        )
        _write(repo, BUILD_PATH, conflicting)
        head_before = _commit_all(repo, "internal: edit the same target")

        with pytest.raises(SystemExit) as excinfo:
            stage_imported_files(repo, parent, commit, [BUILD_PATH], False, run)

        assert excinfo.value.code == 1
        # Exiting before the commit is what keeps markers out of history.
        assert _git(repo, "rev-parse", "HEAD").stdout.strip() == head_before

    def test_applies_a_deletion_without_failing_the_add(self, import_repo):
        """A PR that deletes a file must not abort the import.

        The merge stages the deletion, which leaves the path unmatchable by `git add` -- and
        that used to fail the whole command with a pathspec error.
        """
        repo, _, _ = import_repo
        _stage_with_pr_deletion(repo, allow_clobber=False)

    def test_allow_clobber_propagates_a_deletion(self, import_repo):
        repo, _, _ = import_repo
        _stage_with_pr_deletion(repo, allow_clobber=True)

    def test_applies_a_rename_as_add_plus_delete(self, import_repo):
        """A renamed file must not land at both paths.

        The old path only reaches here because get_pr_changed_files collects
        previous_filename and the copybara diffs pass --no-renames; the file list is built
        the same way main() builds it, so dropping either one puts the duplicate back.
        Importing Valdi #134 landed the add with no matching delete, which left a stale copy
        that defeated the move the PR was making.

        Test structure from bcollins's #118114.
        """
        repo, _, _ = import_repo
        old_path = f"{OPEN_SOURCE_PREFIX}valdi/src/Moved.ts"
        new_path = f"{OPEN_SOURCE_PREFIX}valdi/test/Moved.ts"

        _git(repo, "checkout", "--quiet", "-B", "rename-base", "HEAD")
        # Back to the external base content, so the internal commit below is a real delta.
        _write(repo, BUILD_PATH, BASE_BUILD)
        _write(repo, old_path, "export const moved = true;\n")
        base = _commit_all(repo, "external base with the file in src")

        _git(repo, "checkout", "--quiet", "-b", "copybara-rename", base)
        (repo / new_path).parent.mkdir(parents=True, exist_ok=True)
        _git(repo, "mv", old_path, new_path)
        commit = _commit_all(repo, "copybara: move the file to test")

        # Internal side moves on independently, so the merge model is exercised too.
        _git(repo, "checkout", "--quiet", "-B", "internal-rename", base)
        _write(repo, BUILD_PATH, BASE_BUILD + INTERNAL_ONLY_TARGET)
        _commit_all(repo, "internal: add test support target")

        # Exactly what main() computes: a --no-renames diff intersected with the PR's files,
        # where the PR set now carries previous_filename alongside filename.
        changed = _git(
            repo, "diff", "--name-only", "--no-renames", base, commit
        ).stdout.split()
        pr_files = {new_path, old_path}
        file_paths = [f for f in changed if f in pr_files]
        assert old_path in file_paths

        stage_imported_files(repo, base, commit, file_paths, False, run)

        assert not (repo / old_path).exists(), "stale copy left at the old path"
        assert (repo / new_path).exists()
        # --no-renames here too: the check is that both halves are staged, and rename
        # detection would collapse them into a single R line that hides a missing delete.
        staged = _git(repo, "diff", "--cached", "--name-status", "--no-renames").stdout
        assert f"D\t{old_path}" in staged
        assert f"A\t{new_path}" in staged
        # The internal-only target must survive the same import.
        assert "valdi_android_test_support" in (repo / BUILD_PATH).read_text(
            encoding="utf-8"
        )

    def test_allow_clobber_takes_a_new_file(self, import_repo):
        repo, parent, _ = import_repo
        added_path = f"{OPEN_SOURCE_PREFIX}valdi/Added.ts"
        _git(repo, "checkout", "--quiet", "copybara")
        _write(repo, added_path, "export const added = true;\n")
        commit = _commit_all(repo, "copybara: add file")
        _git(repo, "checkout", "--quiet", "main")

        stage_imported_files(repo, parent, commit, [BUILD_PATH, added_path], True, run)

        assert (repo / added_path).exists()
        staged = _git(repo, "diff", "--cached", "--name-only").stdout.split()
        assert added_path in staged

    def test_conflict_hands_off_to_a_manual_run(self, import_repo, capsys):
        repo, parent, commit = import_repo
        conflicting = BASE_BUILD.replace(
            'name = "valdi_java",',
            'name = "valdi_java",\n    deps = ["//internal_only"],',
        )
        _write(repo, BUILD_PATH, conflicting)
        _commit_all(repo, "internal: edit the same target")

        with pytest.raises(SystemExit):
            stage_imported_files(
                repo,
                parent,
                commit,
                [BUILD_PATH],
                False,
                run,
                manual_command="./import_pr.py 122",
            )

        out = capsys.readouterr().out
        assert "./import_pr.py 122" in out
        # The handoff has to say where the conflict is, and how to walk away from it.
        assert "left in the working tree" in out
        assert "git reset --hard HEAD" in out


# ---------------------------------------------------------------------------
# get_stale_pr_files
# ---------------------------------------------------------------------------


class TestGetStalePrFiles:
    _PR_DATA = {"base": {"ref": "main"}, "head": {"sha": "headsha"}}

    def _responses(self, pr_files, base_files, merge_base="mergebasesha"):
        """The four api.github.com calls the helper makes, in order: PR files, PR, then the
        head- and base-compares."""
        return [
            pr_files,
            self._PR_DATA,
            {"merge_base_commit": {"sha": merge_base}},
            {"files": base_files},
        ]

    def test_reports_overlapping_files(self):
        with patch("import_pr._github_api_json") as api:
            api.side_effect = self._responses(
                pr_files=[
                    {"filename": "valdi/BUILD.bazel"},
                    {"filename": "src/only_in_pr.ts"},
                ],
                base_files=[
                    {"filename": "valdi/BUILD.bazel"},
                    {"filename": "src/only_on_main.ts"},
                ],
            )
            result = get_stale_pr_files("122", use_staging=False)
        assert result == {f"{OPEN_SOURCE_PREFIX}valdi/BUILD.bazel"}

    def test_returns_empty_when_pr_is_current(self):
        with patch("import_pr._github_api_json") as api:
            api.side_effect = self._responses(
                pr_files=[{"filename": "valdi/BUILD.bazel"}],
                base_files=[{"filename": "docs/unrelated.md"}],
            )
            result = get_stale_pr_files("122", use_staging=False)
        assert result == set()

    def test_applies_rename_mapping_to_both_sides(self):
        with patch("import_pr._github_api_json") as api:
            api.side_effect = self._responses(
                pr_files=[{"filename": "README.md"}],
                base_files=[{"filename": "README.md"}],
            )
            result = get_stale_pr_files("122", use_staging=False)
        assert result == {f"{OPEN_SOURCE_PREFIX}README.copybara"}

    def test_no_pr_files_returns_none(self):
        with patch("import_pr._github_api_json", return_value=[]):
            assert get_stale_pr_files("122", use_staging=False) is None

    def test_pr_lookup_failure_returns_none(self):
        with patch("import_pr._github_api_json") as api:
            api.side_effect = [[{"filename": "valdi/BUILD.bazel"}], None]
            assert get_stale_pr_files("122", use_staging=False) is None

    def test_malformed_pr_response_returns_none(self):
        with patch("import_pr._github_api_json") as api:
            api.side_effect = [[{"filename": "valdi/BUILD.bazel"}], ["unexpected"]]
            assert get_stale_pr_files("122", use_staging=False) is None

    def test_empty_merge_base_returns_none(self):
        with patch("import_pr._github_api_json") as api:
            api.side_effect = [
                [{"filename": "valdi/BUILD.bazel"}],
                self._PR_DATA,
                {"merge_base_commit": {"sha": ""}},
            ]
            assert get_stale_pr_files("122", use_staging=False) is None

    def test_staging_uses_staging_repo(self):
        with patch("import_pr._github_api_json") as api:
            api.side_effect = self._responses(
                pr_files=[{"filename": "valdi/BUILD.bazel"}],
                base_files=[{"filename": "valdi/BUILD.bazel"}],
            )
            get_stale_pr_files("7", use_staging=True)
        called_paths = " ".join(call.args[0] for call in api.call_args_list)
        assert "valdi_staging" in called_paths
        assert "Snapchat/Valdi/" not in called_paths
