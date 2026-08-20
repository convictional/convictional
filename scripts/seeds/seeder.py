from collections.abc import Callable
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, TypeVar
from uuid import UUID, uuid5

from tortoise.exceptions import DoesNotExist

from app.models.accounts import Organization
from infra.db import RecordModel


@dataclass(frozen=True)
class Ref:
    key: str

    @property
    def id(self) -> UUID:
        return seed_id(f"{_current.get().namespace}-{self.key}")


M = TypeVar("M", bound=RecordModel)

_current: ContextVar["Seeder"] = ContextVar("seed_ctx")

SEED_NAMESPACE = UUID("b3e0d842-7a3f-4c1e-9f6a-8d2b5e1c7f4a")

# Markers that identify a GCS signed URL. Persisting one in seed content rots
# the data after the 24h signing window — block it at insert time.
_GCS_SIGNED_URL_MARKERS = ("x-goog-signature=", "googleaccessid=")

_pre_create: dict[type[RecordModel], list[Callable]] = {}
_post_create: dict[type[RecordModel], list[Callable]] = {}


def _assert_no_signed_gcs_urls(model: type[RecordModel], seed_key: str, values: dict[str, Any]) -> None:
    for name, value in values.items():
        if not isinstance(value, str):
            continue
        lowered = value.lower()
        if any(marker in lowered for marker in _GCS_SIGNED_URL_MARKERS):
            raise ValueError(
                f"Seed '{seed_key}' on {model.__name__}.{name} contains a signed GCS URL. "
                "Signed URLs expire and rot demo data — store a FileReference.id and resolve "
                "the URL at request time instead."
            )


def before_create(*models: type[RecordModel]):
    def decorator(fn):
        for model in models:
            _pre_create.setdefault(model, []).append(fn)
        return fn

    return decorator


def after_create(*models: type[RecordModel]):
    def decorator(fn):
        for model in models:
            _post_create.setdefault(model, []).append(fn)
        return fn

    return decorator


class SeedError(Exception):
    def __init__(self, model: type, seed_key: str, fields: dict[str, Any], scenario: str, cause: Exception):
        self.model = model
        self.seed_key = seed_key
        self.fields = fields
        self.scenario = scenario
        self.cause = cause
        provided = ", ".join(sorted(fields.keys()))
        super().__init__(
            f"{model.__name__}.create() failed for seed key '{seed_key}'\n"
            f"  Scenario: scripts/seeds/{scenario}/\n"
            f"  Fields provided: {provided}\n"
            f"  Error: {cause}"
        )


def seed_id(name: str) -> UUID:
    return uuid5(SEED_NAMESPACE, name)


@dataclass
class Seeder:
    namespace: str
    _defaults: dict[str, Any] = field(default_factory=dict)
    _model_defaults: dict[type[RecordModel], dict[str, Any]] = field(default_factory=dict)
    _prefix: str = ""
    organization_ids: set[UUID] = field(default_factory=set)
    _created: int = 0
    _existing: int = 0

    @contextmanager
    def prefix(self, key_prefix: str):
        old = self._prefix
        self._prefix = f"{old}{key_prefix}-"
        try:
            yield
        finally:
            self._prefix = old

    @contextmanager
    def fields(self, model: type[RecordModel] | None = None, **kwargs: Any):
        if model is None:
            previous = self._defaults.copy()
            self._defaults.update(kwargs)
            try:
                yield
            finally:
                self._defaults = previous
            return

        previous = self._model_defaults.get(model, {}).copy()
        self._model_defaults.setdefault(model, {}).update(kwargs)
        try:
            yield
        finally:
            if previous:
                self._model_defaults[model] = previous
            else:
                self._model_defaults.pop(model, None)

    async def seed(self, model: type[M], key: str, **kwargs: Any) -> M:
        full_key = f"{self.namespace}-{self._prefix}{key}"
        record_id = seed_id(full_key)

        try:
            instance = await model.get(id=record_id)
            self._existing += 1
        except DoesNotExist:
            merged = {**self._defaults, **self._model_defaults.get(model, {}), **kwargs}
            meta: dict[str, Any] = {}
            for hook in _pre_create.get(model, []):
                await hook(merged, namespace=self.namespace, meta=meta)
            resolved: dict[str, Any] = {}
            for k, v in merged.items():
                if isinstance(v, RecordModel):
                    resolved[f"{k}_id"] = v.id
                elif isinstance(v, Ref):
                    resolved[f"{k}_id"] = v.id
                else:
                    resolved[k] = v
            _assert_no_signed_gcs_urls(model, full_key, resolved)
            try:
                instance = await model.create(id=record_id, **resolved)
            except Exception as e:
                raise SeedError(model, full_key, resolved, self.namespace, e) from e
            for hook in _post_create.get(model, []):
                await hook(instance, merged=merged, key=key, namespace=self.namespace, meta=meta)
            self._created += 1

        if isinstance(instance, Organization):
            self.organization_ids.add(instance.id)
        return instance

    def print_summary(self):
        parts = []
        if self._created:
            parts.append(f"{self._created} created")
        if self._existing:
            parts.append(f"{self._existing} existing")
        print(f"  {', '.join(parts)}")

    async def __aenter__(self):
        self._token = _current.set(self)
        return self

    async def __aexit__(self, *_):
        _current.reset(self._token)


async def create[M: RecordModel](model: type[M], key: str, **kwargs: Any) -> M:
    """Create a record with a deterministic ID, or return the existing one."""
    return await _current.get().seed(model, key, **kwargs)


@contextmanager
def fields(model: type[RecordModel] | None = None, **kwargs: Any):
    """Set default field values. Scope to a model or omit for global defaults."""
    with _current.get().fields(model, **kwargs):
        yield


@contextmanager
def prefix(key_prefix: str):
    """Auto-prefix all seed keys within this block. Nests."""
    with _current.get().prefix(key_prefix):
        yield
