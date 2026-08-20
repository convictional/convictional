from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

from app.jobs.content import MERGE_THRESHOLD, SPLIT_TARGET, SPLIT_THRESHOLD, IndexChatHistoryJob

build_adaptive_windows = IndexChatHistoryJob.build_adaptive_windows


def _make_message(created_at: datetime) -> MagicMock:
    msg = MagicMock()
    msg.created_at = created_at
    msg.user.display_name = "Alice"
    msg.content = "test message"
    return msg


def _make_messages_on_date(dt: datetime, count: int) -> list[MagicMock]:
    return [_make_message(dt + timedelta(minutes=i)) for i in range(count)]


def test_build_adaptive_windows_empty():
    assert build_adaptive_windows([]) == []


def test_build_adaptive_windows_single_day_above_merge_threshold():
    base = datetime(2026, 3, 1, 10, 0, tzinfo=UTC)
    messages = _make_messages_on_date(base, MERGE_THRESHOLD + 1)
    windows = build_adaptive_windows(messages)
    assert len(windows) == 1
    assert len(windows[0].messages) == MERGE_THRESHOLD + 1
    assert windows[0].sequence is None


def test_build_adaptive_windows_thin_days_merge():
    day1 = datetime(2026, 3, 1, 10, 0, tzinfo=UTC)
    day2 = datetime(2026, 3, 2, 10, 0, tzinfo=UTC)
    messages = _make_messages_on_date(day1, 3) + _make_messages_on_date(day2, 10)
    windows = build_adaptive_windows(messages)
    assert len(windows) == 1
    assert len(windows[0].messages) == 13


def test_build_adaptive_windows_multiple_thin_days_merge():
    messages = []
    for day_offset in range(4):
        dt = datetime(2026, 3, 1 + day_offset, 10, 0, tzinfo=UTC)
        messages.extend(_make_messages_on_date(dt, 2))
    windows = build_adaptive_windows(messages)
    assert len(windows) == 1
    assert len(windows[0].messages) == 8


def test_build_adaptive_windows_heavy_day_splits():
    base = datetime(2026, 3, 1, 10, 0, tzinfo=UTC)
    count = SPLIT_THRESHOLD + 20
    messages = _make_messages_on_date(base, count)
    windows = build_adaptive_windows(messages)
    assert len(windows) > 1
    for window in windows:
        assert len(window.messages) <= SPLIT_TARGET
        assert window.sequence is not None


def test_build_adaptive_windows_separate_normal_days():
    day1 = datetime(2026, 3, 1, 10, 0, tzinfo=UTC)
    day3 = datetime(2026, 3, 3, 10, 0, tzinfo=UTC)
    messages = _make_messages_on_date(day1, 10) + _make_messages_on_date(day3, 10)
    windows = build_adaptive_windows(messages)
    assert len(windows) == 2


def test_window_source_id_single_day():
    gid = "gid://convictional/Chat/abc123"
    base = datetime(2026, 3, 15, 10, 0, tzinfo=UTC)
    messages = _make_messages_on_date(base, 10)
    windows = build_adaptive_windows(messages)
    assert windows[0].source_id(gid) == f"{gid}#window-2026-03-15"


def test_window_source_id_split_day():
    gid = "gid://convictional/Chat/abc123"
    base = datetime(2026, 3, 15, 10, 0, tzinfo=UTC)
    messages = _make_messages_on_date(base, SPLIT_THRESHOLD + 10)
    windows = build_adaptive_windows(messages)
    assert windows[0].source_id(gid) == f"{gid}#window-2026-03-15-0"
    assert windows[1].source_id(gid) == f"{gid}#window-2026-03-15-1"


def test_window_source_id_merged_days():
    gid = "gid://convictional/Chat/abc123"
    day1 = datetime(2026, 3, 1, 10, 0, tzinfo=UTC)
    day2 = datetime(2026, 3, 2, 10, 0, tzinfo=UTC)
    messages = _make_messages_on_date(day1, 2) + _make_messages_on_date(day2, 2)
    windows = build_adaptive_windows(messages)
    assert "2026-03-01--2026-03-02" in windows[0].source_id(gid)


def test_window_source_ids_unique():
    gid = "gid://convictional/Chat/abc123"
    day1 = datetime(2026, 3, 1, 10, 0, tzinfo=UTC)
    day2 = datetime(2026, 3, 2, 10, 0, tzinfo=UTC)
    messages = _make_messages_on_date(day1, 3) + _make_messages_on_date(day2, SPLIT_THRESHOLD)
    windows = build_adaptive_windows(messages)
    source_ids = [w.source_id(gid) for w in windows]
    assert len(source_ids) > 1
    assert len(source_ids) == len(set(source_ids))
