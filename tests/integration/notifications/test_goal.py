"""Notifications — Goal (desired state, TDD).

The Goal rows of `docs/notifications-spec.md`, made executable. Goals are now inbox-native
(GoalMailboxEntry) and no longer deliver via legacy email, so this file is the acceptance
spec for goal inbox reach.

Two goal-specific rules shape every expectation below:

- **Goals never push.** A reached goal row is always `INBOX_ONLY` (unread, no push), never
  `INBOX_AND_PUSH` — even for a mention, a reply on your goal, or a direct update request. The
  forced-vs-level distinction therefore only shows in *whether* a below-level recipient is
  reached at all, not in a push.
- **A goal's collaborators are its owner and its group's members.** A group member's reach
  follows their global "Goals" preference (default "Relevant to me") or a per-goal subscription,
  like any subscriber — membership makes them a candidate, not an automatic `ALL`. There is no
  per-group opt-out. The owner is reached at `ALL` when they created the goal (the creator tier);
  independently, an **update request is a direct ask to the owner** and reaches them even below
  `ALL` (relevant-to-me reach), whether or not they are the creator. That direct ask reaches the
  owner *and no one else*: it is not a level-reach broadcast, so an `ALL`-level subscriber or group
  member — even the goal's creator, once ownership has moved on — is not reached by it.

The actor's own row follows the general rule: no self-alert, and — below reach with no existing
row — no row at all (acting on a goal does not manufacture an inbox row).
"""

import pytest

from config.enums import SubscriptionLevel
from infra.jobs import InlineJobs
from infra.push import FakePushDelivery
from tests.helpers.app import AppClient
from tests.integration.notifications import harness
from tests.integration.notifications.harness import ALREADY_SEEN, INBOX_ONLY, NOTHING
from tests.integration.notifications.scenarios import GoalScenario


@pytest.mark.asyncio
async def test_goal_commented(
    client: AppClient, push_enabled, background_jobs: InlineJobs, push_delivery: FakePushDelivery
):
    scenario = await GoalScenario.new(client, group=True, title="Ship Q3")
    await scenario.add("subscriber_all", level=SubscriptionLevel.ALL)
    await scenario.add("mentioned", level=SubscriptionLevel.RELEVANT_ONLY)
    await scenario.add("relevant_no_tie", level=SubscriptionLevel.RELEVANT_ONLY)
    await scenario.add("outsider", collaborator=False)
    await scenario.add("commenter")

    await scenario.comment(by="commenter", mentioning="mentioned")

    await scenario.expect(
        owner=INBOX_ONLY,  # reply on your goal — reached, but goals never push
        subscriber_all=INBOX_ONLY,  # level reach
        mentioned=INBOX_ONLY,  # mention forces past RELEVANT_ONLY (still no push)
        relevant_no_tie=NOTHING,  # below level, no mention, no thread tie
        outsider=NOTHING,  # not a collaborator; goals don't broadcast org-wide
        commenter=NOTHING,  # actor below ALL with no prior row — no self-alert, no row manufactured
    )


@pytest.mark.asyncio
async def test_goal_reply_in_your_thread(
    client: AppClient, push_enabled, background_jobs: InlineJobs, push_delivery: FakePushDelivery
):
    scenario = await GoalScenario.new(client, title="Roadmap")
    await scenario.add("participant", level=SubscriptionLevel.RELEVANT_ONLY)
    await scenario.add("relevant_no_tie", level=SubscriptionLevel.RELEVANT_ONLY)
    await scenario.add("replier")

    # participant starts a thread at RELEVANT_ONLY; someone else replies in it.
    thread = await scenario.comment(by="participant")
    await scenario.comment(by="replier", parent_id=thread)

    await scenario.expect(
        participant=INBOX_ONLY,  # reply on yours (thread) — a tie reaches you below ALL
        relevant_no_tie=NOTHING,  # RELEVANT_ONLY, never in the thread → below level
    )


@pytest.mark.asyncio
async def test_goal_update_posted(
    client: AppClient, push_enabled, background_jobs: InlineJobs, push_delivery: FakePushDelivery
):
    scenario = await GoalScenario.new(client, group=True, title="Q3 revenue")
    await scenario.add("subscriber_all", level=SubscriptionLevel.ALL)
    await scenario.add("relevant_no_tie", level=SubscriptionLevel.RELEVANT_ONLY)
    # Posting an update requires the goal's owner or a group member (not a plain collaborator).
    await scenario.add("poster", in_group=True, collaborator=False)

    await scenario.post_update(by="poster")

    await scenario.expect(
        owner=INBOX_ONLY,  # an update on your goal
        subscriber_all=INBOX_ONLY,  # level reach
        relevant_no_tie=NOTHING,  # below level
        poster=NOTHING,  # actor below ALL with no prior row — no self-alert, no row manufactured
    )


@pytest.mark.asyncio
async def test_goal_update_requested(
    client: AppClient, push_enabled, background_jobs: InlineJobs, push_delivery: FakePushDelivery
):
    scenario = await GoalScenario.new(client, group=True, title="Marketing plan")
    await scenario.add("member_all", level=SubscriptionLevel.ALL, in_group=True, collaborator=False)
    await scenario.add("bystander", level=SubscriptionLevel.RELEVANT_ONLY)
    await scenario.add("requester")

    await scenario.request_update(by="requester")  # always asks the goal's owner

    await scenario.expect(
        owner=INBOX_ONLY,  # the update is always requested from the owner — a direct ask on their goal
        member_all=NOTHING,  # a direct ask reaches ONLY the owner — an ALL-level group member is not
        bystander=NOTHING,  # not the owner, below level
        requester=NOTHING,  # actor below ALL with no prior row — no self-alert, no row manufactured
    )


