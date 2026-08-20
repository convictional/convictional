#!/usr/bin/env python3
import asyncio

from infra.cache import cache
from scripts.helpers import green_text, in_app_lifespan


async def main():
    await cache.clear()
    print(green_text("Cache cleared successfully"))


if __name__ == "__main__":
    asyncio.run(in_app_lifespan(main()))
