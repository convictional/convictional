# Sandbox

A Lima VM for running Claude Code autonomously, isolated from your host
machine. The sandbox exists to let us ship more customer-relevant work by
increasing how much autonomous AI execution we can safely do.

## Setup (once)

```bash
brew install lima
```

Authenticate Claude Code with a subscription token in `.env.sandbox`
(git-ignored). Generate it once on the host with `claude setup-token` (needs a
browser) and paste it in:

```bash
# .env.sandbox
CLAUDE_CODE_OAUTH_TOKEN=...
```

Use a token, not an API key — it bills your subscription instead of usage, and
the seat is already paid for.

**To also give the app under development its own key,** add an
`ANTHROPIC_API_KEY` alongside the token. It's written only to Convictional's
`.env.secrets`, never the shell, so the agent keeps using your subscription
while Convictional gets the key:

```bash
# .env.sandbox
CLAUDE_CODE_OAUTH_TOKEN=...    # authenticates the agent (your subscription)
ANTHROPIC_API_KEY=sk-ant-...   # for Convictional, not the agent
```

Reach for an API key as the agent's credential only when you can't get a token
(no subscription seat). Set it alone and it authenticates both.

Requires macOS 13+ (Apple Silicon recommended).

## First run

```bash
make sandbox                                    # creates the VM, provisions everything
make sandbox_worktree BRANCH=my-first-task      # creates a worktree off main
make sandbox_shell BRANCH=my-first-task         # opens a shell in that worktree

# You're in the worktree with the full stack installed and ready.
# Try running the tests:
make test ARGS="tests/unit/"

# Start an interactive Claude session:
claude --dangerously-skip-permissions
```

A git worktree is a second checkout of the same repo in a different directory.
It lets you have multiple branches checked out at once without stashing or
switching. Inside the sandbox, each task gets its own worktree so work doesn't
collide.

`--dangerously-skip-permissions` disables Claude's interactive permission
prompts. This is unsafe on your host machine. It's safe in the sandbox because
the VM boundary is the security layer — Claude can't access anything outside
the VM regardless of what it does inside it.

## Usage

### `make sandbox`

Creates and starts the VM if it doesn't exist, or ensures it's running if it
does. The first run provisions the full Convictional stack — PostgreSQL, Python/uv,
Node/npm, Playwright, Chromium, and Claude Code. This takes a few minutes.
Subsequent starts take seconds.

The VM is persistent. You use it across tasks, days, and weeks. When it gets
stale or weird, destroy it and recreate — provisioning from the yaml is the
source of truth.

### `make sandbox_push`

Pushes your host's current branch to the VM's bare repo over SSH. Run this
before starting new work so worktrees branch from up-to-date code. The host
has the VM as a git remote — code flows in via push, not pull. The VM never
reaches back to the host.

```bash
make sandbox_push
# => Pushed main (abc123) to sandbox
```

### `make sandbox_worktree BRANCH=branch-name`

Creates a new worktree in the sandbox. Pushes the base branch first, then
creates the worktree at `~/worktrees/<branch-name>`. Defaults to branching
from main.

```bash
make sandbox_worktree BRANCH=fix-auth
# => Created worktree for fix-auth (from main) in sandbox

make sandbox_worktree BRANCH=fix-auth-v2 BASE=fix-auth
# => Created worktree for fix-auth-v2 (from fix-auth) in sandbox
```

### `make sandbox_fetch BRANCH=branch-name`

Fetches a branch from the sandbox, like `git fetch`. With no branch argument,
lists all worktrees in the sandbox.

```bash
make sandbox_fetch
# Sandbox worktrees
#   main
#   fix-auth

make sandbox_fetch BRANCH=fix-auth
# => Fetched fix-auth from sandbox
```

### `make sandbox_checkout BRANCH=branch-name`

Fetches and checks out a branch from the sandbox, like `git checkout`.

```bash
make sandbox_checkout BRANCH=fix-auth
# => Checked out fix-auth from sandbox
```

### `make sandbox_pull`

Pulls the latest commits for the current branch from the sandbox, like
`git pull`.

```bash
make sandbox_pull
# => Pulled fix-auth from sandbox (def5678)
```

### `make sandbox_shell`

Opens a shell inside the VM. With a branch argument, drops you into that
worktree's directory. From here, you do whatever you want — run Claude Code,
run scripts, start a server. The sandbox is agent-agnostic.

```bash
make sandbox_shell                    # opens shell in ~/app/app
make sandbox_shell BRANCH=fix-auth    # opens shell in that worktree
```