@pytest.mark.asyncio
async def test_goal_update_requested_reaches_below_all_owner_who_is_not_creator(
    client: AppClient, push_enabled, background_jobs: InlineJobs, push_delivery: FakePushDelivery
):
    """An update request is a direct ask to the goal's owner, reaching them even below ALL — the
    reach does not depend on the owner being the goal's creator. This is the case the creator
    tier alone would miss: a delegated owner (a group member at the default RELEVANT_ONLY) who
    did not create the goal."""
    scenario = await GoalScenario.new(client, group=True, title="Delegated OKR")
    # Reassign ownership away from the creator to a below-ALL group member.
    delegate = await scenario.add("delegate", in_group=True, collaborator=False)  # default RELEVANT_ONLY
    assert scenario.resource is not None
    scenario.resource.owner_id = delegate.id
    await scenario.resource.save()
    await scenario.add("requester")

    await scenario.request_update(by="requester")

    await scenario.expect(
        delegate=INBOX_ONLY,  # direct ask reaches the below-ALL owner, though they aren't the creator
        owner=NOTHING,  # the original creator is ALL via the creator tier, but a direct ask reaches only the owner
        requester=NOTHING,  # actor below ALL with no prior row
    )


@pytest.mark.asyncio
async def test_goal_completed(
    client: AppClient, push_enabled, background_jobs: InlineJobs, push_delivery: FakePushDelivery
):
    scenario = await GoalScenario.new(client, group=True, title="Launch")
    await scenario.add("subscriber_all", level=SubscriptionLevel.ALL)
    await scenario.add("relevant_no_tie", level=SubscriptionLevel.RELEVANT_ONLY)
    await scenario.add("closer")

    await scenario.complete(by="closer")

    await scenario.expect(
        owner=INBOX_ONLY,  # the goal's owner/creator (ALL via the creator tier) — a lifecycle change on their goal
        subscriber_all=INBOX_ONLY,  # a lifecycle change surfaces by level reach
        relevant_no_tie=NOTHING,  # a lifecycle change is not a "reaches you" for a below-level user
        closer=NOTHING,  # actor below ALL with no prior row — no self-alert, no row manufactured
    )


@pytest.mark.asyncio
async def test_goal_group_member_reach_follows_preference(
    client: AppClient, push_enabled, background_jobs: InlineJobs, push_delivery: FakePushDelivery
):
    """A group member's reach for the group's goals follows their global "Goals" preference (or a
    per-goal subscription), like any subscriber — group membership makes them a candidate, not an
    automatic ALL. A member set to "All" is reached; the default "Relevant to me" is not (for a
    plain comment), nor is a per-goal RELEVANT_ONLY subscription."""
    scenario = await GoalScenario.new(client, group=True, title="Team OKRs")
    await scenario.add("member_all", level=SubscriptionLevel.ALL, in_group=True, collaborator=False)
    await scenario.add("member_default", in_group=True, collaborator=False)
    await scenario.add("member_bell_relevant", in_group=True, collaborator=False)
    await scenario.add("commenter", in_group=True, collaborator=False)
    await scenario.subscribe_relevant("member_bell_relevant")

    await scenario.comment(by="commenter")

    await scenario.expect(
        member_all=INBOX_ONLY,  # global "Goals: All" reaches by level
        member_default=NOTHING,  # no preference → the "Relevant to me" default; a plain comment doesn't reach
        member_bell_relevant=NOTHING,  # a per-goal RELEVANT_ONLY subscription (the bell) keeps them below level
        commenter=NOTHING,  # actor below ALL with no prior row — no self-alert, no row manufactured
    )


@pytest.mark.asyncio
async def test_goal_minor_edit_is_silent(
    client: AppClient, push_enabled, background_jobs: InlineJobs, push_delivery: FakePushDelivery
):
    """A minor field edit (title) refreshes an existing row rather than re-alerting. A row read
    before the edit stays read afterwards."""
    scenario = await GoalScenario.new(client, group=True, title="Original title")
    await scenario.add("engaged", level=SubscriptionLevel.ALL, in_group=True, collaborator=False)
    await scenario.add("editor", in_group=True, collaborator=False)

    await scenario.comment(by="editor")  # engaged is reached (unread)
    await scenario.mark_read(by="engaged")  # …and reads it
    await scenario.edit_title(by="editor", title="Refined title")  # a minor edit must not re-alert

    await scenario.expect(engaged=ALREADY_SEEN)  # revision refreshes the row; it stays read


@pytest.mark.asyncio
async def test_goal_subgoal_gets_its_own_row(
    client: AppClient, push_enabled, background_jobs: InlineJobs, push_delivery: FakePushDelivery
):
    """A subgoal is its own goal with its own inbox row; a comment on it surfaces the subgoal's
    row and never touches the parent's."""
    scenario = await GoalScenario.new(client, group=True, title="Parent goal")
    await scenario.add("member", level=SubscriptionLevel.ALL, in_group=True, collaborator=False)
    commenter = await scenario.add("commenter", in_group=True, collaborator=False)
    subgoal = await scenario.make_subgoal(title="Subgoal")

    await harness.emit_goal_commented(client, subgoal, commenter, content="on the subgoal")

    assert scenario.resource is not None  # the parent goal
    # member reaches the subgoal (its own row), not the parent; the commenter is below ALL with
    # no prior row, so acting on the subgoal manufactures no row for them.
    await scenario.expect_for(subgoal, member=INBOX_ONLY, commenter=NOTHING)
    await scenario.expect_for(scenario.resource, member=NOTHING)  # parent untouched
