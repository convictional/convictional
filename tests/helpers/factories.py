import io
import random
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.models.accounts import (
    EmailAlias,
    Group,
    GroupMember,
    OAuthToken,
    Organization,
    OrganizationUpdatesConfiguration,
    PushSubscription,
    User,
)
from app.models.collaboration.content import Content, Research
from app.models.collaboration.mailbox import MailboxEntry, MailboxView
from app.models.collaboration.workspace import (
    Attachment,
    Collaborator,
    CommentMixin,
    Decision,
    Event,
    SubscriptionPreference,
    Workspace,
)
from app.models.commands import ResearchQuestion, ScheduledResearch
from app.models.workspaces.chat import Chat, ChatMessage
from app.models.workspaces.documents import Document
from app.models.workspaces.email.contact import EmailContact
from app.models.workspaces.email.thread import EmailDraft, EmailMessage, EmailThread, EmailThreadComment
from app.models.workspaces.goals import Goal, GoalComment, GoalUpdate
from app.models.workspaces.meetings import Meeting, MeetingAttendee, MeetingCollection
from app.models.workspaces.posts import Post, PostComment, PostGroupMute
from config.enums import (
    AuthenticationProvider,
    ContentCategory,
    ContentType,
    EmailLabel,
    EmailMessageType,
    EventAction,
    GoalStatus,
    MeetingAttendeeStatus,
    ResearchSource,
    Sharing,
)
from config.settings import settings
from infra.jobs import Job, JobDefinition
from infra.oauth import Token
from infra.storage import store_file
from integrations.google.models import GmailAccount
from integrations.google.oauth import GOOGLE_GMAIL_SCOPES
from integrations.notion.models import NotionConnection, NotionPage
from integrations.recall_ai.models import RecallAIMeeting

user_count = 0
organization_count = 0
content_count = 0


async def create_user(**kwargs) -> User:
    global user_count
    user_count += 1

    attributes = {"email": f"foo-{user_count}@example.com", **kwargs}
    if "organization_id" not in attributes:
        organization = await create_organization()
        attributes["organization_id"] = organization.id

    result = await User.create(**{**attributes})
    await OAuthToken.create_or_update_by_token(result, Token.fake(result.email))
    await SubscriptionPreference.ensure_defaults(result.id)
    return result


async def create_superuser(**kwargs) -> User:
    # Superuser is granted by listing an address in settings.superuser_emails, so the
    # factory has to widen that setting. Assigning the set directly skips the validator, so
    # lowercase here to keep the invariant that its members are already lowercased. The
    # autouse `custom_settings` fixture wraps each test in settings.override(), which
    # restores it afterwards.
    user = await create_user(**kwargs)
    settings.superuser_emails = settings.superuser_emails | {user.email.lower()}
    return user


async def create_email_alias(**kwargs) -> EmailAlias:
    attributes = {**kwargs}
    if "user_id" not in attributes:
        user = await create_user()
        attributes["user_id"] = user.id

    return await EmailAlias.create(**attributes)


push_subscription_count = 0


async def create_push_subscription(**kwargs) -> PushSubscription:
    global push_subscription_count
    push_subscription_count += 1

    attributes = {
        "endpoint": f"https://fcm.googleapis.com/fcm/send/test-{push_subscription_count}",
        "p256dh_key": "test-p256dh-key",  # gitleaks:allow
        "auth_key": "test-auth-key",
        **kwargs,
    }
    if "user_id" not in attributes:
        user = await create_user()
        attributes["user_id"] = user.id

    return await PushSubscription.create(**attributes)


async def create_organization(**kwargs) -> Organization:
    global organization_count
    organization_count += 1

    attributes = {"domain": f"example-{organization_count}.com", **kwargs}
    return await Organization.create(**{**attributes})


async def create_workspace(**kwargs) -> Workspace:
    attributes = {**kwargs}
    if "organization_id" not in attributes:
        organization = await create_organization()
        attributes["organization_id"] = organization.id

    return await Workspace.create(**{**attributes})


