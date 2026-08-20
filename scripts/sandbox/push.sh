#!/bin/bash
set -euo pipefail

SANDBOX_NAME="convictional-sandbox"
SANDBOX_SSH_CONFIG="$HOME/.lima/$SANDBOX_NAME/ssh.config"

BRANCH=$(git symbolic-ref --short HEAD)

GIT_SSH_COMMAND="ssh -F $SANDBOX_SSH_CONFIG" git push --force "lima-${SANDBOX_NAME}:repo.git" "$BRANCH:$BRANCH"

echo -e "\033[32m\033[1m✓ Pushed $BRANCH to sandbox ($(git rev-parse --short HEAD))\033[0m"
