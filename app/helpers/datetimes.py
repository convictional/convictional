from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

DATETIME_FORMATS = {
    "date": "%-m/%-d/%Y",  # 8/21/2024
    "date_iso_8601": "%Y-%m-%d",  # 2024-08-21
    "date_medium": "%b %-d %Y",  # Aug 21 2024
    "time": "%-I:%M%p",  # 3:14PM
    "datetime": "%-m/%-d/%Y %-I:%M%p",  # 8/21/2024 3:14PM
    "datetime_iso_8601": "%Y-%m-%dT%H:%M:%S%z",  # 2024-08-21T15:14:00
    "datetime_long": "%B %-d, %Y at %-I:%M %p",  # August 21, 2024 at 3:14 PM
    "full_weekday_full_month_day": "%A, %B %-d",  # Wednesday, August 21
    "short_month_day_year_time": "%b %-d %Y, %-I:%M %p",  # Aug 21 2024, 3:14 PM
    "day_of_week": "%A",  # Wednesday
    "month_day": "%b %-d",  # Aug 4
}


def format_datetime(
    value: datetime | None,
    format: str | None = "datetime",
    timezone: ZoneInfo | str = ZoneInfo("UTC"),
):
    if value is None:
        return ""

    if isinstance(timezone, str):
        timezone = ZoneInfo(timezone)
    localized = value.astimezone(timezone)

    if format == "isoformat":
        return localized.isoformat()
    if format in DATETIME_FORMATS:
        format = DATETIME_FORMATS[format]
    if not format:
        format = DATETIME_FORMATS["datetime"]

    return localized.strftime(format)


def format_date(value: date | None, format: str, timezone: ZoneInfo | str = ZoneInfo("UTC")):
    if value is None:
        return ""

    if isinstance(timezone, str):
        timezone = ZoneInfo(timezone)

    utc = ZoneInfo("UTC")
    value = datetime.combine(value, time.min, tzinfo=utc).astimezone(timezone).date()

    if format in DATETIME_FORMATS:
        format = DATETIME_FORMATS[format]
    if not format:
        format = DATETIME_FORMATS["datetime"]

    return value.strftime(format)


def now(timezone: ZoneInfo = ZoneInfo("UTC")):
    return datetime.now(timezone)


def today(timezone: ZoneInfo = ZoneInfo("UTC")) -> date:
    return now(timezone).date()


def tomorrow(timezone: ZoneInfo = ZoneInfo("UTC")) -> date:
    return today(timezone) + timedelta(days=1)


def default_snooze_times(timezone: ZoneInfo = ZoneInfo("UTC")):
    now = datetime.now(timezone)
    two_hours = (now + timedelta(hours=2)).isoformat(timespec="minutes")
    tomorrow_morning = (now + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
    next_week = (now + timedelta(days=(7 - now.weekday()))).replace(hour=9, minute=0, second=0, microsecond=0)

    return [
        {"value": two_hours, "description": "Two hours from now"},
        {"value": tomorrow_morning.isoformat(timespec="minutes"), "description": "Tomorrow morning (9am)"},
        {"value": next_week.isoformat(timespec="minutes"), "description": "Next week (Monday 9am)"},
    ]