async def create_email_thread_comment(**kwargs) -> EmailThreadComment:
    attributes = {"content": "This is a comment", **kwargs}
    # Resolve the thread from whichever identifier is given (email_thread_id or workspace_id),
    # or create one, then scope the comment by email_thread_id.
    workspace_id = attributes.pop("workspace_id", None)
    if "email_thread_id" in attributes:
        thread = await EmailThread.get(id=attributes["email_thread_id"])
    elif workspace_id is not None:
        thread = await EmailThread.get(workspace_id=workspace_id)
    elif "organization_id" in attributes:
        thread = await create_email_thread(organization_id=attributes["organization_id"])
    else:
        thread = await create_email_thread()
    attributes.setdefault("email_thread_id", thread.id)
    if "user_id" not in attributes:
        user = await create_user(organization_id=thread.organization_id)
        attributes["user_id"] = user.id

    return await EmailThreadComment.create(**{**attributes})


async def create_decision(workspace_id: UUID, comment: CommentMixin, **kwargs) -> Decision:
    attributes = {
        "workspace_id": workspace_id,
        "comment_gid": comment.global_id,
        "decided_at": datetime.now(UTC),
        **kwargs,
    }
    return await Decision.create(**attributes)


async def create_collaborator(**kwargs) -> Collaborator:
    attributes = {"name": "John Doe", **kwargs}
    if "user_id" not in attributes:
        user = await create_user(organization_id=attributes["organization_id"])
        attributes["user_id"] = user.id
    if "workspace_id" not in attributes:
        workspace = await create_workspace()
        attributes["workspace_id"] = workspace.id

    return await Collaborator.create(**{**attributes})


async def create_attachment(**kwargs) -> Attachment:
    attributes = {
        "title": "Attachment",
        "filename": "test.csv",
        "content": b"Title,Year\nThe Shawshank Redemption,1994\nThe Godfather,1972\nThe Dark Knight,2008\n",
        "content_type": "text/csv",
        **kwargs,
    }

    file_ref = await store_file(
        filename=attributes["filename"],
        content=io.BytesIO(attributes["content"]),
        content_type=attributes["content_type"],
    )
    attributes["file_id"] = file_ref.id

    if "workspace_id" not in attributes:
        workspace = await create_workspace(**attributes)
        attributes["workspace_id"] = workspace.id

    return await Attachment.create(**{**attributes})


async def create_meeting(**kwargs) -> Meeting:
    attributes = {
        "title": "Daily Standup",
        "attendees": [
            MeetingAttendee(name="bob@example.com", status=MeetingAttendeeStatus.ACCEPTED),
            MeetingAttendee(name="clams@example.com", status=MeetingAttendeeStatus.ACCEPTED),
        ],
        "summary": "We're getting a lot done today",
        **kwargs,
    }
    if "organization_id" not in attributes:
        organization = await create_organization()
        attributes["organization_id"] = organization.id
    if "creator_id" not in attributes:
        user = await create_user(organization_id=attributes["organization_id"])
        attributes["creator_id"] = user.id

    meeting = await Meeting.create(**{**attributes})
    await RecallAIMeeting.create(meeting_id=meeting.id, **attributes)
    return meeting


async def create_meeting_collection(**kwargs) -> MeetingCollection:
    attributes = {
        "title": "Daily Standups",
        "description": "All the daily standups",
        **kwargs,
    }
    if "organization_id" not in attributes:
        organization = await create_organization()
        attributes["organization_id"] = organization.id

    return await MeetingCollection.create(**{**attributes})


async def create_content(**kwargs):
    global content_count
    content_count += 1

    attributes = {
        "author": "Bob Clams",
        "title": "Economic Tariff Impact",
        "index_content": "The impact of tariffs on the economy is large.",
        "category": ContentCategory.DOCUMENT,
        "source_id": f"source-{content_count}",
        "source_url": "https://docs.google.com/document/d/1/edit",
        "content_type": ContentType.FILE,
        "sharing": Sharing.ORGANIZATION,
        **kwargs,
    }
    if "organization_id" not in attributes and "organization" not in attributes:
        organization = await create_organization()
        attributes["organization"] = organization
        attributes["organization_id"] = organization.id

    return await Content.create(**attributes)


