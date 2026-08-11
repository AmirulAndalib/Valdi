#!/bin/bash
set -e
set -x

# Define the archives file (Starlark/Bazel format)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARCHIVES_FILE=$SCRIPT_DIR/../../bzl/open_source_archives.bzl

# Use provided repository URL or default to production
REPO_URL="${1:-git@github.com:Snapchat/Valdi.git}"
REPO_DIR="/tmp/Valdi_Github"
BRANCH="${2:-main}"  # Default to main if no branch specified

# Check if required commands are available
for cmd in python3 gsutil unzstd tar git strip; do
    if ! command -v "$cmd" &>/dev/null; then
        echo "Error: $cmd is not installed. Please install $cmd to proceed."
        exit 1
    fi
done

# Function to strip binaries in a directory
strip_binaries() {
    local dir="$1"
    echo "Stripping binaries in $dir..."
    
    # Find and strip executable files (binaries)
    # Only strip files that are actually ELF binaries or Mach-O binaries
    find "$dir" -type f -executable 2>/dev/null | while read -r file; do
        # Check if it's a binary file (not a script)
        if file "$file" | grep -qE "(ELF|Mach-O)" 2>/dev/null; then
            echo "  Stripping: $file"
            strip "$file" 2>/dev/null || echo "  Warning: Could not strip $file"
        fi
    done
}

# Clone the Valdi_external repository
if [ -d "$REPO_DIR" ]; then
    echo "Directory $REPO_DIR already exists. Pulling latest changes..."
    cd "$REPO_DIR"
    git pull origin "$BRANCH"
    cd ..
else
    echo "Cloning repository from $REPO_URL..."
    git clone "$REPO_URL" "$REPO_DIR"
fi

# Change to the cloned repository directory
cd "$REPO_DIR"
git checkout "$BRANCH"

# Create a temporary directory for downloads
TEMP_DIR=$(mktemp -d)

# Extract URLs from the Starlark bzl file (path starts with "src/open_source")
# Use Python parser; Starlark has trailing commas etc. that are not valid JSON
PARSE_SCRIPT="$SCRIPT_DIR/parse_archives.py"
archives=$(python3 "$PARSE_SCRIPT" "$ARCHIVES_FILE")

while IFS='|' read -r path url; do
    # Skip archive that has path 'src/open_source/scripts/mirroring/bin'
    if [[ "$path" == "src/open_source/scripts/mirroring/bin" ]]; then
        continue
    fi

    # Skip compiler_companion binaries
    if [[ "$path" == *"bin/compiler_companion"* ]]; then
        echo "Skipping compiler_companion binaries at path: $path"
        continue
    fi

    # Skip compiler and jscore binaries — these build from source on the public repo
    if [[ "$path" == *"bin/compiler"* ]] || [[ "$path" == *"jscore/libs"* ]]; then
        echo "Skipping $path (builds from source on public repo)"
        continue
    fi

    echo "Processing archive at path: $path"

    # Remove 'src/open_source' prefix from the path
    echo $path
    relative_path="${path#src/open_source/}"
    echo $relative_path

    # Create the directory inside the cloned repo
    mkdir -p "$relative_path"

    # Download the file from GCS to the temporary directory
    filename=$(basename "$url")
    temp_file="$TEMP_DIR/$filename"
    echo "Downloading from $url..."
    gsutil cp "$url" "$temp_file"

    # Check if the file was downloaded
    if [[ ! -f "$temp_file" ]]; then
        echo "Error: Failed to download $url"
        continue
    fi

    # Decompress and extract the file based on its extension
    case "$filename" in
        *.tar.zst)
            echo "Decompressing $filename..."
            unzstd -f "$temp_file" -o "${temp_file%.zst}"
            echo "Extracting ${filename%.zst} to $relative_path..."
            tar -xvf "${temp_file%.zst}" -C "$relative_path"
            rm "${temp_file%.zst}"
            ;;
        *.tar.gz)
            echo "Extracting $filename to $relative_path..."
            tar -xzf "$temp_file" -C "$relative_path"
            ;;
        *.zip)
            echo "Extracting $filename to $relative_path..."
            unzip -o "$temp_file" -d "$relative_path"
            ;;
        *)
            echo "Error: Unsupported file extension for $filename"
            continue
            ;;
    esac

    # Strip binaries in the extracted directory
    strip_binaries "$relative_path"

    # Remove the downloaded file
    rm "$temp_file"

    echo "Finished processing $path"
done <<< "$archives"

# Remove the temporary directory
rm -rf "$TEMP_DIR"

# Add changes to git
echo "Adding changes to git..."
git add .

# Commit the changes
commit_message="Add files from GCS archives"
echo "Committing changes with message: '$commit_message'"
if git commit -m "$commit_message"; then
    # Push the changes to the main branch
    echo "Pushing changes to $BRANCH branch..."
    git push origin "$BRANCH"
else
    echo "No changes to commit, working tree clean"
fi

echo "Script completed successfully."
