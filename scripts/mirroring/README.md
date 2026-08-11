# Syncing Valdi Open Source and Internal Repos

Valdi is open sourced and hosted on [GitHub](https://github.com/Snapchat/Valdi), but Snapchat maintains the source-of-truth for the codebase within our mobile repo. We use [copybara](https://github.com/google/copybara) to [mirror](https://github.sc-corp.net/Snapchat/mobile/tree/master/client/src/open_source/scripts/mirroring) the open\_source directory from our mobile repo to GitHub. 

## Overview

Copybara is a tool to help migrate code from repo to repo. It understands git commits, authorship, pull requests and more. Copybara workflows specify a source and destination, and build up a working directory of changes to stage across them. Workflows can apply different types of transformations in that working directory, such as renaming files, scrubbing commit messages, and much more.

The mirroring system supports two destinations:
- **Production**: [github.com/Snapchat/Valdi](https://github.com/Snapchat/Valdi) - The official open source repository
- **Staging**: [github.com/Snapchat/valdi_staging](https://github.com/Snapchat/valdi_staging) - Testing repository for validating PR import scripts

> **⚠️ Important**: The staging repository is **only used for testing the PR import scripts**. It is not intended for staging actual Valdi features or releases. Use this repository to validate that the PR import infrastructure works correctly before making changes to the production workflow.

The mirroring scripts can be run from CI or a local machine, provided it has access to both GitHub and GHE. The PR ingestion script should be run locally. The scripts will make a fresh copy of the source and destination repositories. This can be quite slow since that means loading our mobile monorepo. When running locally, Copybara will cache the repository and so subsequent runs are significantly faster.

## Publishing Valdi to GitHub

### Incremental Updates in CI

We mirror Valdi from mobile/open_source to GitHub from our CI pipeline. The system supports both production and staging repositories:

#### Production Mirroring
- **Job**: `mirror_valdi_open_source`
- **Trigger**: Automatic when files under `src/open_source` are modified
- **Schedule**: Nightly at midnight
- **Destination**: [github.com/Snapchat/Valdi](https://github.com/Snapchat/Valdi)
- **Manual Trigger**: `:valdi-mirror-external:` in PR comments

#### Staging Mirroring  
- **Job**: `mirror_valdi_open_source_staging`
- **Schedule**: Nightly at midnight
- **Destination**: [github.com/Snapchat/valdi_staging](https://github.com/Snapchat/valdi_staging)
- **Manual Trigger**: `:valdi-mirror-external-staging:` in PR comments

Note that mirroring does a fresh checkout of both source and destination repositories and so can take some time.

### Authentication

We use SSH key authentication to connect to GitHub repositories. Each repository has its own deploy key configured:

#### Production Repository (github.com/Snapchat/Valdi)
Final key:
**Spookey Secret**: [valdi-final-github](https://spookey.sc-corp.net/#/secret/valdi-final-github)
**Public Key**:
```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIC6e3ReL5uktENLiZTDpDz6zmZ0rGCa64uua1oo/S5gg cholgate@JN6327P4C7
```

##### **OLD DEPRECATED**
- **Spookey Secret**: [valdi-github](https://spookey.sc-corp.net/#/secret/valdi-github)
- **Public Key**:
```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIHjxnaof80K+1IOx+jD5VmClZw7CUJcl699/dHvaqyRr snapci@snapchat.com
```

#### Staging Repository (github.com/Snapchat/valdi_staging)  
- **Spookey Secret**: [valdi_staging-github](https://spookey.sc-corp.net/#/secret/valdi_staging-github)
- **Public Key**:
```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGPxooExE+BBtWb9l++x7A4lGO8MvUb7KEc0wLsvZmiV cholgate@Q250XMQYKW
```

#### Valdi Widgets Repository
- **Spookey Secret**: [valdi-widgets-github](https://spookey.sc-corp.net/#/secret/valdi-widgets-github)  
- **Public Key**:
```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIHCtFD6566a32omXuF/4EM1YLrB3HoiDgGMKB/cMv7hC snapci@snapchat.com
```

Deploy keys must be added to the "Settings → Deploy Keys" section of each respective GitHub repository.

### Initial Imports

Initial imports reset the GitHub repository state and history, creating a fresh tree in the "initial" branch with clean commit history.

#### Production Initial Import
```bash
# Local execution
./src/open_source/scripts/mirroring/mirror.sh --initial-import

# CI trigger
:valdi-initial-import:
```

#### Staging Initial Import  
```bash  
# Local execution
./src/open_source/scripts/mirroring/mirror.sh --workflow staging --initial-import

# CI trigger  
:valdi-initial-import-staging:
```

After an initial import, you can reset the main branch from the initial branch:
```bash
git fetch origin initial
git checkout initial  
git branch -D main
git checkout -b main
git push --force --set-upstream origin main
```

#### Local Usage

The `mirror.sh` script supports several options:

```bash
# Regular mirroring (production)
./mirror.sh

# Regular mirroring (staging)
./mirror.sh --workflow staging

# Initial import (production) 
./mirror.sh --initial-import

# Initial import (staging)
./mirror.sh --workflow staging --initial-import

# With init-history flag
./mirror.sh --init-history --initial-import
```

## Implementation Details

### Configuration Management

The mirroring system uses a single Copybara configuration file (`copy.bara.sky`) with multiple workflows:

- **Production**: Uses workflows `default` and `initial_import` pointing to `git@github.com:Snapchat/Valdi.git`
- **Staging**: Uses workflows `staging` and `staging_initial_import` pointing to `git@github.com:Snapchat/valdi_staging.git`

This approach allows for hardcoded repository URLs in the configuration while supporting both destinations through workflow selection.

### Binary Mirroring

The system mirrors both source code and compiled binaries:

1. **Source Code**: Copybara handles file transformations and git operations
2. **Binaries**: `repo_archiver_update.sh` downloads archives from GCS and commits them to the target repository

The binary archiver automatically uses the correct destination repository and branch based on the `--workflow` flag:
- **Initial import workflows** (`initial_import`, `staging_initial_import`): Use `initial` branch
- **Regular workflows** (`default`, `staging`): Use `main` branch

### Authentication Strategy

- Production jobs use the `valdi-final-github` Spookey secret
- Staging jobs use the `valdi_staging-github` Spookey secret
- Each repository has its own SSH deploy key for security isolation

## Accepting Pull Requests from GitHub

Our mobile repo is the source-of-truth for Valdi, but we'd still like to accept outside contributions that come in from GitHub. We use Copybara workflows and a unified script to sync GitHub PRs to our internal repository.

### Quick Start

**For Production PRs** (from github.com/Snapchat/Valdi):
```bash
cd client/src/open_source/scripts/mirroring/
./import_pr.py <PR_NUMBER>
```

**For Staging PRs** (from github.com/Snapchat/valdi_staging):
```bash
cd client/src/open_source/scripts/mirroring/
./import_pr.py <PR_NUMBER> --staging
```

### Import PR Script

The `import_pr.py` script is a unified tool for importing PRs from both production and staging repositories:

```bash
# Basic usage - creates or updates branch valdi_github_pr_<NUMBER> (production)
./import_pr.py 123

# Staging PR - creates or updates branch valdi_staging_pr_<NUMBER>
./import_pr.py 1 --staging

# Custom branch name
./import_pr.py 123 --target-branch my-custom-branch

# Preview PR changes without applying them
./import_pr.py 123 --dry-run
```

**Options:**
- `<PR_NUMBER>` - Required. The PR number to import
- `--staging` - Import from staging repo instead of production
- `--target-branch BRANCH` - Use custom branch name
- `--dry-run` - Fetch and show PR changes without applying them
- `--allow-clobber` - Replace files wholesale instead of merging (see below)

**How changes are applied:**

The PR's diff is applied as a three-way merge, so internal changes to a file the PR also
touches are preserved. This matters on re-imports: by then the branch usually carries a
`master` merge and maintainer fixups, and the external branch may predate internal work
that has since been mirrored out. Replacing files wholesale would silently revert it.

- Files that changed internally since the PR branched are listed before applying.
- If a merge conflicts, the import stops without committing, and leaves the conflict in the
  working tree so it can be resolved by hand (`git reset --hard HEAD && git clean -fd`
  abandons it). Conflict markers never reach a commit. Either ask the author to merge the
  upstream default branch into their PR and re-run, or resolve it internally.
- `--allow-clobber` restores the old behaviour of taking the PR's version of every file.
  Use it only when the external version really should win; internal-only changes to those
  files are discarded.

Before fetching anything, the script also reports which of the PR's files have moved on
upstream since it branched, so a stale PR can be sent back to its author early.

**What it does:**
1. Configures Git settings to handle line endings correctly (`core.autocrlf = false`)
2. Runs Copybara locally to fetch and transform the PR
3. Creates a new branch if one doesn't exist, or updates existing branch automatically
4. Shows you what changed
5. Switches back to your original branch

**Branch Naming:**
- Production PRs: `valdi_github_pr_<NUMBER>` (e.g., `valdi_github_pr_123`)
- Staging PRs: `valdi_staging_pr_<NUMBER>` (e.g., `valdi_staging_pr_1`)

**After running the script:**
1. The script switches back to your original branch
2. **For new PRs:** You'll need to push and create the PR manually:
   - Push: `git push origin <BRANCH_NAME> --force`
   - Create PR: `https://github.sc-corp.net/Snapchat/mobile/compare/<BRANCH_NAME>?expand=1`
3. **For PR updates:** The script automatically pushes the updated branch, and the existing internal PR is automatically updated
4. Review the changes: `git diff master <BRANCH_NAME> -- client/src/open_source/`

**Note:** With `--dry-run`, the script previews changes without creating or updating a branch. The changes are available in a temporary Copybara branch for inspection.

**Branch Behavior:**
- If the target branch doesn't exist, creates it from the `valdi-last-mirror` tag (the
  commit matching the last outbound mirror, where the internal and public trees agree)
- If the branch already exists, updates it with the latest PR changes
- Only files in `client/src/open_source/` are updated (preserves your other changes)

**When PR Updates:**
When a contributor updates their external PR, simply run the script again with the same PR number:
```bash
./import_pr.py 123              # Update production PR #123
./import_pr.py 1 --staging      # Update staging PR #1
```

The script will:
1. Automatically detect the existing branch
2. Update it with the latest changes from the external PR
3. Automatically push the updated branch to origin
4. The internal PR will be automatically updated (since it tracks the branch)

**Note:** If you have local commits on the branch, they will be preserved - only the PR files in `client/src/open_source/` are updated.

**Previewing Changes:**
Use `--dry-run` to preview PR changes before importing:
```bash
./import_pr.py 123 --dry-run              # Preview production PR
./import_pr.py 1 --staging --dry-run     # Preview staging PR
```
This will fetch and transform the PR, show you what files changed, but won't modify your local branches. Useful for reviewing changes before applying them.

### Workflow Comparison

| Feature | Production | Staging |
|---------|-----------|---------|
| **External Repo** | github.com/Snapchat/Valdi | github.com/Snapchat/valdi_staging |
| **Internal Base** | `master` | `master` |
| **Branch Pattern** | `valdi_github_pr_<N>` | `valdi_staging_pr_<N>` |
| **Script Command** | `./import_pr.py <N>` | `./import_pr.py <N> --staging` |
| **Dry Run** | `./import_pr.py <N> --dry-run` | `./import_pr.py <N> --staging --dry-run` |
| **Copybara Workflow** | `stage_public_pull_request` | `stage_staging_pull_request` |

### Prerequisites

Make sure you have an [SSH key registered](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/adding-a-new-ssh-key-to-your-github-account) with your public GitHub account.

### How It Works

The scripts use Copybara's `stage_public_pull_request` (production) or `stage_staging_pull_request` (staging) workflows to:
1. Fetch the PR from GitHub
2. Transform files (rename special files, move to `client/src/open_source/`, etc.)
3. Create a commit in your local repository
4. Apply the changes to your branch

The scripts handle line ending differences automatically and work around server-side hook issues by using Copybara's local cache when needed.

### Troubleshooting

#### Github API call failed with code 404

This may happen if you don't have a local `~/.git-credentials` file with your public Github credentials. Copybara expects this file to exist in order to perform API requests and just having your public ssh key associated with your public Github account is insufficient.

To generate this file, installing the Github cli tool, `gh`, and signing into it should generate the file for you.

```
brew install gh
gh auth login
```

If this still doesn't work, you can also try running `gh auth login` again and selecting auth with HTTPS.

#### Unexpected file changes

If you wind up with extra files being pulled in due to changed newlines:

```
git config --global core.autocrlf false 
```

And then run `import_pr.py` again.

#### Line ending problems

The script automatically configures Git to handle line endings (`core.autocrlf = false`). If you still see issues:
- Check that the script completed without errors
- Verify your Git version is recent (`git --version`)

#### Copybara shows 88k+ files modified

This means line ending configuration didn't work properly:
- Make sure you're using the `import_pr.py` script
- Check the script output for Git config confirmation messages
- Try cleaning the Copybara cache: `rm -rf ~/.cache/copybara/`

#### Branch already exists

The script automatically updates existing branches. If you want a fresh start:
- Delete the branch: `git branch -D valdi_github_pr_<NUMBER>` (or `valdi_staging_pr_<NUMBER>` for staging)
- Or use `--target-branch` to create a different branch name

#### Authentication issues

If you see SSH authentication errors:
- Ensure you have an SSH key registered with your GitHub account
- Verify you can access the repository: `git ls-remote git@github.com:Snapchat/Valdi.git` (or `valdi_staging.git` for staging)
- Check your SSH config if needed

## Quick Reference

### CI Trigger Commands

| Command | Description | Destination |
|---------|-------------|-------------|
| `:valdi-mirror-external:` | Manual production mirroring | github.com/Snapchat/Valdi |
| `:valdi-mirror-external-staging:` | Manual staging mirroring | github.com/Snapchat/valdi_staging |
| `:valdi-initial-import:` | Production initial import | github.com/Snapchat/Valdi |
| `:valdi-initial-import-staging:` | Staging initial import | github.com/Snapchat/valdi_staging |

### Local Script Usage

```bash
# Production mirroring
./mirror.sh
./mirror.sh --initial-import

# Staging mirroring
./mirror.sh --workflow staging
./mirror.sh --workflow staging --initial-import
```

### Key Files

- `mirror.sh` - Main mirroring script with dynamic configuration
- `copy.bara.sky` - Copybara configuration with hardcoded production and staging workflows
- `repo_archiver_update.sh` - Binary mirroring script
- `import_pr.py` - PR ingestion from GitHub to internal repo
- `detect_impersonation.py` - Validates commits for internal email addresses (@snapchat.com, @snap.com, @c.snap.com)
