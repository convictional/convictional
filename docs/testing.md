# Testing

Tests are written with [pytest](https://docs.pytest.org/). The guiding rule is *write tests, not too many,
mostly integration* — most tests belong in `tests/integration`, because most of what can break here
involves the database.

---

## Setup

Create the test database once: `ENV=test make db_create`. It's namespaced to your checkout like every other
database here.

The `make test` targets upgrade the test database before running, so its schema always matches your models.

Tests run in **random order** to surface hidden state dependencies between them. A failure that only
reproduces on one ordering is a real bug, not flakiness — re-run the reported seed with
`make test ARGS="--random-order-seed=325017"`.

## Running tests

| Command | Runs |
| --- | --- |
| `make test_parallel` | The whole Python suite, in parallel. **The recommended daily driver.** |
| `make test` | The whole Python suite, serially |
| `make test ARGS="tests/integration/models/test_chat.py"` | One file or directory |
| `make test ARGS="-k test_updating_criteria"` | Tests matching a [keyword pattern](https://docs.pytest.org/en/stable/how-to/usage.html#specifying-which-tests-to-run) |
| `make test_integration` / `make test_unit` | One tier |
| `make test_integration_parallel` / `make test_unit_parallel` | One tier, in parallel |
| `make test_javascript` | The Vitest suite |
| `make test_browser` | The Playwright suite |

`ARGS` passes straight through to
[pytest](https://docs.pytest.org/en/stable/reference/reference.html#command-line-flags), so any flag it
accepts works.

Tests mirror the application structure: a change to `app/models/chat.py` maps to
`tests/unit/models/test_chat.py` and `tests/integration/models/test_chat.py`; a change to
`app/routers/foo.py` maps to `tests/integration/routers/test_foo.py`. For widely-used code — helpers,
shared models, base components, middleware — run the whole directory it lives under, since plenty of tests
depend on it indirectly.

### Parallel tests

Parallel runs use [pytest-xdist](https://pytest-xdist.readthedocs.io/), giving each worker process its own
database so they don't collide.

```bash
make db_create_parallel_tests    # one-time setup
make test_parallel               # run
make test_parallel NPROC=4       # control worker count (defaults to your CPU count)
make db_drop_parallel_tests      # tear the worker databases down
```

Each worker gets a database named `{base_database_name}_{worker_id}` — e.g.
`convictional_test_convictional_alice_0` — where the base name carries the checkout namespace. Workers are identified
by the `PYTEST_XDIST_WORKER` environment variable, and migrations are applied to every worker database in
parallel during setup.

## The tiers

### `tests/integration`

Where most tests go. These use IO — the database, HTTP APIs — and outbound HTTP is recorded, so they stay
fast and deterministic.

### `tests/unit`

Tests with no IO at all.

### `tests/javascript`

Vitest, with Testing Library and jsdom. Run them with `make test_javascript`. Assert on behaviour rather
than on utility class strings — styling is verified in a browser, not in a test.

### `tests/browser`

A deliberately small [Playwright](https://playwright.dev/python/) suite over Chromium and WebKit, covering
core flows. Browser tests are slow and fragile, so they're reserved for behaviour that is genuinely
browser-specific; anything that can be tested at the integration tier should be. They don't run on pull
requests — CI runs them nightly, and on request via a label.

Chromium isn't installed by default, to keep `make install` quick. For local browser runs:

```bash
make install ARGS="--chromium"
```

## Recorded HTTP

Outbound HTTP in `tests/integration` is recorded by [vcrpy](https://vcrpy.readthedocs.io/), wrapped by
[pytest-recording](https://pypi.org/project/pytest-recording/). Every test in `tests/integration` is
wrapped with cassette recording by default, one cassette file per test.

Re-record with `--record-mode=rewrite`:

```bash
make test ARGS="--record-mode=rewrite"                              # everything
make test ARGS="-k test_decision_flow --record-mode=rewrite"        # one test
make test ARGS="-m 'not requires_config' --record-mode=rewrite"     # only what needs no extra config
```

Rewriting everything is the right move after changing a system prompt or making another broad change, since
it validates across all functionality.

If a test needs credentials beyond the two keys in `.env.secrets` to re-record, mark it
`@pytest.mark.requires_config`. That's what makes the third form above possible: re-recording en masse
without dragging every third-party integration along. `@pytest.mark.disable_vcr` opts a test out of
recording entirely.

## Seeds

`make test_seeds` dry-runs every seed scenario inside a transaction and rolls back, which validates seed
code without touching your development database. CI runs the seeds on every pull request. See
[seeds](seeds.md).
