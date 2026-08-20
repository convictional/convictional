# Determine if we're in Docker and set the runners accordingly
PYTHON_RUN := $(if $(wildcard /.dockerenv),python,uv run python)
UV_RUN := $(if $(wildcard /.dockerenv),,uv run)
UNAME := $(shell uname)

# Load environment variables from .env.$(ENV) if it exists, defaulting to .env.development
ENV_FILE := .env.$(or $(ENV),development)
DOTENV_RUN := $(if $(wildcard $(ENV_FILE)),$(UV_RUN) dotenv -f $(ENV_FILE) run --no-override,)

.PHONY: help
help: ## Display available commands
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

.PHONY: install
install: ## Ensures the project dependencies are installed. Usage: make install ARGS="--chromium"
	@if ! uv --version >/dev/null 2>&1; then \
		echo "Installing uv..."; \
		curl -LsSf https://astral.sh/uv/install.sh | sh; \
	else \
		echo "uv is already installed"; \
	fi
	uv sync
	uv run pre-commit install
	@if echo "$(MAKECMDGOALS) $(filter-out --,$(MAKEFLAGS))" | grep -q -- "--chromium"; then \
		echo "Installing Playwright Chromium..."; \
		uv run playwright install chromium; \
	else \
		echo "Skipping Playwright Chromium installation (use ARGS=\"--chromium\" to install)"; \
	fi
	npm install
	make install_libmagic

.PHONY: install_libmagic
install_libmagic: ## Installs required OS libraries
ifneq ($(shell which brew),)
	@if ! brew list libmagic >/dev/null 2>&1; then \
		echo "Installing libmagic via Homebrew..."; \
		HOMEBREW_NO_AUTO_UPDATE=true brew install libmagic; \
	else \
		echo "libmagic already installed via Homebrew"; \
	fi
else ifneq ($(shell which apt),)
	@if ! dpkg -l | grep -q libmagic-dev; then \
		echo "Installing libmagic-dev via apt..."; \
		sudo apt-get update; \
		sudo apt-get install -y libmagic-dev; \
	else \
		echo "libmagic-dev is already installed"; \
	fi
else
	echo "No supported package manager found. Please install libmagic manually."
endif

.PHONY: resolve_uv_conflicts
resolve_uv_conflicts: ## Resolves conflicts in the uv.lock file
	@if git ls-files -u | grep -q uv.lock; then \
		git checkout --theirs uv.lock && \
		uv lock; \
	else \
		echo "No conflict on uv.lock, no action needed."; \
	fi

.PHONY: server
server: ## Runs the server
	@$(PYTHON_RUN) -c "\
env = '$(or $(ENV),development)'; \
from config.settings import settings; \
g = '\033[32m'; c = '\033[36m'; b = '\033[1m'; r = '\033[0m'; \
print(f'''\n\
{b}╭{'─'*40}╮{r}\n\
{b}│{r}  {g}▶ Convictional{r} ({c}{env}{r})\n\
{b}│{r}\n\
{b}│{r}  App:  {b}http://localhost:{settings.app_port}{r}\n\
{b}│{r}  Vite: {b}http://localhost:{settings.vite_port}{r}\n\
{b}╰{'─'*40}╯{r}\n\
''')"
	@PORT=$$($(PYTHON_RUN) -c "from config.settings import settings; print(settings.app_port)"); \
	(while ! curl -s -o /dev/null "http://localhost:$$PORT" 2>/dev/null; do sleep 0.5; done; \
	printf '\033]0;Convictional · localhost:%s\007' "$$PORT"; \
	printf '\n\033[32m\033[1m  ✓ Ready at http://localhost:%s\033[0m\n\n' "$$PORT") & \
	exec $(UV_RUN) honcho start -p $$PORT

.PHONY: server_ngrok
server_ngrok: ## Runs the server behind ngrok at NGROK_HOST. Requires a reserved ngrok domain.
	@[ -n "$$NGROK_HOST" ] || { echo "NGROK_HOST is required. Set it to your reserved ngrok domain, e.g. NGROK_HOST=example.ngrok.dev make server_ngrok"; exit 1; }
	APP_PORT=$$($(PYTHON_RUN) -c "from config.settings import settings; print(settings.app_port)") \
	VITE_PORT=$$($(PYTHON_RUN) -c "from config.settings import settings; print(settings.vite_port)") \
	$(UV_RUN) honcho start -f Procfile.ngrok -e .env.secrets -p $$($(PYTHON_RUN) -c "from config.settings import settings; print(settings.app_port)")

