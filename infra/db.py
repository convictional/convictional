import base64
import binascii
from collections import namedtuple
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable
from contextlib import asynccontextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from enum import Enum
from typing import Any, ClassVar, Self, TypeVar, Union, cast
from urllib.parse import ParseResult, urljoin, urlparse, urlunparse
from uuid import UUID
from uuid import uuid4 as generate_uuid

import asyncpg
import google.auth
import google.auth.credentials
from asyncpg.connection import Connection as AsyncpgConnection
from google.auth.transport import requests
from pydantic import BaseModel, Field, GetCoreSchemaHandler
from pydantic_core import CoreSchema
from pypika_tortoise import Order  # type: ignore
from pypika_tortoise.context import SqlContext
from pypika_tortoise.functions import Cast
from pypika_tortoise.terms import BasicCriterion, Criterion, Term
from pypika_tortoise.utils import format_alias_sql
from tortoise import BaseDBAsyncClient, Tortoise, connections, fields, signals
from tortoise.backends.asyncpg.client import AsyncpgDBClient
from tortoise.backends.asyncpg.executor import AsyncpgExecutor
from tortoise.backends.base.schema_generator import BaseSchemaGenerator
from tortoise.contrib.postgres.indexes import PostgreSQLIndex
from tortoise.contrib.pydantic import pydantic_model_creator
from tortoise.exceptions import DoesNotExist, FieldError, ParamsError
from tortoise.expressions import Q
from tortoise.fields.data import T
from tortoise.functions import Coalesce
from tortoise.manager import Manager
from tortoise.models import Model
from tortoise.queryset import QuerySet
from tortoise.transactions import in_transaction

from config import settings
from config.enums import RecordModelEvent
from config.logging import logger
from lib.json import JSONDumps, JSONLoads

#
# Database management
#
#


class Connection(AsyncpgConnection):
    """
    A custom connection class that does not perform the following resets which asyncpg does by default:
        - advisory locks
        - closing all open cursors
        - configurations using SET

    We don't use these features in our application, so we can skip the N+1 extra queries. Note that tranasctions will
    still be rolled back and closed correctly on exceptions.

    This is the recommended solution via https://github.com/MagicStack/asyncpg/issues/780
    """

    def get_reset_query(self):
        return ""


class AsyncpgExecutorWithCallbacks(AsyncpgExecutor):
    async def execute_select(self, sql: str, values: list | None = None, custom_fields: list | None = None) -> list:
        instance_list = await super().execute_select(sql, values, custom_fields)
        for instance in instance_list:
            if isinstance(instance, RecordModel):
                instance.after_fetch()

        return instance_list


AsyncpgDBClient.executor_class = AsyncpgExecutorWithCallbacks


class CloudConnectedAsyncpgDBClient(AsyncpgDBClient):
    sql_credentials: google.auth.credentials.Credentials

    @staticmethod
    async def _get_credentials():
        creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/sqlservice.login"])
        return creds

    async def create_connection(self, with_db: bool) -> None:
        self.sql_credentials = await self._get_credentials()

        pool_min_size = self.extra.get("pool_min_size", 10)
        pool_max_size = self.extra.get("pool_max_size", 10)
        command_timeout = self.extra.get("command_timeout")

        async def get_connection(dsn: str | None = "", **kwargs) -> asyncpg.Connection:
            if not self.sql_credentials.valid:
                self.sql_credentials.refresh(requests.Request())

            connect_kwargs: dict[str, Any] = {
                "host": self.host,
                "port": self.port,
                "user": self.user,
                "password": str(self.sql_credentials.token),
                "database": self.database,
                # asyncpg direct_tls breaks on asyncio cancellation: https://github.com/MagicStack/asyncpg/issues/1211
                "direct_tls": False,
                "connection_class": Connection,
                "server_settings": self.server_settings,
            }
            if command_timeout is not None:
                connect_kwargs["command_timeout"] = command_timeout

            return await asyncpg.connect(**connect_kwargs)

        async def init_connection(conn: asyncpg.Connection) -> None:
            await conn.execute(f"SET hnsw.ef_search = {settings.hnsw_max_candidates_examined}")
            await conn.execute(f"SET hnsw.iterative_scan = '{settings.hnsw_iterative_scan}'")
            await conn.execute(f"SET hnsw.max_scan_tuples = {settings.hnsw_max_scan_tuples}")

        pool_kwargs: dict[str, Any] = {
            "min_size": pool_min_size,
            "max_size": pool_max_size,
            "connect": get_connection,
            "connection_class": Connection,
            "init": init_connection,
        }
        if command_timeout is not None:
            pool_kwargs["command_timeout"] = command_timeout

        self._pool = await asyncpg.create_pool(**pool_kwargs)


client_class = CloudConnectedAsyncpgDBClient


async def init_db():
    db_config = settings.tortoise_config

    connections_config: dict[str, dict[str, Any]] = db_config.get("connections", {})
    for connection_config in connections_config.values():
        connection_config["credentials"]["connection_class"] = Connection

    await Tortoise.init(db_config)


async def clean_db():
    db = connections.get("default")
    for app, models in Tortoise.apps.items():
        if app != "migrations":
            for model in models.values():
                await db.execute_query(f'TRUNCATE TABLE "{model._meta.db_table}" CASCADE')


async def close_db():
    await Tortoise.close_connections()


#
# Fields
#
#


