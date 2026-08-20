from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from freezegun import freeze_time

from app.models.commands import ScheduledResearch
from config.enums import ResearchSource, ScheduledResearchFrequency
from infra.db import allow_soft_deleted
from tests.helpers.factories import create_scheduled_research, create_user


@pytest.mark.asyncio
async def test_schedule_cron_round_trip_for_all_frequencies():
    daily = await create_scheduled_research(schedule_cron="0 7 * * *")
    weekly = await create_scheduled_research(schedule_cron="0 14 * * 3")
    weekdays = await create_scheduled_research(schedule_cron="0 9 * * 1-5")

    assert daily.frequency == ScheduledResearchFrequency.DAILY
    assert daily.hour == 7
    assert daily.day_of_week is None

    assert weekly.frequency == ScheduledResearchFrequency.WEEKLY
    assert weekly.hour == 14
    assert weekly.day_of_week == "3"

    assert weekdays.frequency == ScheduledResearchFrequency.WEEKDAYS
    assert weekdays.hour == 9
    assert weekdays.day_of_week is None


@pytest.mark.asyncio
async def test_set_schedule_builds_correct_cron_for_each_frequency():
    schedule = await create_scheduled_research()

    schedule.set_schedule(ScheduledResearchFrequency.DAILY, 8)
    assert schedule.schedule_cron == "0 8 * * *"

    schedule.set_schedule(ScheduledResearchFrequency.WEEKLY, 9, "2")
    assert schedule.schedule_cron == "0 9 * * 2"

    schedule.set_schedule(ScheduledResearchFrequency.WEEKDAYS, 6)
    assert schedule.schedule_cron == "0 6 * * 1-5"


@pytest.mark.asyncio
async def test_validate_schedule_rejects_bad_input():
    schedule = ScheduledResearch()

    assert schedule.validate_schedule(ScheduledResearchFrequency.DAILY, 8) is None
    assert schedule.validate_schedule(ScheduledResearchFrequency.DAILY, 25) is not None
    assert schedule.validate_schedule(ScheduledResearchFrequency.WEEKLY, 9, None) is not None
    assert schedule.validate_schedule(ScheduledResearchFrequency.WEEKLY, 9, "7") is not None
    assert schedule.validate_schedule(ScheduledResearchFrequency.WEEKLY, 9, "3") is None
    assert schedule.validate_schedule(ScheduledResearchFrequency.WEEKDAYS, 9) is None


@pytest.mark.asyncio
async def test_weekly_requires_day_of_week_when_building_cron():
    schedule = ScheduledResearch()
    with pytest.raises(ValueError):
        schedule.set_schedule(ScheduledResearchFrequency.WEEKLY, 9, None)


@pytest.mark.asyncio
@freeze_time("2026-04-15 09:10:00", tz_offset=0)  # Wednesday, 9:10 UTC, inside the 9:00 Wed recurrence window
async def test_is_recurring_now_and_last_refresh_scheduled_at_inside_window():
    # Weekly on Wednesday at 9:00 UTC
    schedule = await create_scheduled_research(schedule_cron="0 9 * * 3")
    await schedule.fetch_related("creator")

    assert schedule.is_recurring_now is True
    # Inside the window → last_refresh_scheduled_at points to the *current* fire (the one we're handling
    # right now). The idempotency gate compares last_delivered_at against this; pointing at the prior tick
    # would skip every schedule on the recurring path because last_delivered_at from the previous cycle is
    # always >= the prior tick.
    assert schedule.last_refresh_scheduled_at == datetime(2026, 4, 15, 9, 0, tzinfo=UTC)


@pytest.mark.asyncio
@freeze_time("2026-04-15 11:00:00", tz_offset=0)  # Wednesday, 11:00 UTC, well past the 1-hour window
async def test_is_recurring_now_false_outside_window():
    schedule = await create_scheduled_research(schedule_cron="0 9 * * 3")
    await schedule.fetch_related("creator")

    assert schedule.is_recurring_now is False


@pytest.mark.asyncio
async def test_timezone_uses_creator_time_zone_when_set():
    user = await create_user(time_zone="America/New_York")
    schedule = await create_scheduled_research(creator_id=user.id, organization_id=user.organization_id)
    await schedule.fetch_related("creator")

    assert schedule.timezone == ZoneInfo("America/New_York")


@pytest.mark.asyncio
async def test_timezone_falls_back_to_utc_when_unset_or_invalid():
    user = await create_user(time_zone=None)
    schedule = await create_scheduled_research(creator_id=user.id, organization_id=user.organization_id)
    await schedule.fetch_related("creator")

    assert schedule.timezone == ZoneInfo("UTC")

    invalid_user = await create_user(time_zone="Not/A/Real/Zone")
    invalid_schedule = await create_scheduled_research(
        creator_id=invalid_user.id, organization_id=invalid_user.organization_id
    )
    await invalid_schedule.fetch_related("creator")

    assert invalid_schedule.timezone == ZoneInfo("UTC")


@pytest.mark.asyncio
async def test_effective_topic_prompt_falls_back_to_prompt_until_prepared():
    schedule = await create_scheduled_research(prompt="Raw user prompt", topic_prompt=None)
    assert schedule.effective_topic_prompt == "Raw user prompt"

    schedule.topic_prompt = "Refined topic"
    assert schedule.effective_topic_prompt == "Refined topic"


@pytest.mark.asyncio
async def test_is_untitled_until_title_changes():
    schedule = await create_scheduled_research()
    assert schedule.is_untitled is True
    assert schedule.title == "Untitled"

    schedule.title = "Quarterly SaaS trends"
    assert schedule.is_untitled is False


@pytest.mark.asyncio
async def test_schedule_description_for_each_frequency():
    daily = await create_scheduled_research(schedule_cron="0 7 * * *")
    weekly = await create_scheduled_research(schedule_cron="0 14 * * 3")
    weekdays = await create_scheduled_research(schedule_cron="0 9 * * 1-5")

    assert "Daily" in daily.schedule_description
    assert "07:00" in daily.schedule_description
    assert "Wednesday" in weekly.schedule_description
    assert "14:00" in weekly.schedule_description
    assert "Weekdays" in weekdays.schedule_description
    assert "09:00" in weekdays.schedule_description


@pytest.mark.asyncio
async def test_soft_delete_excludes_from_default_queryset():
    schedule = await create_scheduled_research()
    assert await ScheduledResearch.filter(id=schedule.id).count() == 1

    await schedule.soft_delete()
    assert await ScheduledResearch.filter(id=schedule.id).count() == 0

    async with allow_soft_deleted():
        assert await ScheduledResearch.filter(id=schedule.id).count() == 1


@pytest.mark.asyncio
async def test_sources_field_persists_as_list():
    schedule = await create_scheduled_research(sources=[ResearchSource.INTERNAL, ResearchSource.SLACK])
    refreshed = await ScheduledResearch.get(id=schedule.id)
    assert ResearchSource.INTERNAL in refreshed.sources
    assert ResearchSource.SLACK in refreshed.sources