async def create_job(job_definition: JobDefinition, **kwargs):
    return await Job.create_by_job_definition(job_definition, **kwargs)


async def create_goal(**kwargs):
    attributes = {
        "title": "",
        "description": "Default goal description",
        **kwargs,
    }

    if "organization_id" not in attributes:
        organization = await create_organization()
        attributes["organization_id"] = organization.id

    if "creator_id" not in attributes:
        user = await create_user(organization_id=attributes["organization_id"])
        attributes["creator_id"] = user.id

    if "activated_at" not in attributes:
        planning_list_name = attributes.get("planning_list_name")
        is_subgoal = attributes.get("parent_id") is not None
        if planning_list_name and not is_subgoal:
            attributes["activated_at"] = None
        else:
            attributes["activated_at"] = datetime.now(UTC)

    return await Goal.create(**attributes)


async def create_subgoal(**kwargs):
    attributes = {
        "title": "",
        "description": "Default subgoal description",
        **kwargs,
    }
    if "parent_id" not in attributes:
        parent = await create_goal()
        attributes["parent_id"] = parent.id
        attributes["organization_id"] = parent.organization_id
        attributes["creator_id"] = parent.creator_id

    if "activated_at" not in attributes:
        attributes["activated_at"] = datetime.now(UTC)

    return await Goal.create(**attributes)


async def create_goal_comment(**kwargs) -> GoalComment:
    attributes = {"content": "This is a goal comment", **kwargs}

    if "goal_id" not in attributes:
        goal = await create_goal()
        attributes["goal_id"] = goal.id

    if "user_id" not in attributes:
        if "goal_id" in kwargs:
            goal = await Goal.get(id=kwargs["goal_id"])
            attributes["user_id"] = goal.creator_id
        else:
            user = await create_user()
            attributes["user_id"] = user.id

    return await GoalComment.create(**attributes)


async def create_document(**kwargs):
    attributes = {"title": "Untitled document", **kwargs}

    if "organization_id" not in attributes:
        organization = await create_organization()
        attributes["organization_id"] = organization.id

    if "creator_id" not in attributes:
        user = await create_user(organization_id=attributes["organization_id"])
        attributes["creator_id"] = user.id

    return await Document.create(**attributes)


async def create_post(**kwargs):
    attributes = {"title": "Let's talk lunch", **kwargs}

    if "organization_id" not in attributes:
        organization = await create_organization()
        attributes["organization_id"] = organization.id

    if "creator_id" not in attributes:
        user = await create_user(organization_id=attributes["organization_id"])
        attributes["creator_id"] = user.id

    if "published_at" not in attributes:
        attributes["published_at"] = datetime.now(UTC)

    result = await Post.create(**attributes)
    if result.is_published:
        await create_post_comment(post_id=result.id, user_id=attributes["creator_id"])

    return result


async def create_post_comment(**kwargs):
    attributes = {"content": "What should we eat for lunch?", **kwargs}

    if "post_id" not in attributes:
        post = await create_post()
        attributes["post_id"] = post.id

    return await PostComment.create(**attributes)


async def create_goal_update(**kwargs):
    attributes = {
        "question_text": "How's it going?",
        **kwargs,
    }

    if "goal_id" not in attributes:
        goal = await create_goal()
        attributes["goal_id"] = goal.id
        if "status" not in attributes:
            attributes["status"] = goal.status

    if "creator_id" not in attributes:
        goal = await Goal.get(id=attributes["goal_id"])
        user = await create_user(organization_id=goal.organization_id)
        attributes["creator_id"] = user.id

    if "status" not in attributes:
        attributes["status"] = GoalStatus.ON_TRACK

    if "answer_text" in attributes and "completed_at" not in attributes:
        attributes["completed_at"] = datetime.now(UTC)

    return await GoalUpdate.create(**attributes)


