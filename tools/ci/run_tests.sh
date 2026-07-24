#!/usr/bin/env bash

set -eux

(

# Intended to be run from open_source/
cd "$(dirname "$0")/../.."

bzl test //valdi:test_snap_drawing //valdi:test_hermes --test_output=errors
bzl test //valdi:test_layout --test_output=all --test_arg=--gtest_print_time=1

if [[ $(uname) != Linux ]] ; then
    bzl test //valdi:valdi_ios_objc_test
    bzl test //valdi:valdi_ios_swift_test
    bzl test //valdi:valdi_macos_objc_test

    # C++ runtime unit tests (Value, ValueUtils, JavaScriptTypes, etc.), engine-agnostic.
    # External counterpart of the internal ValdiBazelTestStep addition (#115098).
    # macOS-only: on Linux `bzl test` trips a pre-existing static-destructor segfault in
    # gtest's XML writer when linked against valdi_standalone_runtime (all tests pass; only
    # teardown crashes under bzl test). Internal CI works around it by running the binary directly.
    # //valdi:test_integration is intentionally NOT wired — separate pre-existing framework
    # failures (RuntimeFixture async-dispatch assert, remote-component mock fixtures).
    bzl test //valdi:test_runtime --test_output=errors
fi

)