class JSONField(fields.JSONField[T]):  # type: ignore
    def __init__(self, **kwargs):
        super().__init__(encoder=JSONDumps, decoder=JSONLoads, **kwargs)


class LocalTimeField(fields.TimeField):
    """Time-of-day column that doesn't carry a timezone offset.

    Tortoise's default ``TimeField`` maps to ``TIMETZ`` on Postgres and re-attaches a
    default UTC tzinfo on read. For "wall-clock in some other column's timezone"
    semantics (e.g., working hours interpreted in ``user.time_zone``), we want plain
    ``TIME`` and naive values on both sides of the round-trip.
    """

    # Tortoise looks dialect overrides up by literal name `_db_<dialect>`; CapWords would miss.
    class _db_postgres:  # noqa: N801
        SQL_TYPE = "TIME"

    def to_python_value(self, value: Any) -> time | timedelta | None:
        # Parent TimeField re-attaches `get_default_timezone()` to any naive value it
        # reads back, which leaks an unwanted tz into wall-clock comparisons. Strip it.
        result = super().to_python_value(value)
        if isinstance(result, time) and result.tzinfo is not None:
            return result.replace(tzinfo=None)
        return result

    def to_db_value(self, value: Any, instance: type[Model] | Model) -> time | timedelta | None:
        # Symmetric with to_python_value: a tz-aware time written by a forgetful caller
        # is meaningless for a plain TIME column (no tz to round-trip), so normalize.
        if isinstance(value, time) and value.tzinfo is not None:
            value = value.replace(tzinfo=None)
        return super().to_db_value(value, instance)


class PydanticField(fields.JSONField):  # type: ignore
    pydantic_model: type[BaseModel]

    def __init__(self, pydantic_model: type[BaseModel], **kwargs):
        self.pydantic_model = pydantic_model
        super().__init__(**kwargs)
        self.encoder = JSONDumps
        self.decoder = JSONLoads

    def encode_model(self, model: BaseModel):
        """Encode each field of the model to a JSON serializable format."""
        if not hasattr(model, "model_dump"):
            return model

        return model.model_dump()

    def to_db_value(self, value: Any, instance: type[Model] | Model):
        if self.null and value is None:
            return None

        encoded_fields = self.encode_model(value)
        return self.encoder(encoded_fields)

    def to_python_value(self, value: Any):
        if isinstance(value, (str, bytes)):
            try:
                value = self.decoder(value)
            except Exception:
                raise FieldError("Value is invalid JSON value.")
        if isinstance(value, self.pydantic_model):
            return value

        if self.null and value is None:
            return None

        return self.pydantic_model(**value)


class PydanticListField(PydanticField):  # type: ignore
    def to_db_value(self, value: Any, instance: type[Model] | Model):
        self.validate(value)

        if isinstance(value, (str, bytes)):
            try:
                self.decoder(value)
            except Exception:
                raise FieldError("Value is invalid json value.")
            return value
        if not value:
            return "[]"
        dict_list = [self.encode_model(item) for item in value]
        return self.encoder(dict_list)

    def to_python_value(self, value: Any):
        if isinstance(value, (str, bytes)):
            # Use the decoder to decode the entire object
            value = self.decoder(value)
            return [self.pydantic_model(**item) for item in value]
        if not value:
            return []
        if not isinstance(value, list):
            raise FieldError("Value must be a list.")
        if not all(isinstance(item, self.pydantic_model) for item in value):
            raise FieldError(f"All items must be of type {self.pydantic_model}.")

        return value


