#!/usr/bin/env python3
import asyncio

from app.models.accounts import User
from integrations.recall_ai.jobs import CreateUpcomingMeetingsForUserJob
from integrations.recall_ai.models import RecallAICalendarUser
from scripts.helpers import in_app_lifespan


async def main():
    calendar_users = await RecallAICalendarUser.all()
    connected_calendar_users = [calendar_user for calendar_user in calendar_users if calendar_user.is_connected]
    users = await User.filter(id__in=[calendar_user.user_id for calendar_user in connected_calendar_users])
    for user in users:
        await CreateUpcomingMeetingsForUserJob(user_id=user.id).perform()


if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    loop.run_until_complete(in_app_lifespan(main()))
