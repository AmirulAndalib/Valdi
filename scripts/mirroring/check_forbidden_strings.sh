#!/bin/bash
set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null && pwd )"
ROOT_DIR="$(cd "$SCRIPT_DIR/../../../../../"; pwd)"

# To be expanded as needed
FORBIDDEN_STRINGS=(
    "sc-corp"
    "(^|[^[:alnum:]_])go/"
    "registry.snapchat.com"
    "compile.py"
    "hotreloader.py"
    "phantom"
    "spookey",
    "gs://",
    "livegrep",
    "snapengine",
    ".sc-",
    "everybodysaydance",
    ".internal",
    "bolt"
)

# Needs to be relative to the directory this script is being run from
OPEN_SOURCE_DIR="client/src/open_source"

# Folders that aren't mirrored, relative to open_source, space separated
EXCLUDED_FOLDERS=("scripts/mirroring")
EXCLUDED_FILES=(".bazelrc.internal" "bzl/additional_dependencies.bzl" "bzl/open_source_archives.bzl" "bzl/scripts/bazel_credential_helper.sh")

pushd "$ROOT_DIR"

found_strings=()

# Construct exclude patterns for git diff-tree
exclude_patterns=()
for folder in "${EXCLUDED_FOLDERS[@]}"; do
    exclude_patterns+=("$OPEN_SOURCE_DIR/$folder")
done

# Construct exclude file patterns
exclude_file_patterns=()
for file in "${EXCLUDED_FILES[@]}"; do
    exclude_file_patterns+=("$OPEN_SOURCE_DIR/$file")
done

# Get list of files changed in the current branch within the specified directory, excluding subfolders
changed_files=$(git diff-tree -r --no-commit-id --name-only HEAD origin/master -- "$OPEN_SOURCE_DIR")

if [ -n "$changed_files" ]; then
    while IFS= read -r file; do

        # Ignore excluded directories
        excluded=false
        for exclude in "${exclude_patterns[@]}"; do
            if [[ "$file" =~ "$exclude" ]]; then
                excluded=true
                break
            fi
        done
        
        # Ignore excluded files
        if ! "$excluded"; then
            for exclude_file in "${exclude_file_patterns[@]}"; do
                if [[ "$file" == "$exclude_file" ]]; then
                    excluded=true
                    break
                fi
            done
        fi
        
        if "$excluded"; then
            continue
        fi
        
        for string in "${FORBIDDEN_STRINGS[@]}"; do
            if grep -E "$string" "$file"; then
                found=false
                for found_string in "${found_strings[@]}"; do
                    if [[ "$found_string" == "$string" ]]; then
                        found=true
                        break
                    fi
                done
                if ! "$found"; then
                    echo "Forbidden string, '$string', found in '$file'."
                    found_strings+=("$string")
                fi
            fi
        done
    done <<< "$changed_files"

    if [ ${#found_strings[@]} -eq 0 ]; then
        echo "No forbidden strings found in '$OPEN_SOURCE_DIR' (excluding folders: ${EXCLUDED_FOLDERS[*]}, files: ${EXCLUDED_FILES[*]})."
    else
        echo "Found the following strings in the latest commit within directory '$OPEN_SOURCE_DIR' (excluding folders: ${EXCLUDED_FOLDERS[*]}, files: ${EXCLUDED_FILES[*]}):"
        for found_string in "${found_strings[@]}"; do
            echo "- $found_string"
        done
        # Fail CI
        exit 1
    fi
else
    echo "No files changed in '$OPEN_SOURCE_DIR' (excluding folders: ${EXCLUDED_FOLDERS[*]}, files: ${EXCLUDED_FILES[*]})."
fi

popd