class VectorField(fields.Field[list[float]]):
    def __init__(self, vector_size: int, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._vector_size = vector_size

    @property
    def SQL_TYPE(self) -> str:  # type: ignore # noqa: N802, RUF100
        return f"vector({self._vector_size})"

    def to_db_value(self, value: list[float], instance: type[Model] | Model) -> str:
        if isinstance(value, list):
            return "[" + ",".join([str(item) for item in value]) + "]"
        return value

    def to_python_value(self, value: Any) -> list[float]:
        if isinstance(value, str):
            value = value.removeprefix("[").removesuffix("]")
            return list([float(item) for item in value.split(",")])
        return value


# This is a workaround for the fact that Tortoise does not support generated fields
# that are not primary keys.
class TSVectorField(fields.Field[str]):
    SQL_TYPE = "TSVECTOR"
    field_type = str
    allows_generated = True


class LTreeField(fields.Field[str]):
    SQL_TYPE = "LTREE"
    field_type = str


class GlobalIDField(fields.Field["GlobalID"]):
    SQL_TYPE = "VARCHAR(500)"
    field_type = str

    def to_db_value(self, value: Any, instance: type[Model] | Model) -> str:
        if isinstance(value, GlobalID):
            return str(value)
        return value

    def to_python_value(self, value: Any) -> "GlobalID":
        if isinstance(value, str):
            return GlobalID.parse(value)
        return value


#
# Indexes
#
#


class OpclassIndex(PostgreSQLIndex):
    """Index whose columns carry PostgreSQL operator classes.

    An opclass cannot be smuggled through `field_names`: Tortoise's `_get_index_sql` quotes
    every entry it is given, so `'"col" opclass'` comes back as `'""col" opclass"'` and the
    generated DDL is a syntax error. `field_names` therefore stays bare -- which also keeps
    `index_name()` producing the names already deployed -- and the opclass is appended here,
    after quoting.
    """

    def opclass_for(self, column: str) -> str | None:
        raise NotImplementedError

    def get_sql(self, schema_generator: BaseSchemaGenerator, model: type[Model], safe: bool) -> str:
        columns = []
        for column in self.field_names:
            # Expression indexes arrive already parenthesised and must not be quoted.
            rendered = column if column.startswith("(") else schema_generator.quote(column)
            if opclass := self.opclass_for(column):
                rendered = f"{rendered} {opclass}"
            columns.append(rendered)
        return schema_generator.INDEX_CREATE_TEMPLATE.format(
            exists="IF NOT EXISTS " if safe else "",
            index_name=self.index_name(schema_generator, model),
            # Postgres spells the access method `USING <type>`. BasePostgresSchemaGenerator
            # adds that inside _get_index_sql, which this override bypasses; these indexes
            # subclass PostgreSQLIndex so mirroring it here is safe.
            index_type=f"USING {self.INDEX_TYPE} " if self.INDEX_TYPE else "",
            table_name=model._meta.db_table,
            fields=", ".join(columns),
            extra=self.extra or "",
        )


# This adds the right identity implement for a GIN index so that Aerich doesn't generate new migrations for it every
# time migrate is called.
class GinIndex(OpclassIndex):
    INDEX_TYPE = "GIN"

    def __init__(
        self,
        *expressions: Term,
        fields: tuple[str, ...] | list[str] | None = None,
        name: str | None = None,
        opclass: str | None = None,
        fastupdate: bool | None = None,
    ):
        super().__init__(*expressions, fields=fields, name=name)
        # A GIN index over a plain text column has no default operator class, so one must be
        # named (gin_trgm_ops) or the CREATE INDEX is rejected outright.
        self.opclass = opclass
        self.fastupdate = fastupdate
        if fastupdate is not None:
            self.extra = f" WITH (fastupdate={'on' if fastupdate else 'off'})"

    def opclass_for(self, column: str) -> str | None:
        return self.opclass

    def __hash__(self) -> int:
        return hash((self.INDEX_TYPE, tuple(self.fields), self.opclass, self.fastupdate))

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, PostgreSQLIndex)
            and self.INDEX_TYPE == other.INDEX_TYPE
            and self.fields == other.fields
            and getattr(other, "opclass", None) == self.opclass
            and getattr(other, "fastupdate", None) == self.fastupdate
        )


class PartialIndex(PostgreSQLIndex):
    def __init__(
        self,
        *expressions: Term,
        fields: tuple[str, ...] | list[str] | None = None,
        name: str | None = None,
        condition: dict | None = None,
        extra: str | None = None,
    ):
        super().__init__(*expressions, fields=fields, name=name, condition=condition)
        if extra:
            if self.extra:
                extra = extra + " AND " + self.extra
            self.extra = f" WHERE {extra}"


class PrefixIndex(OpclassIndex):
    """BTree index with per-field operator classes for prefix LIKE queries."""

    def __init__(
        self,
        *expressions: Term,
        fields: tuple[str, ...] | list[str] | None = None,
        name: str | None = None,
        opclasses: dict[str, str] | None = None,
    ):
        super().__init__(*expressions, fields=fields, name=name)
        self.opclasses = opclasses or {}

    def __hash__(self) -> int:
        return hash((tuple(self.fields), tuple(sorted(self.opclasses.items()))))

    def __eq__(self, other: object) -> bool:
        return isinstance(other, PrefixIndex) and self.fields == other.fields and self.opclasses == other.opclasses

    def opclass_for(self, column: str) -> str | None:
        return self.opclasses.get(column)


class HnswIndex(OpclassIndex):
    INDEX_TYPE = "HNSW"

    def __init__(
        self,
        *expressions: Term,
        fields: tuple[str, ...] | list[str] | None = None,
        name: str | None = None,
        m: int = 16,
        ef_construction: int = 64,
        opclass: str = "vector_cosine_ops",
    ):
        super().__init__(*expressions, fields=fields, name=name)
        self.m = m
        self.ef_construction = ef_construction
        self.opclass = opclass
        self.extra = f" WITH (m = {m}, ef_construction = {ef_construction})"

    def __hash__(self) -> int:
        return hash((self.INDEX_TYPE, tuple(self.fields), self.m, self.ef_construction, self.opclass))

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, PostgreSQLIndex)
            and self.INDEX_TYPE == other.INDEX_TYPE
            and self.fields == other.fields
            and getattr(other, "m", None) == self.m
            and getattr(other, "ef_construction", None) == self.ef_construction
            and getattr(other, "opclass", None) == self.opclass
        )

    def opclass_for(self, column: str) -> str | None:
        return self.opclass


#
# Transactions
#
#

_transaction_callbacks: ContextVar[list[Callable[[BaseDBAsyncClient], Awaitable[None]]]] = ContextVar(
    "transaction_callbacks", default=[]
)
_in_transaction: ContextVar[bool] = ContextVar("in_transaction", default=False)

TRANSACTION_LOG_AFTER_SECONDS = 60.0
BULK_FETCH_CHUNK = 500


