import multiprocessing
import warnings

from anthropic._models import construct_type
from anthropic.types import RawMessageStreamEvent

# starlette 1.3's TestClient prefers `httpx2` (Pydantic's renamed fork of the now-stalled
# `httpx`) and warns when falling back to `httpx`. We can't move: `httpx2` is a separate, ~month-old
# distribution and our whole dep graph (anthropic, openai, mcp, notion-client, httpx-ws, svix, …)
# still requires `httpx`. We don't even use starlette's TestClient — AppClient builds on
# httpx.AsyncClient directly — so the warning is moot. Filter here (before any test module imports
# `fastapi.testclient`) rather than in the integration conftest, which loads later.
warnings.filterwarnings(
    "ignore",
    message="Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.",
    category=UserWarning,
)

# Pre-build anthropic's deferred pydantic schemas before any tests run.
# anthropic 0.81.0 uses defer_build=True on its BaseModel. When freezegun patches
# datetime.datetime before these schemas are built, pydantic fails with
# "Unable to generate pydantic-core schema for <class 'datetime.datetime'>".
try:
    construct_type(type_=RawMessageStreamEvent, value={"type": "message_start", "message": {}})
except Exception:
    pass


def pytest_xdist_auto_num_workers():
    return max(1, multiprocessing.cpu_count() - 1)
