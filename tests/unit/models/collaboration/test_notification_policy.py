from app.models.collaboration.workspace import NotificationPolicy, WorkspaceMixin
from app.models.workspaces.chat import Chat, ChatNotificationPolicy
from app.models.workspaces.goals import Goal, GoalNotificationPolicy
from app.models.workspaces.meetings import Meeting
from app.models.workspaces.posts import Post, PostNotificationPolicy
from config.enums import EventAction, SubscriptionLevel


def test_default_subscription_levels_per_policy_class():
    # Class-level access drives SubscriptionPreference.defaults_for, which seeds
    # per-resource-type global preferences without instantiating a policy.
    assert NotificationPolicy.default_subscription_level == SubscriptionLevel.RELEVANT_ONLY
    assert ChatNotificationPolicy.default_subscription_level == SubscriptionLevel.ALL
    assert PostNotificationPolicy.default_subscription_level == SubscriptionLevel.BROADCASTS


def test_workspace_classes_advertise_their_notification_policy_class():
    assert WorkspaceMixin.notification_policy_class() is NotificationPolicy
    assert Chat.notification_policy_class() is ChatNotificationPolicy
    assert Post.notification_policy_class() is PostNotificationPolicy
    assert Goal.notification_policy_class() is GoalNotificationPolicy
    # Resources without a specific subclass fall through to the base.
    assert Meeting.notification_policy_class() is NotificationPolicy


def test_base_notification_policy_defaults():
    policy = NotificationPolicy(workspace=None)  # type: ignore[arg-type]
    assert policy.notification_group_id is None
    assert policy.broadcasts_to_organization is False
    assert policy.force_include_for_inbox() is False
    assert policy.force_include_all_collaborators_for_push is False
    assert policy.notify_subscriber_push is False
    assert policy.notify_mention_push is False
    assert policy.creator_and_assignee_reply_actions == frozenset()


def test_chat_and_post_mentions_push_but_async_resources_do_not():
    # Chat and post @mentions push (an @mention names you specifically); goal/
    # doc/meeting @mentions only reach the inbox/email.
    assert NotificationPolicy(workspace=None).notify_mention_push is False  # type: ignore[arg-type]
    assert ChatNotificationPolicy(workspace=None, chat=None).notify_mention_push is True  # type: ignore[arg-type]
    assert PostNotificationPolicy(workspace=None, post=None).notify_mention_push is True  # type: ignore[arg-type]


def test_post_replies_reach_creator_and_assignee():
    # A reply/comment on a post reaches its creator and assignee, and a decision
    # mark routes like a new comment, so DECIDED rides the same contour.
    # Publishing a post (POST_CREATED) is not in the set.
    base = NotificationPolicy(workspace=None)  # type: ignore[arg-type]
    post_policy = PostNotificationPolicy(workspace=None, post=None)  # type: ignore[arg-type]
    assert base.creator_and_assignee_reply_actions == frozenset()
    assert post_policy.creator_and_assignee_reply_actions == frozenset(
        {EventAction.POST_COMMENTED, EventAction.DECIDED}
    )
    assert EventAction.POST_CREATED not in post_policy.creator_and_assignee_reply_actions
