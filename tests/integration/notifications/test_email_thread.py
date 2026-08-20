"""Notifications — EmailThread.

The EmailThread rows of `docs/notifications-spec.md`. Email threads force every
collaborator into the inbox regardless of level ("Email always arrives in your inbox"),
and a comment pushes both @mentions and the "reply on yours" audience (the thread's
creator and assignee).
"""

import pytest

from app.models.collaboration.mailbox import MailboxEntry
from app.models.workspaces.email.thread import EmailThread
from config.enums import SubscriptionLevel
from infra.jobs import InlineJobs
from infra.push import FakePushDelivery
from tests.helpers.app import AppClient
from tests.helpers.factories import create_email_message
from tests.integration.notifications import harness
from tests.integration.notifications.harness import INBOX_AND_PUSH, INBOX_ONLY, Push
from tests.integration.notifications.scenarios import EmailThreadScenario


@pytest.mark.asyncio
async def test_email_thread_comment(
    client: AppClient, push_enabled, background_jobs: InlineJobs, push_delivery: FakePushDelivery
):
    scenario = await EmailThreadScenario.new(client)
    await scenario.add("collaborator_all", level=SubscriptionLevel.ALL)
    await scenario.add("collaborator_relevant", level=SubscriptionLevel.RELEVANT_ONLY)
    await scenario.add("mentioned")
    await scenario.add("commenter")

    await scenario.comment(by="commenter", mentioning="mentioned")

    # Collaborators land in the inbox regardless of level; a plain collaborator (not the
    # thread's creator/assignee) pushes only on @mention.
    await scenario.expect(
        creator=INBOX_AND_PUSH,  # reply on your thread
        collaborator_all=INBOX_ONLY,  # level reach, no ambient push
        collaborator_relevant=INBOX_ONLY,  # force-include: level doesn't gate the email inbox
        mentioned=INBOX_AND_PUSH,  # mention is directed
    )


@pytest.mark.asyncio
async def test_email_thread_reply_pushes_owner(
    client: AppClient, push_enabled, background_jobs: InlineJobs, push_delivery: FakePushDelivery
):
    scenario = await EmailThreadScenario.new(client)
    await scenario.add("commenter")

    await scenario.comment(by="commenter")  # a reply, no mention

    await scenario.expect(creator=INBOX_AND_PUSH)  # reply on your thread should push


@pytest.mark.asyncio
async def test_email_thread_reply_in_your_thread(
    client: AppClient, push_enabled, background_jobs: InlineJobs, push_delivery: FakePushDelivery
):
    scenario = await EmailThreadScenario.new(client)
    await scenario.add("participant", level=SubscriptionLevel.RELEVANT_ONLY)
    await scenario.add("relevant_no_tie", level=SubscriptionLevel.RELEVANT_ONLY)
    await scenario.add("replier")

    # A plain collaborator (not the creator/assignee) comments, then someone replies to them.
    thread = await scenario.comment(by="participant")
    await scenario.comment(by="replier", reply_to_id=thread)

    await scenario.expect(
        participant=INBOX_AND_PUSH,  # reply on yours (thread): force-include lands the inbox, the tie adds push
        relevant_no_tie=INBOX_ONLY,  # force-include lands the inbox; no tie, so no push
    )


@pytest.mark.asyncio
async def test_email_thread_reply_resurfaces_archived_thread(
    client: AppClient, push_enabled, background_jobs: InlineJobs, push_delivery: FakePushDelivery
):
    scenario = await EmailThreadScenario.new(client)
    await scenario.add("commenter")
    thread = scenario.resource
    assert isinstance(thread, EmailThread)

    # The thread has inbound mail that Gmail has since archived (a RECEIVED message with no
    # INBOX label). This is the state that gates re-surfacing: a comment-only or all-outgoing
    # thread re-surfaces on its own, so the archived-inbound case is the one that exercises the
    # forced-surface path past the Gmail gate.
    await create_email_message(
        organization_id=scenario.organization_id,
        creator_id=scenario.creator.id,
        external_thread_id=thread.external_thread_id,
        sender="someone@external.com",
        labels=[],
    )

    # The creator archives the thread, taking it off their inbox.
    await scenario.archive(by="creator")

    # A collaborator replies on the creator's own thread — reply on yours.
    await scenario.comment(by="commenter")

    # The reply pushes the creator, so it must also bring the thread back to their inbox — the
    # two surfaces stay consistent. The shared inbox observable only reads the unread flag, but
    # an archived row can be marked unread without re-surfacing, so assert on the INBOX label
    # directly (the surface the user actually sees).
    entry = await MailboxEntry.get(owner_id=scenario.creator.id, resource_gid=str(thread.global_id))
    assert await harness.push_outcome(scenario.creator) == Push.SEND  # reply-on-yours pushes
    assert entry.is_inbox  # …and is back on the inbox surface
