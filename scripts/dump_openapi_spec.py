#!/usr/bin/env python3
import json

from app.main import app
from config import settings

# No lifespan: app.openapi() is pure schema generation (filters routes and calls
# FastAPI's get_openapi — see _api_openapi in app/main.py). Avoiding the lifespan
# keeps `make lint_api_spec` runnable in CI where no Postgres is available.
# Likewise we avoid `scripts.helpers` here because it imports infra.db / infra.messaging.
OUTPUT_PATH = settings.root / "tmp" / "openapi.json"


def main() -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(app.openapi(), indent=2))
    print(f"OpenAPI spec written to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