@asynccontextmanager
async def transaction(using_db: BaseDBAsyncClient | None = None) -> AsyncIterator[BaseDBAsyncClient]:
    """
    Context manager for creating a transaction scope, uses existing transaction if using_db is provided.
    """
    if using_db is not None:
        yield using_db
    else:
        # Get an outer connection that will not close on transaction completion
        base_connection = connections.get("default")
        callback_token = _transaction_callbacks.set([])
        in_transaction_token = _in_transaction.set(True)
        transaction_succeeded = False
        start = datetime.now()
        try:
            async with in_transaction("default") as connection:
                yield connection
            transaction_succeeded = True
        finally:
            duration = (datetime.now() - start).total_seconds()
            if duration > TRANSACTION_LOG_AFTER_SECONDS:
                logger.warning(
                    "Long transaction",
                    extra={"duration_seconds": duration, "succeeded": transaction_succeeded},
                    exc_info=True,
                )
            try:
                if transaction_succeeded:
                    callbacks = _transaction_callbacks.get()
                    for callback in callbacks:
                        try:
                            await callback(base_connection)
                        except Exception:
                            logger.exception("After-commit callback failed")
            finally:
                _transaction_callbacks.reset(callback_token)
                _in_transaction.reset(in_transaction_token)


async def after_commit(callback: Callable[[BaseDBAsyncClient], Awaitable[None]]):
    """
    Register a callback to be executed after the current transaction commits.
    If not in a transaction, executes the callback immediately.
    """
    in_transaction = _in_transaction.get()

    if in_transaction:
        callbacks = _transaction_callbacks.get()
        callbacks.append(callback)
    else:
        base_connection = connections.get("default")
        await callback(base_connection)


#
# SQL queries
#
#


class LTreeOperators(Enum):
    DESCENDANT = " <@ "
    MATCH = " ~ "


def ltree_descendants_operator(field: Term, value: str) -> Criterion:
    term = cast(Term, field.wrap_constant(value))
    return BasicCriterion(LTreeOperators.DESCENDANT, Cast(field, "ltree"), term)


def ltree_matches_operator(field: Term, value: str) -> Criterion:
    term = cast(Term, field.wrap_constant(value))
    return BasicCriterion(LTreeOperators.MATCH, Cast(field, "ltree"), Cast(term, "lquery"))


class CosineDistance(Term):
    def __init__(self, field: str, vector: list[float]):
        super().__init__()
        self.field = field
        self.vector = vector

    def get_sql(self, ctx: SqlContext) -> str:
        vector_sql = "[" + ", ".join(str(value) for value in self.vector) + "]"
        sql = f"\"{self.field}\" <=> '{vector_sql}'"
        if ctx.with_alias:
            return format_alias_sql(sql=sql, alias=self.alias, ctx=ctx)
        return sql


#
# Observers
#
#


Change = namedtuple("Change", ["old", "new"])
# Observers receive the model instance (not just its global_id) so DELETE observers
# can read attributes off the now-deleted row, whose record is gone from the database.
Observer = Callable[["RecordModel", dict[str, Change], BaseDBAsyncClient | None], Awaitable[None]]
ObservableType = TypeVar("ObservableType", bound="RecordModel")
observer_registry: dict[RecordModelEvent, list[tuple[type["RecordModel"], Observer]]] = {}


def observe[ObservableType: "RecordModel"](
    event_type: RecordModelEvent, model_class: type[ObservableType], observer: Observer
) -> None:
    if event_type not in observer_registry:
        observer_registry[event_type] = []
    observer_registry[event_type].append((model_class, observer))


def unobserve[ObservableType: "RecordModel"](
    event_type: RecordModelEvent, model_class: type[ObservableType], observer: Observer
) -> None:
    if event_type in observer_registry:
        observer_registry[event_type] = [
            (m, o) for m, o in observer_registry[event_type] if m != model_class or o != observer
        ]


async def handle_event(
    event_type: RecordModelEvent,
    instance: "RecordModel",
    changes: dict[str, Change] = {},
    using_db: BaseDBAsyncClient | None = None,
):
    if event_type not in observer_registry:
        return

    # Check if we're in a transaction context
    in_transaction = _in_transaction.get()

    if in_transaction:
        # Defer observers until after transaction commits
        observer_changes = changes.copy()

        for model_class, observer in observer_registry[event_type]:
            if isinstance(instance, model_class):
                # inst is captured by reference, not snapshotted. DELETE observers
                # require this: the row is gone, so only the in-memory instance still
                # carries its field values. The consequence for UPDATE observers is
                # that they see the instance's state at commit time, not at the moment
                # the event fired, so they must read only immutable fields (the record
                # id) rather than rely on point-in-time values.
                def make_deferred_observer(obs, inst, chgs):
                    async def deferred_observer(base_connection: BaseDBAsyncClient):
                        await obs(inst, chgs, base_connection)

                    return deferred_observer

                await after_commit(make_deferred_observer(observer, instance, observer_changes))
    else:
        # Execute observers immediately if not in a transaction
        for model_class, observer in observer_registry[event_type]:
            if isinstance(instance, model_class):
                await observer(instance, changes, using_db)


async def publish_post_save(
    sender: type["RecordModel"], instance: "RecordModel", created: bool, using_db, update_fields
):
    if created:
        await handle_event(RecordModelEvent.CREATE, instance=instance, using_db=using_db)
    else:
        await handle_event(RecordModelEvent.UPDATE, instance=instance, changes=instance.changes, using_db=using_db)


async def publish_post_delete(sender: type[Model], instance: "RecordModel", using_db):
    await handle_event(RecordModelEvent.DELETE, instance=instance, using_db=using_db)


#
# Models
#
#


