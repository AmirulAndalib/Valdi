#!/usr/bin/env bash
#
# Runs the Valdi compiler's own Swift unit suite (compiler/compiler/Compiler/Tests).
#
# It's an SPM testTarget, invisible to Bazel, so it needs a real `swift` toolchain
# rather than the Bazel rules_swift one. macOS runners (external) and internal cool
# macOS both ship swift via Xcode. Factored into a script so the external
# compiler-tests.yml workflow and the internal cool entry script call the same
# thing — a regression is caught before it mirrors to the public repo.
#
# Caller must be on macOS (or otherwise provide `swift`).
set -euo pipefail

cd "$(dirname "$0")/../.."

if ! command -v swift >/dev/null 2>&1; then
  echo "compiler_tests.sh: no swift toolchain on PATH; skipping." >&2
  exit 0
fi

( cd compiler/compiler/Compiler && swift test --enable-test-discovery )
