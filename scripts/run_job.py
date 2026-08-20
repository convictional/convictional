#!/usr/bin/env python3
import argparse
import asyncio
import json

from infra.jobs import JobsOutbox, asyncio_jobs, job_registry
from scripts.helpers import in_app_lifespan


def format_jobs_list() -> str:
    jobs = sorted(job_registry.keys())

    # Calculate column width based on longest job name plus padding
    max_job_length = max(len(job) for job in jobs)
    column_width = max_job_length + 2  # Add 2 for spacing

    # Calculate how many rows we need for 3 columns
    num_jobs = len(jobs)
    rows_per_column = (num_jobs + 2) // 3  # Round up division

    # Split jobs into 3 columns, each sorted vertically
    columns = []
    for col in range(3):
        start_idx = col * rows_per_column
        end_idx = min((col + 1) * rows_per_column, num_jobs)
        columns.append(jobs[start_idx:end_idx])

    # Format output with jobs arranged vertically in columns
    output_lines = []
    max_rows = max(len(col) for col in columns)

    for row in range(max_rows):
        row_jobs = []
        for column in columns:
            if row < len(column):
                row_jobs.append(column[row])
            else:
                row_jobs.append("")  # Empty cell for shorter columns

        # Pad each job name to calculated width for proper column alignment
        formatted_jobs = [f"{job:<{column_width}}" for job in row_jobs]
        output_lines.append("  " + "".join(formatted_jobs).rstrip())

    return "\n".join(output_lines)


class CustomHelpFormatter(argparse.RawDescriptionHelpFormatter):
    def _format_usage(self, usage, actions, groups, prefix):
        if prefix is None:
            prefix = "usage: "

        for action in actions:
            if hasattr(action, "choices") and action.choices and len(action.choices) > 10:
                action.metavar = "JOB_TYPE"

        return super()._format_usage(usage, actions, groups, prefix)


def create_parser() -> argparse.ArgumentParser:
    jobs_list = format_jobs_list()

    parser = argparse.ArgumentParser(
        description="Run background jobs",
        formatter_class=CustomHelpFormatter,
        epilog=f"""Available jobs:
{jobs_list}

Example:
  python scripts/run_job.py generate_update '{{"organization_id": "123e4567-e89b-12d3-a456-426614174000"}}'""",
    )

    parser.add_argument(
        "job_type", help="Type of job to run (see list below)", choices=sorted(job_registry.keys()), metavar="JOB_TYPE"
    )

    parser.add_argument("properties", nargs="?", default="{}", help="JSON properties for the job (default: '{}')")

    return parser


async def main():
    parser = create_parser()
    args = parser.parse_args()

    try:
        job_properties = json.loads(args.properties)
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON properties: {e}")
        return

    job_class = job_registry.get(args.job_type)
    if not job_class:
        print(f"Job '{args.job_type}' not found.")
        return

    try:
        print(f"Running {args.job_type} job with properties: {job_properties}")
        # Mirror the request lifecycle: jobs enqueued during perform() land in the
        # JobsOutbox, and exiting the context flushes them to the runner. Without
        # this, follow-on work — e.g. the mention emails a notify job enqueues — is
        # silently dropped.
        async with JobsOutbox():
            job = job_class(**job_properties)
            await job.perform()
        # Under the asyncio runner those follow-on jobs (and any they enqueue in
        # turn) run as detached tasks; wait for them before we return, or the app
        # lifespan closes the DB pool out from under them ("pool is closing"). A
        # no-op under runners that don't spawn tasks.
        await asyncio_jobs.wait_for_all()
        # wait_for_all swallows task exceptions, so surface any follow-on failures
        # rather than reporting success for a partial run.
        if asyncio_jobs.failed:
            for failed_job, exc in asyncio_jobs.failed:
                print(f"Follow-on job {failed_job.job_type} failed: {exc}")
            raise RuntimeError(f"{len(asyncio_jobs.failed)} follow-on job(s) failed")
        print(f"Job {args.job_type} completed successfully")
    except Exception as e:
        print(f"Job {args.job_type} failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(in_app_lifespan(main()))