async def set_timestamps(
    sender: type["RecordModel"], instance: "RecordModel", using_db: BaseDBAsyncClient | None, update_fields: list[str]
) -> None:
    now = datetime.now(UTC)

    # Don't auto-set timestamps if they were explicitly set by the user (non-None value in update_fields)
    explicitly_updating_created_at = (
        update_fields and "created_at" in update_fields and instance.created_at is not None
    )
    explicitly_updating_updated_at = (
        update_fields and "updated_at" in update_fields and instance.updated_at is not None
    )

    if instance.is_new and not explicitly_updating_created_at and instance.created_at is None:
        instance._set_system_field("created_at", now)

    if not explicitly_updating_updated_at:
        if instance.is_new:
            if instance.updated_at is None:
                instance._set_system_field("updated_at", now)
        else:
            if "updated_at" in instance.__dict__ and instance._original_updated_at == instance.updated_at:
                instance._set_system_field("updated_at", now)


async def reset_db_values(
    sender: type["RecordModel"],
    instance: "RecordModel",
    created: bool,
    using_db: BaseDBAsyncClient | None,
    update_fields: list[str],
) -> None:
    instance._change_tracking_cache = None
    instance._original_change_tracking_field_values = instance._change_tracking_field_values
    instance._original_updated_at = instance.updated_at if "updated_at" in instance.__dict__ else None


def dump_fields(obj: Any, extra_allowed_classes: list[type] = []):
    results: dict[str, Any] = {}

    # Use dir to serialize all fields, including properties
    for name in dir(obj):
        if name.startswith("_"):
            continue

        # Hide irrelevant generated fields
        if name in ["pk", "changes", "field_values"]:
            continue

        val = getattr(obj, name)

        # Only serialize JSON serializable types and the extra allowed classes
        if not isinstance(val, (str, int, float, bool, list, tuple, dict, type(None))) and not isinstance(
            val, tuple(extra_allowed_classes)
        ):
            continue
        results[name] = getattr(obj, name)

    return results


RecordModelType = TypeVar("RecordModelType", bound="RecordModel")


class ClassProperty[T]:
    def __init__(self, fget: Callable[[type[Any]], T]) -> None:
        self.fget = fget

    def __get__(self, instance: Any, owner: type[Any]) -> T:
        return self.fget(owner)


def classproperty(fget: Callable[[type[Any]], T]) -> ClassProperty[T]:
    return ClassProperty(fget)


