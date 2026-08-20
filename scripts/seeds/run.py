#!/usr/bin/env python3

import argparse
import asyncio
import importlib
import pkgutil
import sys
from collections.abc import Callable, Coroutine
from uuid import UUID

from tortoise.transactions import in_transaction

import scripts.seeds as _seeds_pkg
from app.jobs.maintenance import IndexSearchJob
from infra.jobs import JobsOutbox, asyncio_jobs
from scripts.helpers import green_text, in_database_context, in_subscription_context, yellow_text
from scripts.seeds.hooks import register as _register_hooks
from scripts.seeds.seeder import Seeder

_register_hooks()

CONTENT_INDEXING_TIMEOUT = 150


def _discover_scenarios() -> dict[str, Callable[[], Coroutine]]:
    scenarios = {}
    for _, name, is_pkg in pkgutil.iter_modules(_seeds_pkg.__path__, _seeds_pkg.__name__ + "."):
        if not is_pkg:
            continue
        module = importlib.import_module(name)
        fn = getattr(module, "seed", None)
        if callable(fn):
            scenarios[name.rsplit(".", 1)[-1]] = fn
    return scenarios


class _DryRunError(Exception):
    pass


async def _index_search_content(organization_ids: set[UUID]):
    if not organization_ids:
        return
    print("Indexing search content...")
    async with JobsOutbox():
        for org_id in organization_ids:
            await IndexSearchJob(organization_id=org_id).perform()
    await asyncio_jobs.wait_for_all(timeout=CONTENT_INDEXING_TIMEOUT)
    print(green_text("Search content indexed"))


def _resolve_scenarios(scenario_names: list[str] | None = None) -> dict[str, Callable]:
    scenarios = _discover_scenarios()
    if not scenario_names:
        return scenarios

    resolved = {}
    for name in scenario_names:
        if name not in scenarios:
            print(f"Unknown scenario: {name}")
            print(f"Available: {', '.join(scenarios.keys())}")
            sys.exit(1)
        resolved[name] = scenarios[name]
    return resolved


async def _dry_run_scenarios(to_run: dict[str, Callable]):
    try:
        async with in_transaction("default"):
            for name, fn in to_run.items():
                print(green_text(f"\n▶ Dry run: {name}"))
                async with Seeder(namespace=name) as seeder:
                    await fn()
                seeder.print_summary()
            raise _DryRunError()
    except _DryRunError:
        print(green_text("\nDry run passed — all changes rolled back."))


async def run_scenarios(scenario_names: list[str] | None = None, *, dry_run: bool = False):
    to_run = _resolve_scenarios(scenario_names)

    if dry_run:
        await _dry_run_scenarios(to_run)
        return

    for name, fn in to_run.items():
        print(green_text(f"\n▶ Running scenario: {name}"))
        async with Seeder(namespace=name) as seeder:
            async with in_transaction("default"):
                await fn()
        seeder.print_summary()
        await _index_search_content(seeder.organization_ids)

    print(green_text(f"\nDone. Ran {len(to_run)} scenario(s)."))


def list_scenarios():
    scenarios = _discover_scenarios()
    if not scenarios:
        print(yellow_text("No scenarios found."))
        return

    print("Available scenarios:")
    for name in scenarios:
        print(f"  - {name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed demo data using scenarios")
    parser.add_argument("scenarios", nargs="*", help="Scenario names to run (default: all)")
    parser.add_argument("--list", action="store_true", help="List available scenarios")
    parser.add_argument("--dry-run", action="store_true", help="Validate without persisting")
    args = parser.parse_args()

    if args.list:
        list_scenarios()
    else:
        names = args.scenarios if args.scenarios else None
        asyncio.run(in_database_context(in_subscription_context(run_scenarios(names, dry_run=args.dry_run))))
