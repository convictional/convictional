# Development

Everything you need to run the app locally beyond the quick start in the [README](../README.md):
prerequisites in detail, running several checkouts at once, dependency management, and editor setup.

---

## Prerequisites

- **[uv](https://docs.astral.sh/uv/)** — `curl -LsSf https://astral.sh/uv/install.sh | sh`. uv manages
  the Python version (3.13) for you, so there's no need for pyenv.
- **[Postgres](https://www.postgresql.org) 18** with **[pgvector](https://github.com/pgvector/pgvector#installation)**.
  On Ubuntu, install `postgresql-18` from the [Postgres APT repository](https://www.postgresql.org/download/linux/ubuntu/).
- **Node**, at the version in `.nvmrc`. With [nvm](https://github.com/nvm-sh/nvm), `nvm use` picks it up.
- **libmagic** — `make install` installs this for you via Homebrew or apt.

`make install` handles the rest: `uv sync`, `npm install`, and the pre-commit hook. Pass
`ARGS="--chromium"` if you also want Playwright's Chromium for [browser tests](testing.md).

## Configuration

Settings are defined in one place, `config/settings.py`, and read from the environment. Three files are
loaded in order, later files winning: `.env`, `.env.{ENV}` (so `.env.development` by default), and
`.env.secrets`.

`.env.development` and `.env.test` are committed and hold the defaults that make a local checkout work.
`.env.secrets` is yours alone — it's gitignored, and you create it by hand:

```
ANTHROPIC_API_KEY={value}
OPENAI_API_KEY={value}
```

`ANTHROPIC_API_KEY` drives inference ([Anthropic console](https://console.anthropic.com/settings/keys)) and
`OPENAI_API_KEY` drives embeddings for search ([OpenAI API keys](https://platform.openai.com/account/api-keys)).
Everything else is optional and feature-gated — each integration simply stays hidden when its
credentials are unset. See [integrations](integrations.md) to turn one on, and
[self-hosting](self-hosting.md) for the full list of settings a deployment cares about.

### Push notifications

Web push needs a VAPID keypair. `make vapid_dev_keys` generates one and writes `VAPID_PUBLIC_KEY` and
`VAPID_PRIVATE_KEY` into `.env.secrets`; `make vapid_dev_keys ARGS="--force"` rotates it. Without them the
Push notifications section of `/notifications` stays hidden and everything else works. A deployment uses
its own keypair — never commit the dev pair.

## Running the server

`make server` runs the app through [honcho](https://honcho.readthedocs.io/), which starts uvicorn with
hot reload alongside the Vite asset watcher. The startup banner prints your app URL.

Two variants exist for asset debugging: `make server_static` builds the bundle once and serves it with no
Vite and no hot reload (re-run it to pick up JS/TS changes), and `make app` runs the app alone.

## Running multiple instances

Separate clones and git worktrees are isolated automatically — each gets its own database, ports, and
storage, derived from the checkout's directory name. No configuration needed.

```bash
# Clone 1: ~/Code/convictional-red
make db_create  # Creates convictional_development_convictional_red
make server     # Runs on a deterministic port unique to "convictional_red"

# Clone 2: ~/Code/convictional-blue
make db_create  # Creates convictional_development_convictional_blue
make server     # Runs on a different deterministic port
```

- **Database** — named `convictional_{ENV}_{directory}`, from the checkout directory's basename.
- **Ports** — computed deterministically from the directory name. Override with
  `APP_PORT=9000 VITE_PORT=9001 make server`.
- **Storage** — scoped to `tmp/storage/{ENV}/`, already per-directory since each checkout has its own
  filesystem.

**Telling the tabs apart:** that's why the clones above are named for colours. End a checkout's directory
name with a colour from `DEV_COLORS` in `config/settings.py` (`red`, `orange`, `yellow`, `green`, `blue`,
`purple`, `pink`, `cyan`, `teal`) and that checkout serves a favicon tinted to match. The page title is
prefixed with the directory name too, minus a leading `convictional-` and upper-cased — so `~/Code/convictional-red`
shows a red icon and `RED | …` in the tab, and `~/Code/convictional-blue` a blue one and `BLUE | …`. This matters
most when several agents are each driving their own checkout — the browser tab tells you which one you're
looking at.

`make browser_open` opens the current checkout's URL, which is the quickest way to get the right one.

## Dependencies

Python dependencies are managed with [uv](https://docs.astral.sh/uv/):

| Command | Purpose |
| --- | --- |
| `uv add [name]` | Add a dependency |
| `uv add --group development [name]` | Add a development dependency |
| `uv add --group test [name]` | Add a test dependency |
| `uv sync` | Sync the environment to the lockfile |
| `uv lock` | Update the lockfile |
| `uv remove [name]` | Remove a dependency |

JavaScript dependencies use npm as usual. If you hit a `uv.lock` conflict after a merge,
`make resolve_uv_conflicts` takes theirs and re-locks.

## Editor setup

Use whatever you prefer. There's shared configuration for VSCode; PyCharm works fine without any.

### VSCode

Recommended extensions live in `.vscode/extensions.json` — VSCode offers to install them. To format on
save, add this to your user settings:

```json
{
  "[python]": {
    "editor.formatOnSave": true,
    "editor.codeActionsOnSave": {
      "source.fixAll": "explicit"
    },
    "editor.defaultFormatter": "charliermarsh.ruff"
  },
  "[jinja-html]": {
    "editor.defaultFormatter": "monosans.djlint",
    "editor.formatOnSave": true
  }
}
```

The TailwindCSS IntelliSense extension needs to be told we write Jinja:

```json
"tailwindCSS.includeLanguages": {
  "jinja-html": "html"
}
```

### Debugging with VSCode

Create `.vscode/launch.json` with configurations for the server and the asset watcher, plus a compound
configuration that runs both. The two names under `compounds` must match the configuration names above
them:

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Python Debugger",
      "type": "debugpy",
      "request": "launch",
      "cwd": "${workspaceFolder}",
      "program": "${workspaceFolder}/.venv/bin/python",
      "args": ["-Xfrozen_modules=off", "-m", "uvicorn", "app.main:app", "--reload"],
      "justMyCode": true,
      "console": "integratedTerminal"
    },
    {
      "name": "Watch Assets",
      "type": "node",
      "request": "launch",
      "cwd": "${workspaceFolder}",
      "runtimeExecutable": "npm",
      "runtimeArgs": ["run", "assets-watch"]
    }
  ],
  "compounds": [
    {
      "name": "Start Debug Server",
      "configurations": ["Python Debugger", "Watch Assets"]
    }
  ]
}
```

## Other tools

- `make console` — an IPython REPL with the app loaded.
- `make script ARGS="scripts/foo.py"` — run a script with `PYTHONPATH` set.
- `make job ARGS='job_type {}'` — run a background job directly.
- `make db_console` — psql, connected to this checkout's database.
- `make sandbox` — a Lima VM for running agents off your host. See [sandbox](sandbox.md).
