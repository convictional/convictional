"""Notifications — Chat.

The Chat rows of `docs/notifications-spec.md`. Chat type follows participant count
(2 = DM, 3+ = multi-person direct) or a group (channel). Covers the one place level-based
reach still pushes: a multi-person direct chat at ALL (muting silences it).
"""

import pytest

from config.enums import SubscriptionLevel
from infra.jobs import InlineJobs
from infra.push import FakePushDelivery
from tests.helpers.app import AppClient
from tests.integration.notifications.harness import ALREADY_SEEN, INBOX_AND_PUSH, INBOX_ONLY, NOTHING
from tests.integration.notifications.scenarios import ChatScenario


@pytest.mark.asyncio
async def test_chat_dm(client: AppClient, push_enabled, background_jobs: InlineJobs, push_delivery: FakePushDelivery):
    scenario = await ChatScenario.new(client)  # 2 collaborators, no group => DM
    await scenario.add("alice")  # sender / actor
    await scenario.add("bob")

    await scenario.message(by="alice")

    await scenario.expect(
        bob=INBOX_AND_PUSH,  # 1:1 DM is directed
        alice=ALREADY_SEEN,  # sender's own row, no self-alert
    )


@pytest.mark.asyncio
async def test_chat_multi(
    client: AppClient, push_enabled, background_jobs: InlineJobs, push_delivery: FakePushDelivery
):
    scenario = await ChatScenario.new(client)  # 3 collaborators, no group => MULTI
    await scenario.add("alice")  # actor
    await scenario.add("bob")  # default ALL
    await scenario.add("carol", level=SubscriptionLevel.RELEVANT_ONLY)  # muted

    await scenario.message(by="alice")

    await scenario.expect(
        bob=INBOX_AND_PUSH,  # direct chat pushes at ALL; muting silences it
        carol=NOTHING,  # muting silences it
    )


@pytest.mark.asyncio
async def test_chat_group_channel(
    client: AppClient, push_enabled, background_jobs: InlineJobs, push_delivery: FakePushDelivery
):
    scenario = await ChatScenario.new(client, channel=True)
    await scenario.add("alice")  # actor
    await scenario.add("bob", level=SubscriptionLevel.ALL)
    await scenario.add("carol", level=SubscriptionLevel.RELEVANT_ONLY)  # row comes only from the mention

    await scenario.message(by="alice", mentioning="carol")

    await scenario.expect(
        bob=INBOX_ONLY,  # channel: level reach, no push
        carol=INBOX_AND_PUSH,  # mention is directed
    )
