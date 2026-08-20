# Scripts

- **Scripts must use lifecycle helpers** - Always use `in_app_lifespan()` or `in_database_context()` from `scripts/helpers.py`.
- Run scripts through the Makefile so `PYTHONPATH` and the environment are set up: `make script ARGS="scripts/foo.py"`. Never invoke `python scripts/...` directly.
