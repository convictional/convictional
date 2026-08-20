"""Inbox reach for email threads.

An email thread has no per-collaborator subscription level — collaboration is unconditionally
ALL — so inbox reach is exactly the collaborator set. These tests pin that:

- `resolve_for_inbox` reaches every collaborator. The lever is
  `EmailThreadNotificationPolicy.force_include_for_inbox`; email collaborators
  have no `Subscription` rows, so without it they'd fall back to RELEVANT_ONLY.
- Force-include lives ONLY in `resolve_for_inbox` (inbox reach), NOT in the generic
  `resolve()`/`resolve_with_sources` primitive (the subscription cascade), which also feeds the
  push and email channels. `test_resolve_primitive_stays_pure` guards that boundary.

The workspace post_save (`ensure_creator_collaborator`) auto-adds the thread creator as a
collaborator, so tests add only the *other* collaborators explicitly.
"""

import pytest

from app.models.collaboration.workspace import SubscriberResolver
from config.enums import EventAction
from tests.helpers.factories import (
    create_collaborator,
    create_email_thread,
    create_event,
    create_user,
)


async def _email_thread_with_collaborator():
    creator = await create_user()
    cc_collaborator = await create_user(organization_id=creator.organization_id)
    bystander = await create_user(organization_id=creator.organization_id)
    thread = await create_email_thread(creator_id=creator.id, organization_id=creator.organization_id)
    await create_collaborator(workspace_id=thread.workspace_id, user_id=cc_collaborator.id)
    await thread.fetch_related("workspace")
    return thread, creator, cc_collaborator, bystander


@pytest.mark.asyncio
async def test_resolve_for_inbox_reaches_every_collaborator():
    # resolve_for_inbox must reach the creator and every collaborator, never a non-collaborator.
    # The factory creates NO Subscription rows (collaboration on a thread is implicit and
    # unconditionally ALL), so cc_collaborator falls back to RELEVANT_ONLY in _level_for and can
    # only be reached via force-include. No mention recipients are passed either, so a mention
    # can't mask a broken force-include.
    thread, creator, cc_collaborator, bystander = await _email_thread_with_collaborator()

    event = await create_event(thread.workspace, creator_id=creator.id, action=EventAction.COMMENTED)
    reached = await SubscriberResolver(workspace=thread.workspace).resolve_for_inbox(event, direct_recipients=[])

    assert {u.id for u in reached} == {creator.id, cc_collaborator.id}
    assert bystander.id not in {u.id for u in reached}


@pytest.mark.asyncio
async def test_resolve_primitive_stays_pure():
    # Force-include is an inbox-reach concern and must NOT leak into the generic resolve()
    # primitive (which also feeds resolve_for_push / resolve_for_email). For an email thread
    # with no subscriptions, resolve() returns only the creator (ALL via creator→ALL); the CC'd
    # collaborator is RELEVANT_ONLY and excluded. This guards the layering boundary: if someone
    # adds force-include to resolve_with_sources, this test fails.
    thread, creator, cc_collaborator, _bystander = await _email_thread_with_collaborator()

    resolved = await SubscriberResolver(workspace=thread.workspace).resolve()
    resolved_ids = {u.id for u in resolved}

    assert creator.id in resolved_ids
    assert cc_collaborator.id not in resolved_ids
