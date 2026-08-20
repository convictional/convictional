#!/usr/bin/env python3
import argparse
import asyncio

from aerich import migrate as aerich_migrate  # type: ignore
from aerich.migrate import Migrate  # type: ignore
from aerich.utils import get_formatted_compressed_data, get_models_describe

import config.aerich  # noqa: F401  -- ensure MIGRATE_TEMPLATE monkey patch is applied
from config import settings
from scripts.helpers import green_text


async def main(migration_name: str | None = None):
    migration_name = migration_name or "update"

    Migrate.app = "convictional"  # It tries to access migrations before setting this.
    await Migrate.init(config=settings.tortoise_config, app=Migrate.app, location=str(settings.root / "migrations"))

    filename = await Migrate.generate_version(migration_name)
    destination = settings.root / "migrations" / Migrate.app
    models_state = get_formatted_compressed_data(get_models_describe(Migrate.app))
    with open(destination / filename, "w") as f:
        f.write(
            aerich_migrate.MIGRATE_TEMPLATE.format(upgrade_sql="TODO", downgrade_sql="TODO", models_state=models_state)
        )

    print(green_text(f"Success migrate {filename}"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create an empty migration.")
    parser.add_argument("--name", help="Name for the migration", default="update")
    args = parser.parse_args()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(main(args.name))
