#!/bin/bash
set -euo pipefail

SANDBOX_NAME="convictional-sandbox"
SANDBOX_SSH="limactl shell $SANDBOX_NAME --"
SANDBOX_SSH_CONFIG="$HOME/.lima/$SANDBOX_NAME/ssh.config"

G='\033[32m'
B='\033[1m'
R='\033[0m'
step() { echo -e "\n${B}==> $1${R}"; }
done_msg() { echo -e "${G}${B}✓ $1${R}"; }
err() { echo -e "\033[31m✗ $1${R}"; exit 1; }

# Preflight
$SANDBOX_SSH true 2>/dev/null || err "Sandbox is not running. Run 'make sandbox' first."

# zsh
step "Configuring zsh"
$SANDBOX_SSH bash -c 'command -v zsh >/dev/null 2>&1 || sudo apt-get install -y -qq zsh'
if [ -f "$HOME/.zshrc" ]; then
  { grep -E '^\s*alias ' "$HOME/.zshrc" || true; } | $SANDBOX_SSH bash -c 'cat >> ~/.zshrc'
  done_msg "Appended aliases to ~/.zshrc"
else
  echo "  Skipping aliases (no ~/.zshrc found on host)"
fi
if [ -f "$HOME/.zprofile" ]; then
  { grep -E '^\s*setopt ' "$HOME/.zprofile" || true; } | $SANDBOX_SSH bash -c 'cat >> ~/.zprofile'
  done_msg "Appended setopt to ~/.zprofile"
else
  echo "  Skipping setopt (no ~/.zprofile found on host)"
fi
# oh-my-zsh (if host has it)
if [ -d "$HOME/.oh-my-zsh" ]; then
  $SANDBOX_SSH bash -c 'test -d ~/.oh-my-zsh' 2>/dev/null || {
    $SANDBOX_SSH bash -c 'git clone --depth=1 https://github.com/ohmyzsh/ohmyzsh.git ~/.oh-my-zsh'
    done_msg "Installed oh-my-zsh"
  }
  # powerlevel10k theme (if host has it)
  if [ -d "$HOME/.oh-my-zsh/custom/themes/powerlevel10k" ]; then
    $SANDBOX_SSH bash -c 'test -d ~/.oh-my-zsh/custom/themes/powerlevel10k' 2>/dev/null || {
      $SANDBOX_SSH bash -c 'git clone --depth=1 https://github.com/romkatv/powerlevel10k.git ~/.oh-my-zsh/custom/themes/powerlevel10k'
      done_msg "Installed powerlevel10k theme"
    }
    if [ -f "$HOME/.p10k.zsh" ]; then
      $SANDBOX_SSH bash -c 'cat > ~/.p10k.zsh' < "$HOME/.p10k.zsh"
      done_msg "Copied .p10k.zsh"
    fi
  fi
else
  echo "  Skipping oh-my-zsh (not found on host)"
fi
# sandbox.yaml sources ~/.env (the agent credential) from ~/.bashrc, which zsh
# doesn't read. Wire it into ~/.zshrc too so login zsh shells get the credential.
$SANDBOX_SSH bash -c 'grep -qF "source ~/.env" ~/.zshrc 2>/dev/null || echo "[ -f ~/.env ] && set -a && source ~/.env && set +a" >> ~/.zshrc'
$SANDBOX_SSH bash -c 'sudo chsh -s "$(which zsh)" "$(whoami)"'
done_msg "zsh set as default shell"

# Claude config
step "Syncing Claude config"
if [ -d "$HOME/.claude" ]; then
  $SANDBOX_SSH bash -c 'rm -rf ~/.claude'
  # Exclude stored credentials — the agent authenticates from ~/.env (the token),
  # and the host's login has no business inside the VM.
  tar -C "$HOME" --no-xattrs --exclude='.claude/.credentials.json' -cf - .claude | $SANDBOX_SSH bash -c 'tar -C ~ -xf - --warning=no-unknown-keyword'
  # Rewrite host home paths to sandbox home paths in config files
  $SANDBOX_SSH bash -c "find ~/.claude -type f -name '*.json' -exec sed -i \"s|$HOME|\$HOME|g\" {} +"
  done_msg "Synced ~/.claude"
else
  echo "  Skipping ~/.claude (not found on host)"
fi

# Per-developer local configuration (gitignored). Lets each teammate provision
# machine-specific extras (e.g. a browser for QA) without committing them. Runs
# on the host; shell into the VM via "$SANDBOX_SSH". Failures are non-fatal.
LOCAL_CONFIG="$(dirname "$0")/configure.local.sh"
if [ -f "$LOCAL_CONFIG" ]; then
  step "Running local sandbox config (configure.local.sh)"
  export SANDBOX_NAME SANDBOX_SSH SANDBOX_SSH_CONFIG
  if bash "$LOCAL_CONFIG"; then
    done_msg "Local config applied"
  else
    echo -e "\033[33m  ⚠ configure.local.sh exited non-zero — continuing\033[0m"
  fi
else
  echo "  No configure.local.sh — skipping local config"
fi

echo ""
done_msg "Sandbox configured. Run 'make sandbox_shell' to get in."
