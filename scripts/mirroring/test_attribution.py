"""
Regression tests for preserve_attribution() in attribution.bara.sky.

These build the real Copybara binary and run attribution_test_cases.bara.sky
through it, rather than reimplementing the parsing logic in Python. A Python
port would hide the exact class of bug this guards against: Starlark's
split() requires an explicit separator, unlike Python's default
whitespace-split. That mismatch is what crashed the 2026-07-08 nightly mirror
(SnapCI pipeline 7fa07f85-bed5-44fc-ba52-95514e6307f0) when cool-tool's squash
merge collapsed commit-message labels onto a single line and the fallback
label parser hit `rest.split()` with no separator.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

MIRRORING_DIR = Path(__file__).resolve().parent
CLIENT_ROOT = MIRRORING_DIR.parents[3]  # .../client
COPYBARA_JAR_TARGET = "@valdi_mirroring_bin//:copybara_bin_deploy.jar"
# Matches the path mirror.sh itself invokes after `bzl build` of the same target.
COPYBARA_JAR_PATH = (
    CLIENT_ROOT
    / "bazel-bin/external/+snap_dependencies_extension+valdi_mirroring_bin/copybara_bin_deploy.jar"
)


@pytest.fixture(scope="session")
def copybara_jar() -> Path:
    """Build (or reuse the cached build of) the real Copybara binary."""
    result = subprocess.run(
        ["bzl", "build", COPYBARA_JAR_TARGET],
        cwd=CLIENT_ROOT,
        capture_output=True,
        text=True,
        timeout=600,
    )
    if result.returncode != 0:
        pytest.fail(f"Failed to build {COPYBARA_JAR_TARGET}:\n{result.stdout}\n{result.stderr}")
    if not COPYBARA_JAR_PATH.exists():
        pytest.fail(f"Expected jar not found at {COPYBARA_JAR_PATH} after build")
    return COPYBARA_JAR_PATH


@pytest.fixture()
def attribution_test_config(tmp_path: Path) -> Path:
    """Copy attribution.bara.sky + its test cases into a temp dir as copy.bara.sky.

    Copybara requires the file passed on the command line to be literally
    named copy.bara.sky; load()ed dependency modules (attribution.bara.sky)
    can have any name. This mirrors how the real copy.bara.sky loads it.
    """
    shutil.copy(MIRRORING_DIR / "attribution.bara.sky", tmp_path / "attribution.bara.sky")
    shutil.copy(MIRRORING_DIR / "attribution_test_cases.bara.sky", tmp_path / "copy.bara.sky")
    return tmp_path / "copy.bara.sky"


class TestPreserveAttribution:
    """Runs attribution_test_cases.bara.sky's assertions through the real Copybara binary.

    `copybara info` loads the config and evaluates all top-level statements
    (which is where attribution_test_cases.bara.sky's assertions live) before
    printing anything — a failed assertion's fail() call aborts loading with
    a non-zero exit and a visible traceback; success exits 0.
    """

    def test_all_cases_pass(self, copybara_jar: Path, attribution_test_config: Path) -> None:
        result = subprocess.run(
            [
                "java",
                "-jar",
                str(copybara_jar),
                "info",
                "--config-root",
                str(attribution_test_config.parent),
                str(attribution_test_config),
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, (
            "preserve_attribution() regression case failed under the real Copybara "
            f"Starlark engine:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