### `make sandbox_destroy`

Deletes the VM. Recreate anytime with `make sandbox`.

## How people use it

The sandbox provides the box. What you do inside is up to you. Here's how
different workflows look in practice.

### Nick — night shift bug fixing

Nick writes specs during the day and runs an automated loop overnight. Each
spec gets a fresh Claude session (no context window blowup). He reviews
branches and reports in the morning.

```bash
# Evening: specs are ready
# ~/app/support/agent/specs/bug-disappearing-draft.md
# ~/app/support/agent/specs/bug-mailbox-sort.md
# ~/app/support/agent/specs/feat-agenda-duplication.md

make sandbox_shell

# Inside the VM — his orchestrator loops through specs:
cd ~/app

for spec in support/agent/specs/bug-*.md support/agent/specs/feat-*.md; do
  name=$(basename "$spec" .md)
  git worktree add ~/tasks/$name -b night-shift/$name main
  cd ~/tasks/$name

  claude --dangerously-skip-permissions -p "$(cat ~/app/support/agent/AGENT_LOOP.md)

## Your Task
$(cat ~/app/$spec)"

  cd ~/app
  git worktree remove ~/tasks/$name
  mv "$spec" "support/agent/specs/done-$name.md"
done
```

Morning, from the host:
```bash
make sandbox_checkout BRANCH=night-shift/bug-disappearing-draft
git diff main...night-shift/bug-disappearing-draft

make sandbox_checkout BRANCH=night-shift/bug-mailbox-sort
git diff main...night-shift/bug-mailbox-sort

make sandbox_checkout BRANCH=night-shift/feat-agenda-duplication
git diff main...night-shift/feat-agenda-duplication

# Push the ones that look good:
git push origin night-shift/bug-disappearing-draft
gh pr create --head night-shift/bug-disappearing-draft
```

### Ben — night shift react migration with visual QA

Similar to Nick's loop but specs are for migrating HTMX/Alpine components to
React. Claude uses Chrome MCP to screenshot before and after each migration to
verify visual parity.

```bash
# Evening: specs are ready
# ~/plans/feat-migrate-goal-chart-react.md
# ~/plans/feat-migrate-meeting-sidebar-react.md

make sandbox_shell

# Inside the VM:
cd ~/app

for spec in ~/plans/feat-*.md; do
  name=$(basename "$spec" .md)
  git worktree add ~/tasks/$name -b react/$name main
  cd ~/tasks/$name

  make assets
  make app &
  APP_PID=$!
  sleep 5

  claude --dangerously-skip-permissions -p "$(cat ~/app/AGENT_LOOP.md)

## Your Task
$(cat $spec)

The dev server is running at http://localhost:$(make -s app_port).
Use Chrome MCP to screenshot the EXISTING component before you change anything.
Save it as evidence/before.png.
After migration, screenshot the same page. Save as evidence/after.png.
They should be visually identical. If not, fix it until they match.

Run the existing tests to make sure behavior is preserved.
Write new React component tests if the existing coverage is thin."

  kill $APP_PID
  cd ~/app
  git worktree remove ~/tasks/$name
done
```

Morning, from the host:
```bash
make sandbox_checkout BRANCH=react/feat-migrate-goal-chart-react
make sandbox_checkout BRANCH=react/feat-migrate-meeting-sidebar-react

# Before/after screenshots make review fast:
git diff main...react/feat-migrate-goal-chart-react
# Check evidence/before.png vs evidence/after.png — looks identical, good

git push origin react/feat-migrate-goal-chart-react
gh pr create --head react/feat-migrate-goal-chart-react

# The sidebar one has a visual diff — padding is off.
# Update the spec, re-run tomorrow.
```

### Jake — interactive exploration

Jake uses the sandbox for exploratory work where the shape isn't clear upfront.
He works interactively with Claude, tries things, fails, adjusts.

```bash
make sandbox_worktree BRANCH=mailbox-refactor
make sandbox_shell BRANCH=mailbox-refactor

claude --dangerously-skip-permissions
# > "I'm trying to figure out the right architecture for mailbox views.
# >  Read app/models/workspaces/email/ and app/routers/email_threads.py.
# >  I want to explore separating MailboxView from MailboxEntry..."

# Back and forth. Try ideas, run tests, fail, adjust.
# Detach with Ctrl-B D when taking a break, come back later.

# When happy:
git add -A && git commit -m "Refactor mailbox view architecture"
```

