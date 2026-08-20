"""Unit tests for MailboxSyncParams — channel.params parsing for the mailbox_sync stream."""

import pytest
from pydantic import ValidationError

from app.routers.api.mailbox_entries import MailboxSyncParams
from config.enums import MailboxSort


def test_defaults_when_no_params():
    params = MailboxSyncParams.model_validate({})
    assert params.view == "inbox"
    assert params.sort == MailboxSort.NEWEST
    assert params.mailbox_view_mode is False
    assert params.view_id is None
    assert params.cached_entry_ids == []


def test_canonical_view_passes_through():
    for view in ("inbox", "unread", "archived", "sent", "drafts", "assigned_to_me", "snoozed"):
        assert MailboxSyncParams.model_validate({"view": view}).view == view


def test_legacy_route_name_aliases_to_canonical_view():
    aliases = {
        "mailbox_index": "inbox",
        "mailbox_archived": "archived",
        "mailbox_sent": "sent",
        "mailbox_drafts": "drafts",
        "mailbox_assigned_to_me": "assigned_to_me",
        "mailbox_snoozed": "snoozed",
    }
    for legacy, canonical in aliases.items():
        assert MailboxSyncParams.model_validate({"view": legacy}).view == canonical


def test_mailbox_view_mode_string_to_bool():
    assert MailboxSyncParams.model_validate({"mailbox_view_mode": "true"}).mailbox_view_mode is True
    assert MailboxSyncParams.model_validate({"mailbox_view_mode": "false"}).mailbox_view_mode is False


def test_cached_entry_ids_parses_json_string():
    params = MailboxSyncParams.model_validate({"cached_entry_ids": '["a", "b"]'})
    assert params.cached_entry_ids == ["a", "b"]


def test_cached_entry_ids_falls_back_to_empty_on_malformed_json():
    params = MailboxSyncParams.model_validate({"cached_entry_ids": "not-json"})
    assert params.cached_entry_ids == []


def test_sort_parses_enum_value():
    assert MailboxSyncParams.model_validate({"sort": "oldest"}).sort == MailboxSort.OLDEST


def test_current_entry_ids_parses_json_string():
    params = MailboxSyncParams.model_validate({"current_entry_ids": '["x", "y"]'})
    assert params.current_entry_ids == ["x", "y"]


def test_current_entry_ids_raises_on_malformed_json():
    # Strict: current_entry_ids drives the cross-page dedupe diff. Silently dropping bad
    # input would make the client believe its locally-cached entries were "kept" when
    # they were actually discarded. cached_entry_ids stays soft (count exclusion only).
    with pytest.raises(ValidationError):
        MailboxSyncParams.model_validate({"current_entry_ids": "not-json"})


def test_unknown_view_value_rejected():
    with pytest.raises(ValidationError):
        MailboxSyncParams.model_validate({"view": "not-a-real-view"})
