from datetime import date, datetime
from zoneinfo import ZoneInfo

from freezegun import freeze_time

from app.helpers.datetimes import (
    default_snooze_times,
    format_date,
    format_datetime,
)


def test_format_datetime():
    # Test with default parameters
    instance = datetime(2023, 5, 15, 14, 30, tzinfo=ZoneInfo("UTC"))
    assert format_datetime(instance) == "5/15/2023 2:30PM"

    # Test with custom format
    assert format_datetime(instance, format="date") == "5/15/2023"

    # Test with custom timezone
    assert format_datetime(instance, timezone=ZoneInfo("America/New_York")) == "5/15/2023 10:30AM"

    # Test with None value
    assert format_datetime(None) == ""


def test_format_date():
    instance = date(2023, 5, 15)
    assert format_date(instance, "date") == "5/15/2023"
    assert format_date(instance, "date_iso_8601") == "2023-05-15"
    assert format_date(instance, "%Y-%m-%d") == "2023-05-15"

    # Test with None value
    assert format_date(None, "date") == ""


def test_format_date_timezone_conversion():
    # A UTC calendar date rendered in PST shifts back a day: 2025-02-13 00:00 UTC
    # is 2025-02-12 in Los Angeles. format_date must convert before formatting.
    pst = ZoneInfo("America/Los_Angeles")
    event_date = datetime(2025, 2, 13, 0, 30, tzinfo=ZoneInfo("UTC")).date()

    assert format_date(event_date, "date", timezone=pst) == "2/12/2025"


def test_default_snooze_times():
    """Test default_snooze_times with different timezones and edge cases"""

    # Test on Friday afternoon (March 15, 2024 is EDT/PDT — DST started March 10)
    with freeze_time("2024-03-15 14:30:00"):  # Friday at 2:30 PM UTC
        # Test with UTC (default)
        utc_times = default_snooze_times()
        assert len(utc_times) == 3
        assert utc_times[0]["value"] == "2024-03-15T16:30+00:00"
        assert utc_times[0]["description"] == "Two hours from now"
        assert utc_times[1]["value"] == "2024-03-16T09:00+00:00"
        assert utc_times[1]["description"] == "Tomorrow morning (9am)"
        assert utc_times[2]["value"] == "2024-03-18T09:00+00:00"  # Monday (Friday + 3 days)
        assert utc_times[2]["description"] == "Next week (Monday 9am)"

        # Test with Eastern timezone (EDT = UTC-4)
        est_times = default_snooze_times(ZoneInfo("America/New_York"))
        assert est_times[0]["value"] == "2024-03-15T12:30-04:00"  # 10:30 AM EDT + 2 hours
        assert est_times[1]["value"] == "2024-03-16T09:00-04:00"  # Tomorrow 9 AM EDT
        assert est_times[2]["value"] == "2024-03-18T09:00-04:00"  # Next Monday 9 AM EDT

        # Test with Pacific timezone (PDT = UTC-7)
        pst_times = default_snooze_times(ZoneInfo("America/Los_Angeles"))
        assert pst_times[0]["value"] == "2024-03-15T09:30-07:00"  # 7:30 AM PDT + 2 hours
        assert pst_times[1]["value"] == "2024-03-16T09:00-07:00"  # Tomorrow 9 AM PDT
        assert pst_times[2]["value"] == "2024-03-18T09:00-07:00"  # Next Monday 9 AM PDT

    # Test edge case: Monday evening
    with freeze_time("2024-03-18 22:15:00"):  # Monday at 10:15 PM UTC
        times = default_snooze_times()
        assert times[0]["value"] == "2024-03-19T00:15+00:00"  # Two hours = midnight next day
        assert times[1]["value"] == "2024-03-19T09:00+00:00"  # Tomorrow morning (Tuesday)
        assert times[2]["value"] == "2024-03-25T09:00+00:00"  # Next Monday (7 days later)

    # Test edge case: Sunday morning
    with freeze_time("2024-03-17 08:45:00"):  # Sunday at 8:45 AM UTC
        times = default_snooze_times()
        assert times[0]["value"] == "2024-03-17T10:45+00:00"  # Two hours = same day
        assert times[1]["value"] == "2024-03-18T09:00+00:00"  # Tomorrow morning (Monday)
        assert times[2]["value"] == "2024-03-18T09:00+00:00"  # Next Monday is tomorrow