From the host when done:
```bash
make sandbox_checkout BRANCH=mailbox-refactor
git diff main...mailbox-refactor
git push origin mailbox-refactor
gh pr create --head mailbox-refactor
```

### Prentice — design exploration

Prentice uses the sandbox to generate and evaluate design alternatives before
committing to an implementation direction.

```bash
make sandbox_worktree BRANCH=design/goal-update-flows
make sandbox_shell BRANCH=design/goal-update-flows

claude --dangerously-skip-permissions
# > "I need to explore different UX flows for goal updates. The lifecycle is:
# >  user configures goals → goals sent out to people → people fill them out →
# >  information flows back. Generate 5 different mermaid diagrams showing
# >  different ways this flow could work. For each one, describe the UI
# >  implications — what screens are needed, where buttons go, what the
# >  user sees at each step. Save each as a separate markdown file in
# >  docs/design/goal-update-alternatives/"

# Reviews the alternatives, picks pieces from each, plans next steps.
```

From the host:
```bash
make sandbox_checkout BRANCH=design/goal-update-flows
# Reviews the mermaid diagrams locally for planning — may not push,
# just reads the files for his own thinking.
```

### Comparison

| | Nick | Ben | Jake | Prentice |
|---|---|---|---|---|
| Get in | `sandbox_shell` | `sandbox_shell` | `sandbox_shell BRANCH=...` | `sandbox_shell BRANCH=...` |
| Isolate work | worktree per spec (scripted) | worktree per spec (scripted) | `sandbox_worktree` | `sandbox_worktree` |
| Run Claude | `claude -p` in a loop (unattended) | `claude -p` in a loop (unattended) | `claude` interactive | `claude` interactive |
| Duration | overnight (~2-3 hours) | overnight (~2-3 hours) | hours, interactive | an evening session |
| Results | branches + reports in VM | branches + screenshots in VM | commits when ready | design files in VM |
| Collect | `sandbox_checkout` × N in morning | `sandbox_checkout` × N in morning | `sandbox_checkout` when done | `sandbox_checkout` or just read |
| Push/PR | from host | from host | from host | maybe, or just local |

## What Claude can do inside the sandbox

Everything. The sandbox is a full copy of the app environment:

- Read and write any file
- Run the server, run tests, run linters
- Create and apply database migrations
- Install packages
- Run Playwright browser tests (headless)
- Use Chrome MCP for visual QA (headless, no display server needed)
- Use compound engineering plugins and MCP tools
- Create branches and commits
- Access the internet (for LLM APIs, package registries, documentation)

## What Claude cannot do

Anything on your host machine. The sandbox is a VM — a separate kernel,
filesystem, and network:

- No access to your home directory or other projects
- No access to your SSH keys, git credentials, or shell history
- No access to your local database or running services
- No ability to push to GitHub
- No ability to run commands on your host

The only credentials that cross the boundary are Anthropic ones — the agent's
auth and an optional app `ANTHROPIC_API_KEY` — injected at VM creation. This is
the primary risk surface: a compromised credential could be used for inference.
A subscription token is capped by your plan's rate limits; an API key is
uncapped, so set spend alerts and rate limits on any key.

## Security model

**Trust the boundary, not the permissions.** Instead of carefully configuring
what Claude can and can't do (network allowlists, credential scoping, command
restrictions), give it full access inside a boundary where the blast radius is
contained.

The VM contains no credentials beyond Anthropic ones — the agent's auth
(subscription OAuth token or API key) and an optional `ANTHROPIC_API_KEY` for
the app. No SSH keys, no git credentials, no production secrets, no other
usage-based API keys. Integration tests replay from VCR cassettes already in
the repo.

The known risks we're accepting:
- **Credential exposure** — the Claude Code token/key could be exfiltrated via
  prompt injection. A subscription token is capped by plan rate limits; an API
  key is mitigated by rate limits and spend alerts.
- **Source code exposure** — the repo is readable inside the VM. We don't
  consider the source code independently valuable, but this is a team call.
- **Malicious code injection** — Claude could write code that looks correct
  but is harmful. Mitigated by human review of every diff before it ships.

Usage-based API keys (Recall, etc.) should never go in the sandbox.
Re-recording cassettes is a manual operation done on your host.

### Network access

The VM has unrestricted internet access. Claude uses it for documentation
lookups, dependency installation, and the Anthropic API. We're proposing
unrestricted access rather than a proxy/allowlist because:
- The VM has no credentials worth exfiltrating (beyond the API key above)
- Network proxies add operational friction (TLS termination issues, allowlist
  maintenance) without meaningfully improving the security posture
