#!/usr/bin/env bash
set -x
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Parse command line arguments
INIT_HISTORY_FLAG=""
WORKFLOW="default"

while [[ $# -gt 0 ]]; do
    case $1 in
        --init-history)
            INIT_HISTORY_FLAG="--init-history"
            shift
            ;;
        --workflow)
            WORKFLOW="$2"
            shift 2
            ;;
        --initial-import)
            if [[ "$WORKFLOW" == "staging" ]]; then
                WORKFLOW="staging_initial_import"
            else
                WORKFLOW="initial_import"
            fi
            shift
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

bzl build @valdi_mirroring_bin//:copybara_bin_deploy.jar

GIT_INIT="$SCRIPT_DIR/git_init.sh"
$GIT_INIT

# Configure Copybara
COPYBARA_CONFIG="$SCRIPT_DIR/copy.bara.sky"
echo "Using workflow: $WORKFLOW"

# Determine if this is initial import workflow
if [[ "$WORKFLOW" == "initial_import" || "$WORKFLOW" == "staging_initial_import" ]]; then
    # Initial import mode
    COPYBARA_CMD="java -jar bazel-bin/external/+snap_dependencies_extension+valdi_mirroring_bin/copybara_bin_deploy.jar \
        $INIT_HISTORY_FLAG \
        migrate $COPYBARA_CONFIG $WORKFLOW \
        --force \
        --repo-timeout 1h"
    
    # Run Copybara (will exit on failure due to set -e)
    $COPYBARA_CMD
else
    # Regular mirroring mode
    COPYBARA_CMD="java -jar bazel-bin/external/+snap_dependencies_extension+valdi_mirroring_bin/copybara_bin_deploy.jar \
        $INIT_HISTORY_FLAG \
        migrate $COPYBARA_CONFIG $WORKFLOW \
        --ignore-noop \
        --repo-timeout 2h"
    
    # Run Copybara and handle "no changes" exit code gracefully
    set +e
    $COPYBARA_CMD
    COPYBARA_EXIT=$?
    set -e
    
    # Exit codes 0 (success) and 4 (no changes) are acceptable
    if [ $COPYBARA_EXIT -ne 0 ] && [ $COPYBARA_EXIT -ne 4 ]; then
        echo "Copybara failed with exit code $COPYBARA_EXIT"
        exit $COPYBARA_EXIT
    fi
    
    echo "Copybara completed (exit code: $COPYBARA_EXIT)"

    # Update the valdi-last-mirror tag to track the last successfully mirrored internal commit.
    # import_pr.py uses this tag as the base for import branches.
    git fetch origin master
    git tag -f valdi-last-mirror FETCH_HEAD
    git push origin valdi-last-mirror -f
    echo "Updated valdi-last-mirror tag to $(git rev-parse valdi-last-mirror)"
fi

# The binaries - determine branch based on workflow
if [[ "$WORKFLOW" == "staging_initial_import" || "$WORKFLOW" == "initial_import" ]]; then
    BRANCH="initial"
else
    BRANCH="main"
fi

if [[ "$WORKFLOW" == "staging" || "$WORKFLOW" == "staging_initial_import" ]]; then
    echo "Updating binaries for staging repository (branch: $BRANCH)"
    $SCRIPT_DIR/repo_archiver_update.sh "git@github.com:Snapchat/valdi_staging.git" "$BRANCH"
else
    echo "Updating binaries for production repository (branch: $BRANCH)"
    $SCRIPT_DIR/repo_archiver_update.sh "git@github.com:Snapchat/Valdi.git" "$BRANCH"
fi