async def create_organization_updates_configuration(**kwargs):
    attributes = {**kwargs}

    if "organization_id" not in attributes:
        organization = await create_organization()
        attributes["organization_id"] = organization.id

    return await OrganizationUpdatesConfiguration.create(**attributes)


async def create_file_reference(**kwargs):
    attributes = {
        "filename": "test-file.txt",
        "content_type": "text/plain",
        "content": b"This is a test file",
        **kwargs,
    }

    return await store_file(
        filename=attributes["filename"],
        content=io.BytesIO(attributes["content"]),
        content_type=attributes["content_type"],
    )


async def create_research(**kwargs) -> Research:
    attributes = {
        "topic": "Important research topic",
        "sources": [ResearchSource.INTERNAL],
        **kwargs,
    }
    if "organization_id" not in attributes:
        organization = await create_organization()
        attributes["organization_id"] = organization.id
    if "creator_id" not in attributes:
        user = await create_user(organization_id=attributes["organization_id"])
        attributes["creator_id"] = user.id

    return await Research.create(**attributes)


async def create_gmail_account(**kwargs) -> GmailAccount:
    attributes = {"history_id": "12345", **kwargs}
    if "user_id" not in attributes:
        user = await create_user()
        attributes["user_id"] = user.id
        # Use the user's email as the default email for the Gmail account
        if "email" not in attributes:
            attributes["email"] = user.email
        # Ensure the user has Gmail OAuth scopes
        token = Token.fake(user.email, scopes=GOOGLE_GMAIL_SCOPES)
        token.provider = AuthenticationProvider.GOOGLE
        await OAuthToken.create_or_update_by_token(user, token)

    return await GmailAccount.create(**attributes)


async def create_email_message(**kwargs) -> EmailMessage:
    unique_id = uuid4().hex[:8]
    attributes = {
        "external_message_id": f"msg_{unique_id}",
        "external_thread_id": f"thread_{unique_id}",
        "external_history_id": str(random.randint(10000, 999999)),
        "message_id": f"message_{unique_id}@example.com",
        "message_type": EmailMessageType.RECEIVED,
        "subject": "Test Email",
        "sender": "John Doe <john@example.com>",
        "to": ["jane@example.com"],
        "cc": [],
        "bcc": [],
        "body_plain": "Hello world!",
        "body_html": "<p>Hello world!</p>",
        "preview": "Hello world!",
        "received_at": datetime.now(UTC),
        "sent_at": datetime.now(UTC),
        "labels": [EmailLabel.INBOX],
        "raw_data": {},
        **kwargs,
    }

    if "organization_id" not in attributes:
        organization = await create_organization()
        attributes["organization_id"] = organization.id
    if "creator_id" not in attributes:
        user = await create_user(organization_id=attributes["organization_id"])
        attributes["creator_id"] = user.id

    # For received messages, use the new pattern that handles broadcasting
    if attributes.get("message_type") == EmailMessageType.RECEIVED:
        new_message_result = await EmailThread.receive_new_message(attributes)
        return new_message_result.email
    else:
        # For non-received messages (drafts, sent, etc.), use direct creation
        message = await EmailMessage.create(**attributes)
        if message.thread_id:
            thread = await EmailThread.get(id=message.thread_id)
            await thread.update_metadata_from_messages()
        return message


