"""Reindex all search content from scratch.

Usage: make reindex_search
"""

import asyncio

from app.jobs.maintenance import IndexSearchJob
from infra.jobs import JobsOutbox, asyncio_jobs
from scripts.helpers import green_text, in_app_lifespan

TIMEOUT = 300  # seconds


async def main():
    print("Reindexing all search content...")

    async with JobsOutbox():
        await IndexSearchJob().perform()

    await asyncio_jobs.wait_for_all(timeout=TIMEOUT)
    print(green_text("Search reindexing complete"))


if __name__ == "__main__":
    asyncio.run(in_app_lifespan(main()))
