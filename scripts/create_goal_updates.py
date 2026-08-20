import asyncio

from app.jobs.goals import GenerateGoalUpdatesJob
from app.models.accounts import Organization
from infra.jobs import JobsOutbox
from scripts.helpers import in_app_lifespan


async def main():
    org = await Organization.all().first()
    if org is None:
        print("No organization found.")
        return

    print("Generating goal updates...")

    async with JobsOutbox():
        job = GenerateGoalUpdatesJob(organization_id=org.id)
        await job.perform()

    current_task = asyncio.current_task()
    pending_tasks = [task for task in asyncio.all_tasks() if not task.done() and task != current_task]
    if pending_tasks:
        await asyncio.gather(*pending_tasks, return_exceptions=True)

    print("Goal update generation completed!")


if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    loop.run_until_complete(in_app_lifespan(main()))
