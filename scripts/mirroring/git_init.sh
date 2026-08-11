#!/usr/bin/env bash

GIT_USER_NAME="SnapCI"
GIT_EMAIL="snapci@snapchat.com"

# Test SSH connection
ssh_success=1
set +e
ssh_output=$(ssh -T git@github.com 2>&1)
if echo "$ssh_output" | grep -q "successfully authenticated"; then
    ssh_success=0
fi
set -e
if [ $ssh_success -eq 0 ]; then
    echo "SSH connection to GitHub is successful."
else
    echo "SSH connection to GitHub failed, checking for credentials..."
    if [ -n "$VALDI_GITHUB_KEY" ]; then
        echo "Writing credentials"
        set +x
        echo "$VALDI_GITHUB_KEY" > ~/.ssh/valdi_github.key
        chmod 600 ~/.ssh/valdi_github.key
        
        # Only use ssh-add when not in CI (ssh-agent may not be running in CI)
        if [ -z "$CI" ]; then
            ssh-add ~/.ssh/valdi_github.key 2>/dev/null || true
        fi
        set -x

        echo "" >> ~/.ssh/config
        echo "Host github.com" >> ~/.ssh/config
        echo "    HostName github.com" >> ~/.ssh/config
        echo "    User git" >> ~/.ssh/config
        echo "    IdentityFile ~/.ssh/valdi_github.key" >> ~/.ssh/config
        echo "    IdentitiesOnly yes" >> ~/.ssh/config
        echo "    StrictHostKeyChecking no" >> ~/.ssh/config
        echo "    UserKnownHostsFile /dev/null" >> ~/.ssh/config
        echo "" >> ~/.ssh/config
    fi

    if [ -n "$VALDI_WIDGETS_GITHUB_KEY" ]; then
        echo "Writing credentials"
        set +x
        echo "$VALDI_WIDGETS_GITHUB_KEY" > ~/.ssh/valdi_widgets_github.key
        chmod 600 ~/.ssh/valdi_widgets_github.key
        
        # Only use ssh-add when not in CI (ssh-agent may not be running in CI)
        if [ -z "$CI" ]; then
            ssh-add ~/.ssh/valdi_widgets_github.key 2>/dev/null || true
        fi
        set -x

        echo "" >> ~/.ssh/config
        echo "Host github.com-widgets" >> ~/.ssh/config
        echo "    HostName github.com" >> ~/.ssh/config
        echo "    User git" >> ~/.ssh/config
        echo "    IdentityFile ~/.ssh/valdi_widgets_github.key" >> ~/.ssh/config
        echo "    IdentitiesOnly yes" >> ~/.ssh/config
        echo "    StrictHostKeyChecking no" >> ~/.ssh/config
        echo "    UserKnownHostsFile /dev/null" >> ~/.ssh/config
        echo "" >> ~/.ssh/config
    fi

    cat ~/.ssh/config
fi


if [ -z "$(git config --global --get user.name)" ]; then
  git config --global user.name "$GIT_USER_NAME"
fi

if [ -z "$(git config --global --get user.email)" ]; then
  git config --global user.email "$GIT_EMAIL"
fi