async def create_email_draft(**kwargs) -> EmailDraft:
    attributes = {
        "labels": [EmailLabel.DRAFT, *kwargs.get("labels", [])],
        **kwargs,
    }

    if "organization_id" not in attributes:
        organization = await create_organization()
        attributes["organization_id"] = organization.id
    if "user_id" not in attributes:
        user = await create_user(organization_id=attributes["organization_id"])
        attributes["user_id"] = user.id
    if attributes.get("thread_id") is None:
        # If no thread_id is provided, create a new thread
        thread = await create_email_thread(
            organization_id=attributes["organization_id"], creator_id=attributes["user_id"]
        )
        attributes["thread_id"] = thread.id
    else:
        # If a thread_id is provided, ensure it exists
        thread = await EmailThread.get(id=attributes["thread_id"])
        if not thread:
            raise ValueError(f"Thread with id {attributes['thread_id']} does not exist")

    await thread.fetch_related("creator")

    draft = await thread.start_draft(
        user=thread.creator,
        subject=attributes.get("subject"),
        to=attributes.get("to"),
        cc=attributes.get("cc"),
        bcc=attributes.get("bcc"),
        body_plain=attributes.get("body_plain"),
        using_db=kwargs.get("using_db"),
    )
    return draft


async def create_email_thread(**kwargs) -> EmailThread:
    unique_id = uuid4().hex[:8]
    attributes = {
        "external_thread_id": f"thread_{unique_id}",
        "title": "Test Email Thread",
        "labels": [EmailLabel.INBOX],
        **kwargs,
    }
    if "organization_id" not in attributes:
        organization = await create_organization()
        attributes["organization_id"] = organization.id
    if "creator_id" not in attributes:
        user = await create_user(organization_id=attributes["organization_id"])
        attributes["creator_id"] = user.id

    return await EmailThread.create(**attributes)


async def create_email_contact(**kwargs) -> EmailContact:
    unique_id = uuid4().hex[:8]
    attributes = {"email": f"contact{unique_id}@example.com", "name": f"Contact {unique_id}", **kwargs}

    if "organization_id" not in attributes:
        organization = await create_organization()
        attributes["organization_id"] = organization.id
    if "user_id" not in attributes:
        user = await create_user(organization_id=attributes["organization_id"])
        attributes["user_id"] = user.id

    return await EmailContact.create(**attributes)


async def create_mailbox_entry(**kwargs) -> MailboxEntry:
    attributes = {
        "title": "Test Mailbox Entry",
        "preview": "Test preview content",
        "last_comment": "Test comment",
        "senders": ["Test Sender <sender@example.com>"],
        "labels": [EmailLabel.INBOX, EmailLabel.UNREAD],
        **kwargs,
    }
    if "resource_gid" not in attributes:
        email_thread = await create_email_thread()
        attributes["resource_gid"] = email_thread.global_id
    if "owner_id" not in attributes:
        user = await create_user()
        attributes["owner_id"] = user.id
        if "organization_id" not in attributes:
            attributes["organization_id"] = user.organization_id
    if "last_comment_author_id" not in attributes:
        author = await create_user()
        attributes["last_comment_author_id"] = author.id

    return await MailboxEntry.create(**attributes)


async def create_mailbox_view(**kwargs) -> MailboxView:
    attributes = {
        "title": "Test View",
        "view_request": "Show me important emails",
        **kwargs,
    }
    if "user_id" not in attributes:
        user = await create_user()
        attributes["user_id"] = user.id
        if "organization_id" not in attributes:
            attributes["organization_id"] = user.organization_id
    if "organization_id" not in attributes:
        organization = await create_organization()
        attributes["organization_id"] = organization.id

    return await MailboxView.create(**attributes)


async def create_research_question(**kwargs) -> ResearchQuestion:
    attributes = {"body": "Test research question", "sources": [ResearchSource.INTERNAL], **kwargs}
    if "creator_id" not in attributes:
        user = await create_user()
        attributes["creator_id"] = user.id

    return await ResearchQuestion.create(**attributes)


async def create_scheduled_research(**kwargs) -> ScheduledResearch:
    attributes = {
        "prompt": "Summarize last week's SaaS funding rounds",
        "sources": [ResearchSource.INTERNAL],
        "schedule_cron": "0 9 * * 1",
        **kwargs,
    }
    if "creator_id" not in attributes:
        creator = await create_user()
        attributes["creator_id"] = creator.id
        if "organization_id" not in attributes:
            attributes["organization_id"] = creator.organization_id
    if "organization_id" not in attributes:
        user = await User.get(id=attributes["creator_id"])
        attributes["organization_id"] = user.organization_id

    return await ScheduledResearch.create(**attributes)


