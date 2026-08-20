from typing import Any

from IPython import get_ipython
from IPython.core.async_helpers import get_asyncio_loop

from app.main import app, lifespan

console_lifespan = lifespan(app)

loop = get_asyncio_loop()
loop.run_until_complete(console_lifespan.__aenter__())


def on_exit(info: Any):
    global console_lifespan
    if hasattr(info, "raw_cell") and info.raw_cell.strip() in ("quit", "exit"):
        loop.run_until_complete(console_lifespan.__aexit__(None, None, None))


ipython = get_ipython()
if not ipython:
    raise RuntimeError("IPython environment is not available.")
ipython.events.register("pre_run_cell", on_exit)
