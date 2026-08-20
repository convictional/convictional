"""Notifications — Post.

The Post rows of `docs/notifications-spec.md`, made executable. Each test declares the
people around a post, fires a single event over the real HTTP API, and asserts every
person's (inbox, push) outcome at once.
"""

import pytest

from config.enums import SubscriptionLevel
from infra.jobs import InlineJobs
from infra.push import FakePushDelivery
from tests.helpers.app import AppClient
from tests.integration.notifications.harness import INBOX_AND_PUSH, INBOX_ONLY, NOTHING
from tests.integration.notifications.scenarios import PostScenario


@pytest.mark.asyncio
async def test_post_commented(
    client: AppClient, push_enabled, background_jobs: InlineJobs, push_delivery: FakePushDelivery
):
    scenario = await PostScenario.published(client, title="Lunch")
    await scenario.add("assignee", assignee=True)
    await scenario.add("mentioned")
    await scenario.add("subscriber_all", level=SubscriptionLevel.ALL)
    await scenario.add("relevant_no_tie", level=SubscriptionLevel.RELEVANT_ONLY)
    await scenario.add("commenter")

    await scenario.comment(by="commenter", mentioning="mentioned")

    await scenario.expect(
        creator=INBOX_AND_PUSH,  # reply on yours
        assignee=INBOX_AND_PUSH,  # reply on yours
        mentioned=INBOX_AND_PUSH,  # mention
        subscriber_all=INBOX_ONLY,  # level reach
        relevant_no_tie=NOTHING,  # below level
    )


@pytest.mark.asyncio
async def test_post_reply_in_your_thread(
    client: AppClient, push_enabled, background_jobs: InlineJobs, push_delivery: FakePushDelivery
):
    scenario = await PostScenario.published(client, title="Roadmap")
    await scenario.add("participant", level=SubscriptionLevel.RELEVANT_ONLY)
    await scenario.add("relevant_no_tie", level=SubscriptionLevel.RELEVANT_ONLY)
    await scenario.add("replier")

    # participant starts a thread at RELEVANT_ONLY; someone else replies in it.
    thread = await scenario.comment(by="participant")
    await scenario.comment(by="replier", parent_id=thread)

    await scenario.expect(
        participant=INBOX_AND_PUSH,  # reply on yours (thread) — a tie reaches you below ALL
        relevant_no_tie=NOTHING,  # RELEVANT_ONLY, never in the thread → below level
    )


@pytest.mark.asyncio
async def test_post_assigned(
    client: AppClient, push_enabled, background_jobs: InlineJobs, push_delivery: FakePushDelivery
):
    scenario = await PostScenario.published(client, title="Ship it")
    await scenario.add("assignee", level=SubscriptionLevel.RELEVANT_ONLY)  # below ALL must not silence being assigned
    await scenario.add("manager")

    await scenario.assign(assignee="assignee", by="manager")

    await scenario.expect(
        assignee=INBOX_AND_PUSH,  # assignment always reaches you + pushes
        creator=INBOX_ONLY,  # ALL on their own post → level reach; assignment doesn't push them
    )


@pytest.mark.asyncio
async def test_self_assignment_reaches_you(
    client: AppClient, push_enabled, background_jobs: InlineJobs, push_delivery: FakePushDelivery
):
    scenario = await PostScenario.published(client, title="I'll take it")
    await scenario.add("self_assigner", level=SubscriptionLevel.RELEVANT_ONLY)

    await scenario.assign(assignee="self_assigner", by="self_assigner")  # actor == assignee

    await scenario.expect(self_assigner=INBOX_AND_PUSH)  # a self-assignment reaches you like any assignment


@pytest.mark.asyncio
async def test_post_created_org_wide_tier(
    client: AppClient, push_enabled, background_jobs: InlineJobs, push_delivery: FakePushDelivery
):
    scenario = await PostScenario.new(client)
    await scenario.add("all_user", level=SubscriptionLevel.ALL, collaborator=False)
    await scenario.add("broadcasts_user", level=SubscriptionLevel.BROADCASTS, collaborator=False)
    await scenario.add("relevant_user", level=SubscriptionLevel.RELEVANT_ONLY, collaborator=False)

    await scenario.create(title="All hands")

    await scenario.expect(
        all_user=INBOX_ONLY,  # level reach
        broadcasts_user=INBOX_ONLY,  # org-wide broadcast, level reach
        relevant_user=NOTHING,  # below level
    )


@pytest.mark.asyncio
async def test_post_commented_group_mute(
    client: AppClient, push_enabled, background_jobs: InlineJobs, push_delivery: FakePushDelivery
):
    scenario = await PostScenario.published(client, group=True, title="Group post")
    await scenario.add("member", in_group=True, collaborator=False)
    await scenario.add("muted_member", in_group=True, muted=True, collaborator=False)
    await scenario.add("commenter")

    await scenario.comment(by="commenter")

    await scenario.expect(
        member=INBOX_ONLY,  # group membership → level reach
        # mute drops them to RELEVANT_ONLY; with no pre-existing row this is IGNORE. (A
        # muted member who already had a row would get REFRESH_CONTENT — see the spec.)
        muted_member=NOTHING,
    )


@pytest.mark.asyncio
async def test_post_commented_group_excludes_deactivated_member(
    client: AppClient, push_enabled, background_jobs: InlineJobs, push_delivery: FakePushDelivery
):
    scenario = await PostScenario.published(client, group=True, title="Group post")
    await scenario.add("member", in_group=True, collaborator=False)
    deactivated = await scenario.add("deactivated", in_group=True, collaborator=False)
    await deactivated.deactivate()  # soft-delete + log out before the comment fires
    await scenario.add("commenter")

    await scenario.comment(by="commenter")

    await scenario.expect(
        member=INBOX_ONLY,  # active group membership → level reach
        deactivated=NOTHING,  # deactivated member is not reached — no inbox row, no push
    )