.PHONY: server_ngrok_static
server_ngrok_static: ## Runs the server on ngrok without vite or reload. Requires a reserved ngrok domain.
	@[ -n "$$NGROK_HOST" ] || { echo "NGROK_HOST is required. Set it to your reserved ngrok domain, e.g. NGROK_HOST=example.ngrok.dev make server_ngrok_static"; exit 1; }
	APP_PORT=$$($(PYTHON_RUN) -c "from config.settings import settings; print(settings.app_port)") \
	$(UV_RUN) honcho start -f Procfile.ngrok_static -e .env.secrets -p $$($(PYTHON_RUN) -c "from config.settings import settings; print(settings.app_port)")

.PHONY: server_static
server_static: ## Builds assets, then serves the bundle with no Vite and no hot reload. Re-run to pick up JS/TS changes.
	VITE_BASE_PATH=/static/build $(MAKE) assets
	ASSET_BUILDING_ENABLED=False $(MAKE) app

.PHONY: browser_open
browser_open: ## Opens the app in the browser for the current directory
	PYTHONPATH=. $(PYTHON_RUN) scripts/open_browser.py

.PHONY: app
app: ## Runs the app without reload
	$(UV_RUN) uvicorn app.main:app --port $${APP_PORT:-$$($(PYTHON_RUN) -c "from config.settings import settings; print(settings.app_port)")}

.PHONY: app_watch
app_watch: ## Runs the app with hot reload
	IS_HOT_RELOAD=True $(UV_RUN) uvicorn app.main:app --reload --reload-exclude 'log/*' --port $${APP_PORT:-$$($(PYTHON_RUN) -c "from config.settings import settings; print(settings.app_port)")}

.PHONY: console
console: ## Starts a Python REPL with the virtual environment activated
	$(UV_RUN) ipython -i scripts/console.py

.PHONY: script
script: ## Runs a script with the virtual environment activated. Usage: make script ARGS="path/to/script.py"
	PYTHONPATH=. $(PYTHON_RUN) $(ARGS)

.PHONY: job
job: ## Runs a background job directly. Usage: make job ARGS="job_type '{\"key\": \"value\"}'"
	PYTHONPATH=. $(PYTHON_RUN) scripts/run_job.py $(if $(ARGS),$(ARGS),--help)

.PHONY: lint
lint: ## Runs all linters.
	$(MAKE) lint_python
	$(MAKE) lint_imports
	$(MAKE) lint_api_spec
	$(MAKE) lint_html
	$(MAKE) lint_html_format
	$(MAKE) lint_javascript

.PHONY: lint_python
lint_python: ## Checks Python for linting and formatting with ruff
	$(UV_RUN) ruff check .
	$(UV_RUN) ruff format --check .

.PHONY: lint_imports
lint_imports: ## Checks imports respect the architecture (Python via importlinter, JS via dependency-cruiser). Usage: make lint_imports ARGS="--verbose"
	$(UV_RUN) lint-imports $(ARGS)
	npm run lint-deps

.PHONY: lint_html
lint_html: ## Lint HTML files with djlint
	$(UV_RUN) djlint app/templates

.PHONY: lint_html_format
lint_html_format: ## Checks HTML files for formatting changes with djlint
	$(UV_RUN) djlint app/templates --check

.PHONY: lint_javascript
lint_javascript: ## Lint JavaScript files with ESLint
	npm run lint && npm run format-check

.PHONY: lint_api_spec
lint_api_spec: ## Lint the generated OpenAPI spec with Spectral
	PYTHONPATH=. $(PYTHON_RUN) scripts/dump_openapi_spec.py
	node_modules/.bin/spectral lint tmp/openapi.json --ruleset .spectral.yaml --fail-severity=error


.PHONY: format
format: ## Fix formatting issues
	$(UV_RUN) ruff check --fix .
	$(UV_RUN) ruff format .
	$(MAKE) format_html
	$(MAKE) format_javascript
	$(MAKE) infra_format

.PHONY: format_html
format_html: ## Fix HTML files formatting with djlint
	$(UV_RUN) djlint app/templates --reformat

.PHONY: format_javascript
format_javascript: ## Format JavaScript/TypeScript files with Prettier and ESLint
	npm run format
	npm run lint-fix

.PHONY: types
types: ## Checks for type errors
	$(MAKE) types_python
	$(MAKE) typescript

