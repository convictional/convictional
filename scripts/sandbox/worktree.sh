#!/bin/bash
set -euo pipefail

SANDBOX_NAME="convictional-sandbox"
SANDBOX_SSH_CONFIG="$HOME/.lima/$SANDBOX_NAME/ssh.config"
SANDBOX_SSH="limactl shell $SANDBOX_NAME --"

B='\033[1m'
C='\033[36m'
D='\033[2m'
G='\033[32m'
R='\033[0m'

BRANCH="${1:-}"
BASE="${2:-main}"

if [ -z "$BRANCH" ]; then
  echo -e "${B}Sandbox worktrees${R}"
  scripts/sandbox/list_worktrees.sh
  echo ""
  echo -e "${B}What next?${R}"
  echo -e "  ${C}make sandbox_worktree${R} ${D}BRANCH=<name>${R}              ${D}create from main${R}"
  echo -e "  ${C}make sandbox_worktree${R} ${D}BRANCH=<name> BASE=<base>${R}  ${D}create from base${R}"
  exit 0
fi

# Push the base branch so the sandbox has it up to date
GIT_SSH_COMMAND="ssh -F $SANDBOX_SSH_CONFIG" git push --force "lima-${SANDBOX_NAME}:repo.git" "$BASE:$BASE"

# Create the worktree in the sandbox
$SANDBOX_SSH bash -lc "
  cd ~/app
  git fetch origin
  mkdir -p ~/worktrees
  git worktree add ~/worktrees/'$BRANCH' origin/'$BASE' -b '$BRANCH'
"

echo -e "${G}${B}✓ Created worktree for $BRANCH (from $BASE) in sandbox${R}"
