#!/bin/bash
set -euo pipefail

SANDBOX_NAME="convictional-sandbox"
SANDBOX_SSH_CONFIG="$HOME/.lima/$SANDBOX_NAME/ssh.config"
SANDBOX_SSH="limactl shell $SANDBOX_NAME --"
SANDBOX_GIT_SSH="GIT_SSH_COMMAND=ssh -F $SANDBOX_SSH_CONFIG"

G='\033[32m' # green
B='\033[1m'  # bold
R='\033[0m'  # reset
step() { echo -e "\n${B}==> $1${R}"; }
done_msg() { echo -e "${G}${B}✓ $1${R}"; }
err() { echo -e "\033[31m✗ $1${R}"; exit 1; }

command -v limactl >/dev/null 2>&1 || err "Lima is not installed. Run 'brew install lima' first."
[ -f .env.sandbox ] || err ".env.sandbox not found. Create it with a CLAUDE_CODE_OAUTH_TOKEN (subscription) or ANTHROPIC_API_KEY (usage-billed)."

has_token=$(grep -qE '^\s*CLAUDE_CODE_OAUTH_TOKEN=' .env.sandbox && echo 1 || echo 0)
has_key=$(grep -qE '^\s*ANTHROPIC_API_KEY=' .env.sandbox && echo 1 || echo 0)
if [ "$has_token" = 0 ] && [ "$has_key" = 0 ]; then
  err ".env.sandbox needs CLAUDE_CODE_OAUTH_TOKEN (run 'claude setup-token' on the host) or ANTHROPIC_API_KEY to authenticate Claude Code."
fi

created=0
if ! limactl list -q 2>/dev/null | grep -q "^${SANDBOX_NAME}$"; then
  step "Creating sandbox VM (this takes a few minutes the first time)"
  limactl create --name="$SANDBOX_NAME" sandbox.yaml --tty=false
  limactl start "$SANDBOX_NAME"
  created=1
elif ! $SANDBOX_SSH true 2>/dev/null; then
  step "Starting sandbox VM"
  limactl start "$SANDBOX_NAME"
fi

# Always refresh the agent credential so editing .env.sandbox takes effect on the
# next `make sandbox`. ~/.env is sourced into every shell; with a token present,
# keep ANTHROPIC_API_KEY out of it (Claude Code would prefer the key) — the key
# still reaches the app via .env.secrets below.
step "Injecting agent credential"
if [ "$has_token" = 1 ]; then
  grep -E '^\s*CLAUDE_CODE_OAUTH_TOKEN=' .env.sandbox | $SANDBOX_SSH bash -c 'cat > ~/.env'
else
  $SANDBOX_SSH bash -c 'cat > ~/.env' < .env.sandbox
fi

if [ "$created" = 1 ]; then
  step "Syncing repository"
  BRANCH=$(git symbolic-ref --short HEAD)
  GIT_SSH_COMMAND="ssh -F $SANDBOX_SSH_CONFIG" git push --force "lima-${SANDBOX_NAME}:repo.git" "$BRANCH:$BRANCH"

  step "Cloning working tree"
  $SANDBOX_SSH bash -lc "rm -rf ~/app && git clone -b $BRANCH ~/repo.git ~/app"
  $SANDBOX_SSH bash -lc 'git config --global user.email "sandbox@convictional.com" && git config --global user.name "Sandbox"'
  $SANDBOX_SSH bash -c 'cat > ~/app/app/web/.env.secrets' < .env.sandbox

  step "Installing dependencies"
  $SANDBOX_SSH bash -lc 'cd ~/app/app/web && make install ARGS="--chromium"'

  step "Creating databases"
  $SANDBOX_SSH bash -lc 'cd ~/app/app/web && make db_create'
  $SANDBOX_SSH bash -lc 'cd ~/app/app/web && ENV=test make db_create'

  echo ""
  done_msg "Sandbox ready. Run 'make sandbox_shell' to get in."
else
  done_msg "Sandbox ready."
fi