.PHONY: types_python
types_python: ## Checks for Python type errors
	$(UV_RUN) mypy .

.PHONY: typescript
typescript: ## Checks for TypeScript type errors
	npm run types

.PHONY: validate
validate: ## Runs lint and type checks in parallel. MUST pass before declaring work complete. Tests are run separately — see CLAUDE.md.
	@set -u; \
	rm -f .validate.lint.log .validate.types.log; \
	$(MAKE) lint  > .validate.lint.log  2>&1 & lint_pid=$$!; \
	$(MAKE) types > .validate.types.log 2>&1 & types_pid=$$!; \
	trap 'kill $$lint_pid $$types_pid 2>/dev/null; exit 130' INT TERM; \
	fail=0; \
	wait $$lint_pid  || { echo "\033[31m✗ lint failed\033[0m";  cat .validate.lint.log;  fail=1; }; \
	wait $$types_pid || { echo "\033[31m✗ types failed\033[0m"; cat .validate.types.log; fail=1; }; \
	if [ $$fail -eq 0 ]; then echo "\033[32m\033[1m✓ validate passed\033[0m"; rm -f .validate.lint.log .validate.types.log; fi; \
	exit $$fail

.PHONY: clean
clean: ## Removes build artifacts and the virtual environment
	rm -rf .venv
	rm -rf __pycache__
	rm -rf .pytest_cache
	rm -rf .mypy_cache
	rm -rf .ruff_cache
	rm -rf node_modules
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete

.PHONY: secret
secret: ## Generates a secret key for the application
	$(PYTHON_RUN) -c "import secrets; print(secrets.token_urlsafe(32))"

.PHONY: vapid_dev_keys
vapid_dev_keys: ## Generates a local VAPID keypair and writes it to .env.secrets (push notifications). Usage: make vapid_dev_keys ARGS="--force"
	PYTHONPATH=. $(PYTHON_RUN) scripts/generate_vapid_dev_keys.py $(ARGS)

PYTEST_CMD = ENV=test PYTHONPATH=. $(UV_RUN) pytest -s --random-order -p no:warnings
NPROC ?= $(shell nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 2)
PYTEST_PARALLEL_CMD = ENV=test PYTHONPATH=. $(UV_RUN) pytest -s --random-order -p no:warnings

.PHONY: test_all
test_all: ## Runs all tests
	@ENV=test $(MAKE) db_upgrade
	$(PYTEST_CMD) $(ARGS)
	$(MAKE) test_browser
	$(MAKE) test_javascript

.PHONY: test
test: ## Runs all tests or a single test using pytest. Usage: make test ARGS="path/to/test_file.py --random-order-seed=325017 --record-mode=rewrite"
	@ENV=test $(MAKE) db_upgrade
	$(PYTEST_CMD) --ignore=tests/browser $(ARGS)

.PHONY: test_parallel
test_parallel: ## Runs tests in parallel with pytest-xdist. Usage: make test_parallel ARGS="path/to/test_file.py" NPROC=4
	@ENV=test $(MAKE) db_upgrade_parallel_tests
	$(PYTEST_PARALLEL_CMD)  --ignore=tests/browser -n $(NPROC) $(ARGS)

.PHONY: test_integration
test_integration: ## Runs the integration tests
	@ENV=test $(MAKE) db_upgrade
	$(PYTEST_CMD) tests/integration

.PHONY: test_integration_parallel
test_integration_parallel: ## Runs the integration tests in parallel
	@ENV=test $(MAKE) db_upgrade_parallel_tests
	$(PYTEST_PARALLEL_CMD) -n $(NPROC) tests/integration

.PHONY: test_unit
test_unit: ## Runs the unit tests
	$(PYTEST_CMD) tests/unit

.PHONY: test_unit_parallel
test_unit_parallel: ## Runs the unit tests in parallel
	$(PYTEST_PARALLEL_CMD) -n $(NPROC) tests/unit

.PHONY: test_browser
test_browser: ## Runs the browser tests
	@if ! $(UV_RUN) python -c "from playwright.sync_api import sync_playwright; sync_playwright().start().chromium.launch()" 2>/dev/null; then \
		echo "Error: Chromium is not installed. Run 'make install ARGS=\"--chromium\"' to install it."; \
		exit 1; \
	fi
	@ENV=test $(MAKE) db_upgrade
	@ENV=test $(MAKE) assets
	$(PYTEST_CMD) $(if $(ARGS),$(ARGS),"tests/browser")

