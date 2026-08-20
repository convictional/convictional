"""LEGACY — email-only coverage for Document, Meeting.

See `legacy_email.py` for the rationale and deletion criteria. Email is out of scope for
the notifications spec; these tests protect the legacy email path (the source of many of
the original "sent email" regressions) until these resources gain an inbox surface.
"""

import pytest

from config.enums import SubscriptionLevel
from infra.email import FakeDelivery
from tests.helpers.app import AppClient
from tests.integration.notifications.legacy_email import (
    EMAILED,
    NOT_EMAILED,
    DocumentScenario,
    MeetingScenario,
)


@pytest.mark.asyncio
async def test_document_comment_email(client: AppClient, email_delivery: FakeDelivery):
    scenario = await DocumentScenario.new(client)
    await scenario.add("subscriber_all", level=SubscriptionLevel.ALL)
    await scenario.add("relevant_no_tie", level=SubscriptionLevel.RELEVANT_ONLY)
    await scenario.add("mentioned")
    await scenario.add("commenter")

    await scenario.comment(by="commenter", mentioning="mentioned")

    await scenario.expect_emails(
        creator=EMAILED,  # implicit ALL on their own document
        subscriber_all=EMAILED,  # level reach
        mentioned=EMAILED,  # mention email
        relevant_no_tie=NOT_EMAILED,  # below level
        commenter=NOT_EMAILED,  # sender
    )


@pytest.mark.asyncio
async def test_document_reply_in_your_thread_email(client: AppClient, email_delivery: FakeDelivery):
    # The reported case (a doc commenter, at RELEVANT_ONLY, replied to but never notified),
    # plus a same-resource control that proves the tie is thread-scoped, not resource-scoped.
    scenario = await DocumentScenario.new(client)
    await scenario.add("participant", level=SubscriptionLevel.RELEVANT_ONLY)
    await scenario.add("other_thread", level=SubscriptionLevel.RELEVANT_ONLY)
    await scenario.add("relevant_no_tie", level=SubscriptionLevel.RELEVANT_ONLY)
    await scenario.add("replier")

    await scenario.comment(by="participant", comment_mark_id="mark-a")
    await scenario.comment(by="other_thread", comment_mark_id="mark-b")
    await scenario.comment(by="replier", comment_mark_id="mark-a")  # reply lands in participant's thread only

    await scenario.expect_emails(
        participant=EMAILED,  # replied to in the thread they started
        other_thread=NOT_EMAILED,  # commented, but on a different thread → not their thread
        relevant_no_tie=NOT_EMAILED,  # below level, never commented
        replier=NOT_EMAILED,  # sender
    )


@pytest.mark.asyncio
async def test_meeting_agenda_update_email(client: AppClient, email_delivery: FakeDelivery):
    scenario = await MeetingScenario.new(client)
    await scenario.add("subscriber_all", level=SubscriptionLevel.ALL)
    await scenario.add("relevant_no_tie", level=SubscriptionLevel.RELEVANT_ONLY)

    await scenario.update_agenda(by="creator")  # creator edits their own meeting → excluded as sender

    await scenario.expect_emails(
        subscriber_all=EMAILED,  # level reach
        relevant_no_tie=NOT_EMAILED,  # below level
    )