class RecordModel(Model):
    id = fields.UUIDField(primary_key=True)
    created_at = fields.DatetimeField(auto_now_add=False)
    updated_at = fields.DatetimeField(auto_now=False)
    _original_change_tracking_field_values: dict[str, Any]
    _change_tracking_cache: dict[str, Any] | None
    _original_updated_at: datetime | None
    _system_set_fields: set[str]
    unscoped: Manager = Manager(Self)

    class Meta:
        abstract = True

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._change_tracking_cache = None
        self._original_updated_at = None
        self._system_set_fields = set()

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self.field_values}>"

    def __setattr__(self, name: str, value: Any) -> None:
        super().__setattr__(name, value)
        if not name.startswith("_") and hasattr(self, "_meta") and name in self._meta.fields_map:
            self._change_tracking_cache = None
            # Clear system-set flag if user is manually setting the field
            # (hasattr needed because __setattr__ is called during __init__ before _system_set_fields exists)
            if hasattr(self, "_system_set_fields") and name in self._system_set_fields:
                self._system_set_fields.discard(name)

    def _set_system_field(self, field_name: str, value: Any) -> None:
        """Set a field value and mark it as system-generated (excluded from change tracking)."""
        setattr(self, field_name, value)
        self._system_set_fields.add(field_name)

    @classproperty  # type: ignore
    def record_type(self) -> str:
        return self.__name__  # type: ignore

    @classmethod
    async def get_or_init(
        cls, defaults: dict | None = None, using_db: BaseDBAsyncClient | None = None, **kwargs: Any
    ) -> Self:
        if not defaults:
            defaults = {}

        db = using_db or cls._choose_db(True)
        try:
            return await cls.filter(**kwargs).using_db(db).get()
        except DoesNotExist:
            for key in defaults.keys() & kwargs.keys():
                if (default_value := defaults[key]) != (query_value := kwargs[key]):
                    raise ParamsError(f"Conflict value with {key=}: {default_value=} vs {query_value=}")
            merged_defaults = {**kwargs, **defaults}
            return cls(**merged_defaults)

    @classmethod
    async def get_or_create(
        cls, defaults: dict | None = None, using_db: BaseDBAsyncClient | None = None, **kwargs: Any
    ) -> tuple[Self, bool]:
        """
        Over-ridden to use get_or_init instead of tortoise get_or_create due to problems with nested transactions
        in the tortoise implementation.
        """
        instance = await cls.get_or_init(defaults, using_db, **kwargs)
        was_new = instance.is_new
        if instance.is_new:
            await instance.save(using_db=using_db)
        return instance, was_new

    @classmethod
    def bulk_create(
        cls,
        objects: Iterable[Self],  # type: ignore[override]
        batch_size: int | None = None,
        ignore_conflicts: bool = False,
        update_fields: Iterable[str] | None = None,
        on_conflict: Iterable[str] | None = None,
        using_db: BaseDBAsyncClient | None = None,
    ):
        """
        Override bulk_create to set timestamps on all objects before bulk insertion.
        Bulk operations don't trigger pre_save signals, so we need to set timestamps manually.
        """
        now = datetime.now(UTC)

        for obj in objects:
            if obj.created_at is None:
                obj._set_system_field("created_at", now)
            if obj.updated_at is None:
                obj._set_system_field("updated_at", now)

        return super().bulk_create(
            objects=objects,
            batch_size=batch_size,
            ignore_conflicts=ignore_conflicts,
            update_fields=update_fields,
            on_conflict=on_conflict,
            using_db=using_db,
        )

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: type[BaseModel], handler: GetCoreSchemaHandler) -> CoreSchema:
        return pydantic_model_creator(cls).__get_pydantic_core_schema__(source_type, handler)

    # This is used in Tortoise when the model is initialized from the database
    @classmethod
    def _init_from_db(cls, **kwargs):
        result = super()._init_from_db(**kwargs)
        result._change_tracking_cache = None
        result._original_change_tracking_field_values = result._change_tracking_field_values
        result._original_updated_at = result.updated_at if "updated_at" in result.__dict__ else None
        result._system_set_fields = set()
        return result

    def __init_subclass__(cls) -> None:
        super().__init_subclass__()

        # Add signals when a subclass is created
        cls.register_default_signals()

    @classmethod
    def register_default_signals(cls):
        signals.pre_save(cls)(set_timestamps)
        signals.post_save(cls)(publish_post_save)
        signals.post_save(cls)(reset_db_values)
        signals.post_delete(cls)(publish_post_delete)

    @property
    def global_id(self):
        return GlobalID.from_record(self)

    @property
    def global_id_url(self):
        return self.global_id.to_url

    @property
    def changes(self):
        original_values = getattr(self, "_original_change_tracking_field_values", {})
        full_diff = _diff_fields(original_values, self._change_tracking_field_values)

        results: dict[str, Change] = {}

        for name, field in self._meta.fields_map.items():
            if field.pk:
                continue
            # Skip system-set fields from change tracking
            if field.has_db_field and name in self._system_set_fields:
                continue
            if field.has_db_field and name in full_diff:
                old_val, new_val = full_diff[name]
                results[name] = Change(old_val, new_val)

        return results

    @property
    def field_values(self):
        results: dict[str, Any] = {}
        for name, field in self._meta.fields_map.items():
            if field.has_db_field and name in self.__dict__:
                results[name] = getattr(self, name)
        return results

    @property
    def _change_tracking_field_values(self):
        if self._change_tracking_cache is not None:
            return self._change_tracking_cache

        results: dict[str, Any] = {}
        for name, field in self._meta.fields_map.items():
            if field.has_db_field and name in self.__dict__:
                results[name] = field.to_db_value(getattr(self, name), self)

        self._change_tracking_cache = results
        return results

    @property
    def is_changed(self):
        return bool(self.changes)

    @property
    def is_new(self):
        return not self._saved_in_db

    @property
    def is_unsaved(self):
        return self.is_new or self.is_changed

    def after_fetch(self):
        pass

    async def refresh_from_db(self, fields=None, using_db=None):
        await super().refresh_from_db(fields, using_db)
        self._change_tracking_cache = None
        self._original_change_tracking_field_values = self._change_tracking_field_values

    async def copy(self, overrides: dict[str, Any] = {}, using_db: BaseDBAsyncClient | None = None):
        result = self.clone()
        # These won't be automatically set in Postgres if present
        result.created_at = None  # type: ignore
        result.updated_at = None  # type: ignore

        if overrides:
            result.update_from_dict(overrides)
        if not result.id:
            result.id = generate_uuid()

        await result.save(using_db=using_db)
        return result

    def dump(self, extra_allowed_classes: list[type] = []):
        return dump_fields(self, extra_allowed_classes)


def _diff_fields(original: dict[str, Any], new: dict[str, Any]):
    diff: dict[str, tuple] = {}
    all_keys = original.keys() | new.keys()
    for key in all_keys:
        original_has_key = key in original
        new_has_key = key in new

        # Lots of this complexity is to provide sensible back and forth with None, e.g. no (None, None) in the diff
        if original_has_key and new_has_key:
            if original[key] is None and new[key] is None:
                continue
            elif original[key] != new[key]:
                diff[key] = (original[key], new[key])
        elif original_has_key and original[key] is not None:
            diff[key] = (original[key], None)
        elif new_has_key and new[key] is not None:
            diff[key] = (None, new[key])

    return diff


#
# Mixins
#
#


_allow_soft_deleted: ContextVar[bool] = ContextVar("allow_soft_deleted", default=False)


@asynccontextmanager
async def allow_soft_deleted():
    token: Token = _allow_soft_deleted.set(True)
    try:
        yield
    finally:
        _allow_soft_deleted.reset(token)


@dataclass
class SoftDeleteableFilters:
    nondeleted: ClassVar[Q] = Q(deleted_at__isnull=True)
    deleted: ClassVar[Q] = Q(deleted_at__isnull=False)


class NonDeletedManager(Manager):
    def get_queryset(self) -> QuerySet:
        if _allow_soft_deleted.get():
            return super().get_queryset()

        return super().get_queryset().filter(SoftDeleteableFilters.nondeleted)


class DeletedManager(Manager):
    def get_queryset(self) -> QuerySet:
        return super().get_queryset().filter(SoftDeleteableFilters.deleted)


SoftDeleteableModel = Union[Model, "SoftDeleteableMixin"]
SoftDeleteableType = TypeVar("SoftDeleteableType", bound=SoftDeleteableModel)