.PHONY: test_javascript
test_javascript: ## Runs the JavaScript tests
	npm run test

.PHONY: db_create
db_create: ## Creates the database. To create the test database, use like: ENV=test make db_create
	PYTHONPATH=. $(UV_RUN) scripts/db/manage.py --create
	$(MAKE) db_upgrade

.PHONY: db_create_parallel_tests
db_create_parallel_tests: ## Creates the parallel test worker databases. Usage: make db_create_parallel_tests NPROC=4
	@ENV=test PYTHONPATH=. $(UV_RUN) scripts/db/manage.py --create-workers $(NPROC)
	$(MAKE) db_upgrade_parallel_tests NPROC=$(NPROC)

.PHONY: db_drop
db_drop: ## Drops all tables from the database. WARNING: This will delete all data.
	PYTHONPATH=. $(UV_RUN) scripts/db/manage.py --delete

.PHONY: db_drop_parallel_tests
db_drop_parallel_tests: ## Drops all tables from the parallel test worker databases. Usage: make db_drop_parallel_tests NPROC=4
	@ENV=test PYTHONPATH=. $(UV_RUN) scripts/db/manage.py --delete-workers

.PHONY: db_seed
db_seed: ## Seeds the database from a scenario. Usage: make db_seed ARGS="ellery" (default: all scenarios)
	@ENV=$(or $(ENV),development) $(MAKE) db_upgrade
	PYTHONPATH=. $(PYTHON_RUN) scripts/seeds/run.py $(ARGS)

.PHONY: test_seeds
test_seeds: ## Validates seed scenarios without persisting (uses test database)
	@ENV=test $(MAKE) db_upgrade
	ENV=test PYTHONPATH=. $(PYTHON_RUN) scripts/seeds/run.py --dry-run $(ARGS)

.PHONY: claude_demo_data
claude_demo_data: ## Launch Claude with demo seed writing tools
	cd scripts/seeds && claude

.PHONY: demo_gifs
demo_gifs: ## Record onboarding demo GIFs from seeded data into tmp/demo_gifs/. Requires `make db_seed ARGS="ellery"`. Usage: make demo_gifs ARGS="--install command_palette"
	VITE_BASE_PATH=/static/build $(MAKE) assets
	PYTHONPATH=. $(PYTHON_RUN) scripts/demo_gifs/run.py $(ARGS)

.PHONY: db_reset
db_reset: db_drop db_create  ## Drops the database and recreates it. WARNING: This will delete all data.

.PHONY: db_reset_parallel_tests
db_reset_parallel_tests: db_drop_parallel_tests db_create_parallel_tests ## Drops the parallel test worker databases and recreates them. Usage: make db_reset_parallel_tests NPROC=4

.PHONY: db_migrate
db_migrate: ## Generates a new migration based on changes to the models. Usage: make db_migrate ARGS="--name add_users_table"
	$(UV_RUN) aerich migrate $(ARGS)

.PHONY: db_migrate_empty
db_migrate_empty: ## Generates a new empty migration. Usage: make db_migrate_empty ARGS="--name add_users_table"
	PYTHONPATH=. $(UV_RUN) scripts/db/empty_migration.py $(ARGS)

.PHONY: db_upgrade
db_upgrade: ## Applies pending migrations to the database.
	$(UV_RUN) aerich upgrade

.PHONY: db_upgrade_parallel_tests
db_upgrade_parallel_tests: ## Applies pending migrations to the parallel test worker databases. Usage: make db_upgrade_parallel_tests NPROC=4
	@seq 0 $$(($(NPROC)-1)) | xargs -P $(NPROC) -I{} sh -c 'ENV=test PYTHONPATH=. WORKER_ID={} $(MAKE) db_upgrade'

.PHONY: db_update_permissions
db_update_permissions: ## Updates column-level permissions for protected columns. Usage: RESTRICTED_DB_USERS="role1,role2" make db_update_permissions
	PYTHONPATH=. $(PYTHON_RUN) scripts/db/update_column_permissions.py

.PHONY: db_downgrade
db_downgrade: ## Reverts the last applied migration. Usage: make db_downgrade ARGS="--delete true"
	$(UV_RUN) aerich downgrade $(ARGS)

.PHONY: db_console
db_console: ## Starts psql connected to the application database
	@psql $$($(PYTHON_RUN) -c "from config.settings import settings; print(settings.postgres_dict['database'])")

