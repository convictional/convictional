#!/usr/bin/env python3

import argparse
import asyncio
import getpass
import os
import re
import sys
from dataclasses import dataclass

import asyncpg

from config import settings
from scripts.helpers import green_text, red_text


@dataclass
class DatabaseConfig:
    host: str
    port: int | None
    app_user: str
    app_password: str
    database: str
    admin_user: str
    admin_password: str


async def create_database(connection: asyncpg.Connection, config: DatabaseConfig):
    # Create the app user role if it doesn't exist.
    # IAM-authenticated users (identified by @ in username) are managed externally.
    if config.app_user and "@" not in config.app_user:
        password_clause = f"PASSWORD '{config.app_password}'" if config.app_password else ""
        await connection.execute(f"""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT FROM pg_catalog.pg_roles
                    WHERE rolname = '{config.app_user}') THEN
                    CREATE ROLE "{config.app_user}" LOGIN {password_clause};
                END IF;
            END $$;
        """)
        print(green_text(f"User {config.app_user} has been created or already exists."))

    # Create the database owned by the admin user (who has CREATEDB)
    try:
        await connection.execute(f"CREATE DATABASE {config.database};")
        print(green_text(f"Database {config.database} created."))
    except asyncpg.exceptions.DuplicateDatabaseError:
        print(green_text(f"Database {config.database} already exists."))

    # Connect to the new database to enable the extensions
    new_db_connection = await asyncpg.connect(
        host=config.host,
        port=config.port,
        database=config.database,
        user=config.admin_user,
        password=config.admin_password or None,
    )
    try:
        await new_db_connection.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        await new_db_connection.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
        print(green_text(f"Extensions enabled on {config.database}."))

        # Set default privileges so tables created by the admin are accessible to the app user,
        # and grant access on the public schema. Required for dynamically created databases
        # where instance-level default privileges don't carry over.
        for resource in ["TABLES", "SEQUENCES"]:
            await new_db_connection.execute(
                f'ALTER DEFAULT PRIVILEGES FOR ROLE "{config.admin_user}" IN SCHEMA public '
                f'GRANT ALL PRIVILEGES ON {resource} TO "{config.app_user}"'
            )
            await new_db_connection.execute(
                f'GRANT ALL PRIVILEGES ON ALL {resource} IN SCHEMA public TO "{config.app_user}"'
            )
        await new_db_connection.execute(f'GRANT USAGE, CREATE ON SCHEMA public TO "{config.app_user}"')
        print(green_text(f"Default privileges for {config.app_user} set on {config.database}."))
    finally:
        await new_db_connection.close()


async def delete_database(connection: asyncpg.Connection, config: DatabaseConfig):
    try:
        await connection.execute(f"DROP DATABASE IF EXISTS {config.database};")
        print(green_text(f"Database {config.database} deleted."))
    except Exception as e:
        print(red_text(f"Failed to delete database {config.database}: {e}"))
        sys.exit(1)


async def main(action: str, worker_id: str | None = None):
    admin_user = os.getenv("ADMIN_POSTGRES_USER", getpass.getuser())
    admin_password = os.getenv("ADMIN_POSTGRES_PASSWORD", "")
    default_database = "postgres"
    if worker_id:
        database_name = f"{settings.postgres_dict['database']}_{worker_id}"
    else:
        database_name = settings.postgres_dict["database"]

    config = DatabaseConfig(
        host=settings.postgres_dict["host"],
        port=settings.postgres_dict.get("port"),
        # In demo, the app runs as a different SA than the one that creates the database
        app_user=os.getenv("APP_POSTGRES_USER", settings.postgres_dict.get("user", "")),
        app_password=settings.postgres_dict.get("password", ""),
        database=database_name,
        admin_user=admin_user,
        admin_password=admin_password,
    )

    connection = await asyncpg.connect(
        host=config.host,
        port=config.port,
        database=default_database,
        user=admin_user,
        password=admin_password or None,
    )

    try:
        if action == "create":
            await create_database(connection, config)
        elif action == "delete":
            await delete_database(connection, config)
        elif action == "delete_workers":
            base_db_name = settings.postgres_dict["database"]
            pattern = f"^{re.escape(base_db_name)}_\\d+$"
            try:
                result = await connection.fetch(f"SELECT datname FROM pg_database WHERE datname ~ '{pattern}'")
                if result:
                    print(green_text(f"Deleting {len(result)} worker databases:"))
                    for row in result:
                        db_name = row["datname"]
                        print(f"  - {db_name}")
                        await connection.execute(f"DROP DATABASE {db_name}")
                else:
                    print(green_text("No worker databases found."))
            except Exception as e:
                print(red_text(f"Failed to delete worker databases: {e}"))

    except Exception as e:
        print(red_text(f"An error occurred: {e}"))
        sys.exit(1)
    finally:
        await connection.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Manage PostgreSQL database.")
    parser.add_argument("--create", help="Create the database", action="store_true")
    parser.add_argument("--delete", help="Delete the database", action="store_true")
    parser.add_argument("--delete-workers", help="Delete worker databases", action="store_true")
    parser.add_argument(
        "--create-workers", help="Create worker databases for parallel testing (supply number of workers)", type=int
    )

    args = parser.parse_args()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    if args.create:
        loop.run_until_complete(main("create"))
    elif args.delete:
        loop.run_until_complete(main("delete"))
    elif args.delete_workers:
        loop.run_until_complete(main("delete_workers"))
    elif args.create_workers is not None:
        for i in range(args.create_workers):
            loop.run_until_complete(main("create", str(i)))
