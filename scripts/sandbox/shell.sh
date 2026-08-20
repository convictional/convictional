#!/bin/bash
set -euo pipefail

SANDBOX_NAME="convictional-sandbox"
SANDBOX_SSH="limactl shell $SANDBOX_NAME --"

B='\033[1m'
C='\033[36m'
D='\033[2m'
R='\033[0m'

BRANCH="${1:-}"

if [ -z "$BRANCH" ]; then
  echo -e "${B}Sandbox worktrees${R}"
  scripts/sandbox/list_worktrees.sh
  echo ""
  echo -e "${B}What next?${R}"
  echo -e "  ${C}make sandbox_shell${R} ${D}BRANCH=<name>${R}      ${D}open shell in worktree${R}"
  exit 0
fi

WORKTREE=$($SANDBOX_SSH bash -lc "
  cd ~/app
  git worktree list --porcelain | awk -v branch='$BRANCH' '
    /^worktree / { wt=\$2 }
    /^branch refs\/heads\// { sub(/^branch refs\/heads\//, \"\"); if (\$0 == branch) print wt }
  '
")

if [ -z "$WORKTREE" ]; then
  echo -e "\033[31m✗ No worktree for branch: ${B}$BRANCH${R}" >&2
  echo -e "${B}Sandbox worktrees${R}" >&2
  scripts/sandbox/list_worktrees.sh >&2
  exit 1
fi

exec limactl shell "$SANDBOX_NAME" -- bash -lc "cd '$WORKTREE' && exec \"\$(getent passwd \$(whoami) | cut -d: -f7)\" -l"