class SoftDeleteableMixin:
    deleted_at: datetime | None = fields.DatetimeField(null=True, db_index=True)
    deleted: DeletedManager
    nondeleted: NonDeletedManager

    def __init_subclass__(cls: type["SoftDeleteableMixin"], **kwargs) -> None:
        if not issubclass(cls, RecordModel):
            raise TypeError("SoftDeleteMixin can only be used with RecordModel subclasses")

        super().__init_subclass__(**kwargs)
        custom_meta = getattr(cls, "Meta", None)

        if not custom_meta or not getattr(custom_meta, "manager", False):
            cls._meta.manager = NonDeletedManager(cls)

        cls.deleted = DeletedManager(cls)
        cls.nondeleted = NonDeletedManager(cls)

    @property
    def is_deleted(self):
        return self.deleted_at is not None

    async def soft_delete(self: SoftDeleteableType, using_db: BaseDBAsyncClient | None = None):
        self.deleted_at = datetime.now(UTC)
        return await self.save(using_db)  # type: ignore

    async def restore(self: SoftDeleteableType, using_db: BaseDBAsyncClient | None = None):
        self.deleted_at = None
        return await self.save(using_db)  # type: ignore


#
# Global ID
#
#


class InvalidGlobalIDParamError(Exception):
    pass


class GlobalID(BaseModel):
    """A GlobalID is a unique identifier for a record in the application.
    It is composed of the record type and the record ID.

    Example GlobalID: "gid://convictional/Goal/123e4567-e89b-12d3-a456-426614174000"
    """

    scheme: str = Field(description="URL scheme", default="gid")
    netloc: str = Field(description="Network location", default="convictional")
    path: str = Field(description="Path of the record")
    params: str = Field(description="Parameters", default="")
    query: str = Field(description="Query string", default="")
    fragment: str = Field(description="Fragment", default="")

    def __str__(self):
        components = {
            "scheme": self.scheme,
            "netloc": self.netloc,
            "path": self.path,
            "params": self.params,
            "query": self.query,
            "fragment": self.fragment,
        }
        return urlunparse(components.values())

    def __eq__(self, other):
        if other is None:
            return False

        if isinstance(other, str):
            try:
                other = GlobalID.parse(other)
                if not hasattr(other, "app_name"):
                    return False
            except ValueError:
                return False

        return (
            self.app_name == other.app_name
            and self.record_type == other.record_type
            and self.record_id == other.record_id
        )

    def __hash__(self):
        return hash((self.app_name, self.record_type, self.record_id))

    @classmethod
    def parse(cls, gid: str) -> Self:
        components: ParseResult = urlparse(gid)
        return cls(
            scheme=components.scheme,
            netloc=components.netloc,
            path=components.path,
            params=components.params,
            query=components.query,
            fragment=components.fragment,
        )

    @classmethod
    def create(cls, record_type: str, record_id: UUID, app_name: str = "convictional"):
        components = {
            "scheme": "gid",
            "netloc": app_name,
            "path": f"/{record_type}/{record_id}",
            "params": "",
            "query": "",
            "fragment": "",
        }
        return cls(**components)

    @classmethod
    def from_record(cls, record: RecordModel, app_name: str = "convictional"):
        components = {
            "scheme": "gid",
            "netloc": app_name,
            "path": f"/{record.record_type}/{record.id}",
            "params": "",
            "query": "",
            "fragment": "",
        }
        return cls(**components)

    @classmethod
    def from_param(cls, param: str) -> Self:
        try:
            decoded = base64.b64decode(param.encode()).decode()
            return cls.parse(decoded)
        except binascii.Error as e:
            raise InvalidGlobalIDParamError(f"Invalid base64 encoding: {e}")
        except UnicodeDecodeError as e:
            raise InvalidGlobalIDParamError(f"Unable to decode parameter: {e}")
        except ValueError as e:
            raise InvalidGlobalIDParamError(f"Unable to parse decoded value: {e}")

    @property
    def is_internal(self):
        return self.scheme == "gid"

    @property
    def record_type(self):
        if self.is_internal:
            return self.path.strip("/").split("/")[0]
        return None

    @property
    def record_id(self):
        if self.is_internal:
            id_str = self.path.strip("/").split("/")[1]
            return UUID(id_str)
        return None

    @property
    def app_name(self):
        if self.is_internal:
            return self.netloc
        return None

    @property
    def to_param(self):
        return base64.b64encode(str(self).encode()).decode()

    @property
    def to_url(self):
        if self.is_internal:
            base_url = str(settings.base_url)
            return urljoin(base_url, f"/gid/{self.to_param}")
        else:
            return str(self)

    async def get_or_none(self, using_db: BaseDBAsyncClient | None = None) -> RecordModel | None:
        model = Tortoise.apps[self.app_name][self.record_type]
        if not issubclass(model, RecordModel):
            raise ValueError("Model must be a subclass of RecordModel")

        return await model.get_or_none(id=self.record_id, using_db=using_db)

    async def get(self, using_db: BaseDBAsyncClient | None = None) -> RecordModel:
        model = await self.get_or_none(using_db)
        if not model:
            raise DoesNotExist(f"No record found for {self}")

        return model

    @classmethod
    async def bulk_fetch(
        cls,
        gids: list["GlobalID"],
        using_db: BaseDBAsyncClient | None = None,
        prefetch_map: dict[str, list[str]] | None = None,
    ) -> dict[tuple[str, UUID], RecordModel]:
        gids_by_type: dict[str, list[GlobalID]] = {}
        for gid in gids:
            if gid and gid.record_type:
                gids_by_type.setdefault(gid.record_type, []).append(gid)

        records: dict[tuple[str, UUID], RecordModel] = {}
        for record_type, type_gids in gids_by_type.items():
            model_class = Tortoise.apps.get("convictional", {}).get(record_type)
            if not model_class:
                continue
            prefetch_fields = (prefetch_map or {}).get(record_type, [])
            record_ids = [gid.record_id for gid in type_gids]
            # Chunked because `id__in` costs one bind parameter per element and asyncpg
            # refuses a query carrying more than 32767 of them. Callers pass a gid per
            # row of whatever they are presenting, so the list is theirs to grow.
            for start in range(0, len(record_ids), BULK_FETCH_CHUNK):
                queryset = model_class.filter(id__in=record_ids[start : start + BULK_FETCH_CHUNK])
                if using_db:
                    queryset = queryset.using_db(using_db)
                if prefetch_fields:
                    queryset = queryset.prefetch_related(*prefetch_fields)
                for record in await queryset:
                    record = cast(RecordModel, record)
                    records[(record_type, record.id)] = record

        return records


