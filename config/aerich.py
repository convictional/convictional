import os

from aerich import migrate as aerich_migrate
from aerich.migrate import Migrate  # type: ignore
from tortoise.backends.base.schema_generator import BaseSchemaGenerator

from config.settings import settings

# This exists so that Aerich can read the database configuration from the settings object.
config = settings.tortoise_config


# Monkey patch Migrate.get_all_version_files since os.listdir isn't deterministic across file systems.
def get_all_version_files_with_consistent_sort(cls):
    return sorted(
        filter(lambda x: x.endswith("py"), os.listdir(cls.migrate_location)),
        key=lambda x: (int(x.split("_")[0]), int(x.split("_")[1])),
    )


setattr(Migrate, "get_all_version_files", classmethod(get_all_version_files_with_consistent_sort))


# Monkey patch MIGRATE_TEMPLATE so `db` is nullable — aerich itself calls upgrade(None)/downgrade(None).
aerich_migrate.MIGRATE_TEMPLATE = """from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient | None = None) -> str:
    return \"\"\"
        {upgrade_sql}\"\"\"


async def downgrade(db: BaseDBAsyncClient | None = None) -> str:
    return \"\"\"
        {downgrade_sql}\"\"\"


MODELS_STATE = (
    {models_state}
)
"""


# Monkey patch the schema generator's dependency ordering to respect db_constraint.
# Tortoise records the referenced table as an ordering dependency unconditionally
# (backends/base/schema_generator.py:243) and only consults db_constraint afterwards, when
# deciding whether to emit the FK (:244). So a db_constraint=False relation contributes no
# DDL but still constrains CREATE TABLE order, and a cycle through one aborts schema
# generation entirely. Without this, `aerich init-db` cannot generate this schema at all.
_get_field_sql_and_related_table = BaseSchemaGenerator._get_field_sql_and_related_table


def _get_field_sql_and_related_table_honoring_db_constraint(self, field_object, *args):
    field_creation_string, related_table_name = _get_field_sql_and_related_table(self, field_object, *args)
    reference = getattr(field_object, "reference", None)
    if reference is not None and not reference.db_constraint:
        return field_creation_string, ""
    return field_creation_string, related_table_name


setattr(
    BaseSchemaGenerator,
    "_get_field_sql_and_related_table",
    _get_field_sql_and_related_table_honoring_db_constraint,
)
