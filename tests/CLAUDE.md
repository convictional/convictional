# Testing

- **Unit tests** (`tests/unit/`): No I/O. Test pure functions. Use `setup_in_memory_db` fixture if ORM needed.
- **Integration tests** (`tests/integration/`): Use database/network. Most coverage happens here. HTTP calls are recorded via VCR.
- **Browser tests** (`tests/browser/`): Playwright E2E tests.
- **JavaScript tests** (`tests/javascript/`): Vitest + React Testing Library. Run with `make test_javascript`.

## Critical Rules

1. **Test location matters** - Unit tests go in `tests/unit/` (no I/O), integration tests go in `tests/integration/` (with database). Mirror the application structure.

2. **Write fewer, comprehensive tests** - Group related assertions into single test functions. Don't create separate tests for each assertion.

3. **Use factory functions** - Use `create_user()`, `create_meeting()`, etc. from `tests/helpers/factories.py` instead of manual object creation.

## Key Test Helpers

- `client` fixture: `AppClient` with authenticated user for HTTP requests
- `create_user()`, `create_meeting()`, etc.: Factory functions in `tests/helpers/factories.py`
- `background_jobs` fixture: Access inline job queue for assertions
- `email_delivery` fixture: Fake email delivery for assertions

## VCR for HTTP Recording

Integration tests automatically record external HTTP calls. To re-record cassettes:

```bash
make test ARGS="tests/integration/path/test.py --record-mode=rewrite"
```

## Common Mistakes

- Running commands without Makefile (`uv run pytest` instead of `make test`)
- Putting router tests in `tests/unit/` instead of `tests/integration/`
- Writing too many small granular tests instead of comprehensive functional tests
