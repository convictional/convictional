#!/bin/bash
set -euo pipefail

SANDBOX_NAME="convictional-sandbox"
SANDBOX_SSH_CONFIG="$HOME/.lima/$SANDBOX_NAME/ssh.config"

B='\033[1m'
C='\033[36m'
D='\033[2m'
G='\033[32m'
R='\033[0m'

BRANCH="${1:-}"

if [ -z "$BRANCH" ]; then
  echo -e "${B}Sandbox worktrees${R}"
  scripts/sandbox/list_worktrees.sh
  echo ""
  echo -e "${B}What next?${R}"
  echo -e "  ${C}make sandbox_fetch${R} ${D}BRANCH=<name>${R}       ${D}fetch a branch${R}"
  echo -e "  ${C}make sandbox_checkout${R} ${D}BRANCH=<name>${R}    ${D}fetch and check out${R}"
  exit 0
fi

GIT_SSH_COMMAND="ssh -F $SANDBOX_SSH_CONFIG" git fetch "lima-${SANDBOX_NAME}:app" "$BRANCH"

echo -e "${G}${B}✓ Fetched $BRANCH from sandbox${R}"