.PHONY: db_dump
db_dump: ## Dumps the application database. Usage: make db_dump ARGS="> dump.sql"
	@pg_dump $$($(PYTHON_RUN) -c "from config.settings import settings; print(settings.postgres_dict['database'])") $(ARGS)

.PHONY: assets
assets: ## Bundle frontend assets. Usage: ENV=test make assets
	$(DOTENV_RUN) npm run assets

.PHONY: assets_watch
assets_watch: ## Watch for frontend asset changes and bundle them. Usage: ENV=test make assets_watch
	VITE_PORT=$${VITE_PORT:-$$($(PYTHON_RUN) -c "from config.settings import settings; print(settings.vite_port)")} $(DOTENV_RUN) npm run assets-watch

.PHONY: tmp_clear
tmp_clear: ## Clear the tmp/storage directory for current environment
	rm -rf tmp/storage/$${ENV:-development}/*

.PHONY: tmp_clear_all
tmp_clear_all: ## Clear all tmp/storage directories
	rm -rf tmp/storage/*

.PHONY: search_reindex
search_reindex: ## Reindex all search content from scratch
	PYTHONPATH=. $(PYTHON_RUN) scripts/reindex_search.py

.PHONY: cache_clear
cache_clear: ## Clear the application cache
	PYTHONPATH=. $(PYTHON_RUN) scripts/cache_clear.py

.PHONY: reset
reset: ## Reset database, clear tmp directory, re-seed database
	$(MAKE) db_reset
	$(MAKE) tmp_clear
	$(MAKE) db_seed

# --- Sandbox ---

SANDBOX_NAME := convictional-sandbox

.PHONY: sandbox
sandbox: ## Creates and provisions the sandbox VM, or starts it if stopped
	@scripts/sandbox/setup.sh

.PHONY: sandbox_push
sandbox_push: ## Pushes current branch to the sandbox bare repo, like git push
	@scripts/sandbox/push.sh

.PHONY: sandbox_worktree
sandbox_worktree: ## Creates a new worktree in the sandbox. Usage: make sandbox_worktree BRANCH=my-feature BASE=main
	@scripts/sandbox/worktree.sh $(BRANCH) $(BASE)

.PHONY: sandbox_shell
sandbox_shell: ## Opens a shell inside the sandbox VM. Usage: make sandbox_shell BRANCH=branch-name
	@scripts/sandbox/shell.sh $(BRANCH)

.PHONY: sandbox_configure
sandbox_configure: ## Syncs host user config (Claude, zsh) into the sandbox
	@scripts/sandbox/configure.sh

.PHONY: sandbox_fetch
sandbox_fetch: ## Fetches a branch from the sandbox, like git fetch. Usage: make sandbox_fetch BRANCH=branch-name
	@scripts/sandbox/fetch.sh $(BRANCH)

.PHONY: sandbox_checkout
sandbox_checkout: ## Fetches and checks out a branch from the sandbox, like git checkout. Usage: make sandbox_checkout BRANCH=branch-name
	@scripts/sandbox/checkout.sh $(BRANCH)

.PHONY: sandbox_pull
sandbox_pull: ## Pulls the current branch from the sandbox, like git pull
	@scripts/sandbox/pull.sh

.PHONY: sandbox_destroy
sandbox_destroy: ## Deletes the sandbox VM
	@limactl delete -f $(SANDBOX_NAME) 2>/dev/null || true
	@echo "\033[32m\033[1m✓ Sandbox destroyed.\033[0m"

# The environment directory the infra targets act on. Copy environments/example
# to your own and set INFRA_ENV to its name.
INFRA_ENV ?= example
INFRA_DIR := config/infra/environments/$(INFRA_ENV)

.PHONY: infra
infra: ## Run Terraform against an environment. Usage: make infra ARGS="show" INFRA_ENV=example
	cd $(INFRA_DIR) && tofu $(if $(ARGS),$(ARGS),"validate")

.PHONY: infra_lint
infra_lint: ## Lint Terraform infrastructure files with tofu
	cd config/infra && tofu fmt -check -recursive

.PHONY: infra_format
infra_format: ## Format the Terraform infrastructure files
	cd config/infra && tofu fmt -recursive

.PHONY: infra_plan
infra_plan: ## Plan the Terraform infrastructure changes. Usage: make infra_plan INFRA_ENV=example
	cd $(INFRA_DIR) && tofu plan

.PHONY: infra_apply
infra_apply: ## Apply the Terraform infrastructure changes. Usage: make infra_apply INFRA_ENV=example
	cd $(INFRA_DIR) && tofu apply
