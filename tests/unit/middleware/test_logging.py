import logging
from datetime import datetime
from uuid import uuid4 as generate_uuid

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.middleware.logging import LoggingContextMiddleware
from config.logging import LoggingContext, LoggingContextFilter
from tests.helpers.vcr import mark_as_vcr, vcr_config  # noqa

app = FastAPI()
app.add_middleware(LoggingContextMiddleware)


@app.get("/normal")
async def normal_route():
    # Inside of a request, the request context should be set
    assert LoggingContext.get_request() is not None
    return {}


@app.post("/failure")
async def failure_route(request: Request):
    assert LoggingContext.get_request() is not None
    raise Exception("Failure")


@app.get("/with_context")
async def route_with_logging_context():
    # Use LoggingContext manager to set context
    with LoggingContext(user_id="test-user-123", operation="test"):
        # Verify context is set
        context = LoggingContextFilter.get_context()
        assert context is not None
        assert context["user_id"] == "test-user-123"
        assert context["operation"] == "test"
        return {"context": context}


client = TestClient(app, raise_server_exceptions=False)


def test_logging_middleware():
    # Outside of a request, both request and logging context should be None
    assert LoggingContext.get_request() is None
    assert LoggingContextFilter.get_context() is None

    response = client.get("/normal")
    assert response.status_code == 200

    # After request, both contexts should be cleared
    assert LoggingContext.get_request() is None
    assert LoggingContextFilter.get_context() is None

    response = client.post("/failure")
    assert response.status_code == 500

    # Exceptions shall not prevent contexts from being reset
    assert LoggingContext.get_request() is None
    assert LoggingContextFilter.get_context() is None


def test_logging_context_manager():
    # Initially context should be None
    assert LoggingContextFilter.get_context() is None

    # Use LoggingContext manager
    with LoggingContext(user_id="user-123", org_id="org-456"):
        context = LoggingContextFilter.get_context()
        assert context is not None
        assert context["user_id"] == "user-123"
        assert context["org_id"] == "org-456"

        # Test nested context - should merge with parent context
        with LoggingContext(operation="create", model="Decision"):
            nested_context = LoggingContextFilter.get_context()
            assert nested_context is not None
            assert nested_context["operation"] == "create"
            assert nested_context["model"] == "Decision"
            # Parent context should be preserved and merged
            assert nested_context["user_id"] == "user-123"
            assert nested_context["org_id"] == "org-456"

    # After exiting, context should be cleared
    assert LoggingContextFilter.get_context() is None


def test_logging_context_filter():
    filter_instance = LoggingContextFilter()

    # Create a mock log record
    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg="Test message",
        args=(),
        exc_info=None,
    )

    # Test with no context - should not add json_fields
    result = filter_instance.filter(record)
    assert result is True
    assert not hasattr(record, "json_fields")

    # Test with empty context - should not add json_fields
    with LoggingContext():
        result = filter_instance.filter(record)
        assert result is True
        assert not hasattr(record, "json_fields")

    # Test with context data - should add json_fields
    with LoggingContext(user_id="test-123", operation="test"):
        result = filter_instance.filter(record)
        assert result is True
        assert hasattr(record, "json_fields")
        assert record.json_fields == {"user_id": "test-123", "operation": "test"}


def test_logging_context_in_request():
    # Context should be None outside request
    assert LoggingContextFilter.get_context() is None

    # Make request that sets context
    response = client.get("/with_context")
    assert response.status_code == 200

    # Verify context was set during request
    response_data = response.json()
    assert "context" in response_data
    context = response_data["context"]
    assert context["user_id"] == "test-user-123"
    assert context["operation"] == "test"

    # Context should be cleared after request completes (middleware should handle this)
    assert LoggingContextFilter.get_context() is None


def test_logging_context_filter_json_normalization():
    filter_instance = LoggingContextFilter()

    # Test UUIDs and datetimes are normalized to JSON-serializable types
    test_uuid = generate_uuid()
    test_datetime = datetime.now()

    with LoggingContext(user_id=test_uuid, created_at=test_datetime, message="test"):
        record = logging.LogRecord(
            name="test_logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        result = filter_instance.filter(record)
        assert result is True
        assert hasattr(record, "json_fields")

        # Verify UUIDs are converted to strings
        assert record.json_fields["user_id"] == str(test_uuid)
        assert isinstance(record.json_fields["user_id"], str)

        # Verify datetimes are converted to strings
        assert record.json_fields["created_at"] == str(test_datetime)
        assert isinstance(record.json_fields["created_at"], str)

        # Verify regular strings remain unchanged
        assert record.json_fields["message"] == "test"
        assert isinstance(record.json_fields["message"], str)


def test_middleware_sets_user_id_from_session():
    session_app = FastAPI()
    session_app.add_middleware(LoggingContextMiddleware)

    @session_app.middleware("http")
    async def inject_session(request: Request, call_next):
        request.scope["session"] = {"user_id": "session-user-42"}
        return await call_next(request)

    @session_app.get("/with_session")
    async def with_session():
        context = LoggingContextFilter.get_context()
        return {"context": context}

    session_client = TestClient(session_app)
    response = session_client.get("/with_session")
    assert response.status_code == 200
    context = response.json()["context"]
    assert context["user_id"] == "session-user-42"
