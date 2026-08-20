import logging
import warnings

import pytest
from fastapi.routing import iter_route_contexts

from app.main import app
from config import settings
from config.settings import EmbeddingBackend
from infra.email import fake_delivery, get_email_client
from infra.jobs import inline_jobs
from infra.push import fake_push_delivery
from tests.helpers.app import client, custom_settings, setup_app_lifespan  # noqa: F401
from tests.helpers.cache import use_postgres_cache  # noqa: F401
from tests.helpers.vcr import mark_as_vcr, vcr_config  # noqa: F401

# Suppress specific deprecation warnings
warnings.filterwarnings(
    "ignore",
    message="Since the introduction of custom time granularity, the `TimeGranularity` enum is deprecated."
    " Please just use strings to represent time grains.",
    category=DeprecationWarning,
    module="dbtsl.models.base",
)

# The notion integration tests deliberately exercise error responses (invalid token, rate
# limits, validation errors). notion_client logs each failed request at WARNING, which is
# expected noise in those tests. It resets its own logger level to WARNING on every client
# construction, so raising the level here wouldn't stick — a filter isn't reset, so use one.
logging.getLogger("notion_client").addFilter(lambda record: False)


@pytest.fixture(scope="session", autouse=True)
def _warm_route_schemas():
    # FastAPI 0.136+ builds each route's pydantic response field lazily on first
    # route match instead of at include_router() time. Tests that run under
    # `freeze_time` monkeypatch `datetime`, so if a route is matched for the first
    # time while time is frozen, pydantic-core can't build a schema for the faked
    # datetime and raises PydanticSchemaGenerationError (surfacing as a 1011
    # WebSocket close or a 500). Exhausting FastAPI's route traversal here builds
    # and caches every route's schema once, before any test freezes time.
    #
    # Mirrors the anthropic deferred-schema pre-build in tests/conftest.py.
    #
    # REMOVE WHEN this is no longer needed — likely after a FastAPI upgrade that
    # restores eager response-field building, or if freeze_time is dropped from
    # route-exercising tests. To check: delete this fixture and run the frozen
    # channel tests, e.g.
    #     make test ARGS="tests/integration/channels/test_mailbox_views.py"
    # If they still pass, this workaround is obsolete and should be deleted.
    for _ in iter_route_contexts(app.routes):
        pass


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    def is_in_integration_package(item: pytest.Item) -> bool:
        for node in item.listchain():
            if isinstance(node, pytest.Package) and node.name == "integration":
                return True

        return False

    for item in items:
        if is_in_integration_package(item) and not any(marker.name == "disable_vcr" for marker in item.iter_markers()):
            mark_as_vcr(config, [item])


def pytest_configure(config: pytest.Config) -> None:
    # Skip if timeout was explicitly set via command line
    if config.option.timeout is not None:
        return

    # If VCR record-mode is set to 'rewrite', disable timeout to allow for network calls
    record_mode = config.getoption("--record-mode", default="new_episodes")
    if record_mode == "rewrite":
        config.option.timeout = 0

    # Otherwise, use the timeout configured in pyproject.toml (tool.pytest.ini_options)


#
# Fixtures
#
#


@pytest.fixture(scope="function", autouse=True)
def _embedding_backend(request):
    # Content indexing embeds text as a side effect of nearly every create/update,
    # so integration tests default to the fake backend (.env.test) to avoid recording
    # OpenAI calls no test relies on. Tests that assert on semantic search or ranking
    # opt into the recorded OpenAI vectors with @pytest.mark.real_embeddings.
    if request.node.get_closest_marker("real_embeddings"):
        with settings.override():
            settings.embedding_backend = EmbeddingBackend.OPENAI
            yield
    else:
        yield


@pytest.fixture(scope="function", autouse=True)
def background_jobs():
    inline_jobs.reset()
    yield inline_jobs
    inline_jobs.raise_first_failed()


@pytest.fixture(scope="function")
def email_delivery():
    fake_delivery.reset()
    return fake_delivery


@pytest.fixture(scope="function")
def email_client(email_delivery):
    return get_email_client()


@pytest.fixture(scope="function")
def push_delivery():
    fake_push_delivery.reset()
    return fake_push_delivery


@pytest.fixture
def push_enabled():
    # Push is off by default (the kill-switch); tests that assert push opt in explicitly.
    with settings.override():
        settings.push_enabled = True
        yield
