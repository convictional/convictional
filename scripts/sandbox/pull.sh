#!/bin/bash
set -euo pipefail

SANDBOX_NAME="convictional-sandbox"
SANDBOX_SSH_CONFIG="$HOME/.lima/$SANDBOX_NAME/ssh.config"

BRANCH=$(git symbolic-ref --short HEAD)

GIT_SSH_COMMAND="ssh -F $SANDBOX_SSH_CONFIG" git fetch "lima-${SANDBOX_NAME}:app" "$BRANCH"
git merge FETCH_HEAD

echo -e "\033[32m\033[1m✓ Pulled $BRANCH from sandbox ($(git rev-parse --short HEAD))\033[0m"