async def create_group(**kwargs) -> Group:
    attributes = {"name": "Test Group", **kwargs}

    if "organization_id" not in attributes:
        organization = await create_organization()
        attributes["organization_id"] = organization.id

    return await Group.create(**attributes)


async def create_group_member(group_id: UUID, user_id: UUID) -> GroupMember:
    member, _ = await GroupMember.get_or_create(group_id=group_id, user_id=user_id)
    return member


async def create_event(workspace: Workspace, *, creator_id: UUID, action: EventAction) -> Event:
    """Materialize a saved Event on `workspace`. Use when a test needs to call
    a resolver method (resolve_for_push / resolve_for_email / ...) without
    threading through Notifier."""
    async with workspace.record(action, creator_id=creator_id) as recording:
        pass
    return recording.event


async def create_post_group_mute(user_id: UUID, group_id: UUID) -> PostGroupMute:
    await PostGroupMute.mute(user_id=user_id, group_id=group_id)
    return await PostGroupMute.get(user_id=user_id, group_id=group_id)


async def create_chat(**kwargs) -> Chat:
    attributes = {**kwargs}
    explicit_creator = "creator_id" in attributes

    if "organization_id" not in attributes:
        organization = await create_organization()
        attributes["organization_id"] = organization.id

    if not explicit_creator:
        creator = await create_user(organization_id=attributes["organization_id"])
        attributes["creator_id"] = creator.id

    chat = await Chat.create(**attributes)

    # Workspace post_save adds the creator as a Collaborator. When the caller didn't
    # specify a creator, the creator is a throwaway used only to satisfy FK/signal
    # plumbing — drop their Collaborator row so membership reflects only the
    # create_collaborator calls the test makes.
    if not explicit_creator:
        await (
            Collaborator.unscoped.get_queryset()
            .filter(workspace_id=chat.workspace_id, user_id=attributes["creator_id"])
            .delete()
        )

    return chat


async def create_chat_message(**kwargs) -> ChatMessage:
    attributes = {"content": "Test message", **kwargs}

    if "chat_id" not in attributes:
        chat = await create_chat()
        attributes["chat_id"] = chat.id
    if "user_id" not in attributes:
        user = await create_user()
        attributes["user_id"] = user.id

    message = await ChatMessage.create(**attributes)
    await Chat.sync_last_message(message.chat_id)
    return message


notion_connection_count = 0


async def create_notion_connection(**kwargs) -> NotionConnection:
    global notion_connection_count
    notion_connection_count += 1

    attributes = {
        "access_token": f"secret_test_token_{notion_connection_count}",
        "workspace_id": f"workspace-{notion_connection_count}",
        "workspace_name": f"Test Workspace {notion_connection_count}",
        "bot_id": f"bot-{notion_connection_count}",
        **kwargs,
    }
    if "user_id" not in attributes:
        user = await create_user()
        attributes["user_id"] = user.id

    return await NotionConnection.create(**attributes)


notion_page_count = 0


async def create_notion_page(**kwargs) -> NotionPage:
    global notion_page_count
    notion_page_count += 1

    attributes = {
        "notion_page_id": f"page-{notion_page_count}",
        "title": f"Test Page {notion_page_count}",
        **kwargs,
    }
    if "notion_connection_id" not in attributes:
        connection_kwargs = {"user_id": attributes["user_id"]} if "user_id" in attributes else {}
        connection = await create_notion_connection(**connection_kwargs)
        attributes["notion_connection_id"] = connection.id
        attributes.setdefault("user_id", connection.user_id)
    elif "user_id" not in attributes:
        connection = await NotionConnection.get(id=attributes["notion_connection_id"])
        attributes["user_id"] = connection.user_id

    return await NotionPage.create(**attributes)
