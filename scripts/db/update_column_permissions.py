#!/usr/bin/env python3

import asyncio
import sys

import asyncpg

from config import settings
from scripts.helpers import green_text, red_text

UPDATE_COLUMN_PERMISSIONS_SQL = """
    DO $$
    DECLARE
        table_record RECORD;
        column_record RECORD;
        protected_columns text[];
        accessible_columns text[];
        eng text := 'engineering@convictional.com';
        eng_write text := 'convictional-eng-write@production-440214.iam';
        fivetran text := 'fivetran';
        restricted_user text;
    BEGIN
        FOR table_record IN
            SELECT tablename
            FROM pg_tables
            WHERE schemaname = 'public'
            AND tablename != 'aerich'
        LOOP
            protected_columns := ARRAY[]::text[];
            accessible_columns := ARRAY[]::text[];

            FOR column_record IN
                SELECT
                    column_name,
                    col_description(
                        (quote_ident(table_schema)||'.'||quote_ident(table_name))::regclass::oid,
                        ordinal_position
                    ) as column_comment
                FROM information_schema.columns
                WHERE table_schema = 'public'
                AND table_name = table_record.tablename
            LOOP
                IF column_record.column_comment LIKE 'protected_column%' THEN
                    protected_columns := array_append(protected_columns, column_record.column_name);
                ELSE
                    accessible_columns := array_append(accessible_columns, column_record.column_name);
                END IF;
            END LOOP;

            FOREACH restricted_user IN ARRAY ARRAY[eng, eng_write, fivetran] LOOP
                IF array_length(protected_columns, 1) > 0 THEN
                    EXECUTE format(
                        'REVOKE SELECT ON TABLE %I FROM %I',
                        table_record.tablename,
                        restricted_user
                    );

                    IF array_length(accessible_columns, 1) > 0 THEN
                        EXECUTE format(
                            'GRANT SELECT (%s) ON TABLE %I TO %I',
                            array_to_string(
                                ARRAY(SELECT quote_ident(col) FROM unnest(accessible_columns) AS col),
                                ', '
                            ),
                            table_record.tablename,
                            restricted_user
                        );
                    END IF;
                ELSE
                    EXECUTE format('GRANT SELECT ON TABLE %I TO %I', table_record.tablename, restricted_user);
                END IF;
            END LOOP;
        END LOOP;
    END $$;
"""


async def update_column_permissions():
    try:
        postgres_config = settings.postgres_dict
        connection = await asyncpg.connect(
            host=postgres_config["host"],
            port=postgres_config["port"],
            user=postgres_config["user"],
            password=postgres_config["password"],
            database=postgres_config["database"],
        )

        await connection.execute(UPDATE_COLUMN_PERMISSIONS_SQL)

        print(green_text("Column permissions updated successfully."))
        await connection.close()
        return 0
    except Exception as e:
        print(red_text(f"Error updating column permissions: {e}"))
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(update_column_permissions())
    sys.exit(exit_code)