#
# Pagination
#
#


class Pagination[RecordModelType: "RecordModel"]:
    model: type[RecordModelType]
    cursor: str | None
    per_page: int
    results: list[RecordModelType]
    next_cursor: str | None
    sort_fields: list[tuple[str, str]]

    def __init__(
        self,
        model: type[RecordModelType],
        cursor: str | None = None,
        per_page: int = settings.pagination_default_per_page,
    ):
        self.model = model
        self.cursor = cursor
        self.per_page = max(1, per_page)
        self.results = []
        self.next_cursor = None
        self.sort_fields = []

    def __iter__(self):
        return iter(self.results)

    def __len__(self):
        return len(self.results)

    def __getitem__(self, index):
        return self.results[index]

    @staticmethod
    def encode_cursor(values: list[tuple[str, Any]]) -> str:
        cursor_data = JSONDumps([(field, value) for field, value in values])
        return base64.b64encode(cursor_data.encode()).decode()

    @staticmethod
    def decode_cursor(cursor: str) -> list[tuple[str, Any]]:
        try:
            # Add padding if needed to prevent "Incorrect padding" errors
            padding_needed = len(cursor) % 4
            if padding_needed:
                logger.warning("Cursor with incorrect padding detected. Adding padding.")
                cursor += "=" * (4 - padding_needed)

            cursor_data = JSONLoads(base64.b64decode(cursor.encode()).decode())
            return [(field, value) for field, value in cursor_data]
        except binascii.Error:
            logger.warning("Base64 decoding error for cursor value. Starting with empty pagination.")
            return []
        except Exception:
            logger.warning("Unexpected error decoding cursor value. Starting with empty pagination.")
            return []

    @classmethod
    async def create(
        cls,
        model: type[RecordModelType],
        cursor: str | None = None,
        per_page: int = settings.pagination_default_per_page,
        queryset: QuerySet[RecordModelType] | None = None,
    ):
        paginator = cls(model, cursor, per_page)
        return await paginator.paginate(queryset)

    @property
    def has_next(self) -> bool:
        return self.next_cursor is not None

    async def paginate(self, queryset: QuerySet[RecordModelType] | None = None) -> "Pagination[RecordModelType]":
        if queryset is None:
            queryset = self.model.all()

        # Determine the sort fields from the queryset, and Meta class. Default to created_at ASC, add ID as tiebreaker
        queryset_with_default_ordering = self.model.all().order_by(
            *getattr(self.model.Meta, "ordering", ["created_at"])
        )
        self.sort_fields = (queryset._orderings or queryset_with_default_ordering._orderings) + [("id", Order.asc)]

        # Apply the sort fields to the queryset
        queryset._orderings = self.sort_fields

        if self.cursor:
            cursor_values = self.decode_cursor(self.cursor)
            filter = Q()
            for i, (field, value) in enumerate(cursor_values):
                # Null values are not comparable
                if value is None:
                    continue

                sort = next((order for f, order in self.sort_fields if f == field), Order.asc)
                op = "__gt" if sort in [Order.asc, Order.asc.value, "asc", "ASC"] else "__lt"

                # Annotate nullable fields with a max value to ensure they are included in the ordering
                if field_object := self.model._meta.fields_map.get(field):
                    if field_object.null and isinstance(field_object, fields.DatetimeField):
                        queryset = queryset.annotate(**{f"{field}_coalesced": Coalesce(field, datetime.max)})
                        field = f"{field}_coalesced"
                    elif field_object.null and isinstance(field_object, fields.DateField):
                        queryset = queryset.annotate(**{f"{field}_coalesced": Coalesce(field, date.max)})
                        field = f"{field}_coalesced"

                # Build the filter query
                current_filter = Q(**{f"{field}{op}": value})
                for j in range(i):
                    current_filter &= Q(**{str(cursor_values[j][0]): cursor_values[j][1]})
                filter |= current_filter

            queryset = queryset.filter(filter)

        # Fetch one extra item to determine if there's a next page
        self.results = await queryset.limit(self.per_page + 1)

        # If we got an extra item, there's a next page
        if len(self.results) > self.per_page:
            self.results.pop()
            last_item = self.results[-1]
            cursor_values = []
            for field, _ in self.sort_fields:
                raw_value = getattr(last_item, field)
                if field_object := self.model._meta.fields_map.get(field):
                    cursor_values.append((field, field_object.to_python_value(raw_value)))
                else:
                    cursor_values.append((field, raw_value))

            self.next_cursor = self.encode_cursor(cursor_values)

        return self