- The prompt injection attack surface is narrow — Claude is reading our source
  code and running our tests, not browsing untrusted content

This is an area for ongoing discussion. Restricting network access later is
straightforward if we find a reason to.

The security model should be revisited as we learn from real usage and as AI
capabilities evolve. Historical safety isn't an indicator of future safety —
this requires ongoing vigilance.

## VM lifecycle

The VM is **persistent** — create it once, use it across many tasks. The
base image includes all system packages, runtimes, and tools. Individual
tasks use git worktrees for isolation within the VM.

Worktrees are disposable. The VM is durable but rebuildable. If it gets into
a weird state, `make sandbox_destroy && make sandbox` recreates it from the
yaml template in minutes. The yaml is the source of truth.

## Why Lima

Lima creates Linux VMs using Apple's Virtualization.framework. We're
proposing it over alternatives because:

- **Full Linux environment** — systemd, apt, native PostgreSQL. The sandbox
  uses the same `make install && make db_create` targets you use locally.
  No separate Dockerfile or docker-compose needed.
- **No Docker Desktop dependency** — Lima is open source (CNCF). No licensing
  concerns.
- **Equivalent hypervisor isolation to Docker** — both use Apple's
  Virtualization.framework under the hood. Lima gives us a simpler
  operational model without a network proxy layer.
- **Already in use on the team** — Prentice runs his daily workflow in a Lima
  VM with worktrees. Proven pattern.

## Principles

**Trust the boundary, not the permissions.** Give Claude full access inside
the VM. Don't maintain permission lists.

**Agent-agnostic.** The sandbox is a box with the stack installed. It doesn't
prescribe how you use Claude inside it. Run it interactively, run it headless,
use an agent loop, pass it a spec — whatever works for your task.

**Worktrees for task isolation.** Each task gets its own worktree and branch
inside the VM. Tasks don't interfere with each other. Worktrees are
disposable — the VM is shared infrastructure.

**Convention over configuration.** The sandbox uses the same Makefile targets
you use. No separate provisioning system to maintain.

**Results flow through git.** Work comes out of the sandbox as branches.
Pushing and PR creation happen on the host with the engineer's real
credentials. The sandbox never touches GitHub.

## FAQ

**Q: How is this different from running Claude Code on my machine?**
On your machine, Claude has access to your entire filesystem, credentials, and
running services. In the sandbox, it has access to nothing but a copy of the
repo and an API key. You can let it run unsupervised.

**Q: Can Claude push to GitHub from the sandbox?**
No. The VM has no git remote configured. Results come back via
`sandbox_fetch` — your host fetches from the VM over SSH. You push from
your host with your own credentials.

**Q: What about secrets for third-party integrations?**
Integration tests replay from VCR cassettes, so no external API keys are
needed. Usage-based API keys should never go in the sandbox. Re-recording
cassettes is done on your host.

**Q: I logged into Claude on my Mac — can the sandbox use that login?**
No. On macOS that login lives in the Keychain, not `~/.claude/`, so
`make sandbox_configure` can't carry it into the VM. Use a
`CLAUDE_CODE_OAUTH_TOKEN` instead (see Setup). Don't run `--bare` in the VM —
bare mode ignores the token.

**Q: Can I install Claude plugins and compound engineering skills?**
Yes. The VM provisioning installs Claude Code and compound engineering. Any
plugins or MCP tools you need can be added to the provisioning yaml.

**Q: Does Chrome MCP work inside the VM?**
Yes. Chrome MCP runs headless with `--headless=true` and `--no-sandbox` flags.
No display server or Xvfb needed. Chromium is installed as part of
provisioning (shared with Playwright).

**Q: Why not Docker?**
Docker Sandbox provides equivalent VM-level isolation and has good built-in
network filtering and credential management. We're proposing Lima because it
gives us a full systemd environment where our existing Makefile targets work
unchanged, and because we don't think we need the network proxy (see Security
model above). Open to revisiting if the team prefers Docker.

**Q: What about running this in the cloud?**
V1 is local. Running in the cloud would let tasks run while your laptop
sleeps, which is desirable. We'll revisit once we've validated the local
workflow and understand what we actually need from a cloud solution.

## Further reading

- [Let's Discuss Sandbox Isolation](https://www.shayon.dev/post/2026/52/lets-discuss-sandbox-isolation/) — good overview of the security spectrum for AI sandboxing
- [Night Shift Agentic Workflow](https://jamon.dev/night-shift) — the workflow pattern that inspired this approach
