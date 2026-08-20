#!/bin/bash
# Shared helper for listing sandbox worktrees
set -euo pipefail

SANDBOX_NAME="convictional-sandbox"
SANDBOX_SSH="limactl shell $SANDBOX_NAME --"

B='\033[1m'
D='\033[2m'
R='\033[0m'

$SANDBOX_SSH bash -lc "
  cd ~/app
  git worktree list --porcelain
" | awk -v B="$B" -v D="$D" -v R="$R" '
  /^worktree / { wt=$2 }
  /^branch refs\/heads\// {
    branch = $0
    sub(/^branch refs\/heads\//, "", branch)
    if (branch == "main")
      printf "  " D branch R "\n"
    else
      printf "  " B branch R "\n"
  }
'
