import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, ClassVar
from uuid import UUID

from tortoise import BaseDBAsyncClient, Tortoise
from tortoise.expressions import Q

from app.models.accounts import USER_EMAIL_MAX_LENGTH, User
from app.models.collaboration.content import Content, IndexingID, IndexMetadata, SearchableData
from app.models.collaboration.workspace import CommentMixin, Decision, Workspace
from app.models.workspaces.chat import Chat, ChatMessage
from app.models.workspaces.documents import Document
from app.models.workspaces.email.address import EmailAddress
from app.models.workspaces.email.contact import EmailContact
from app.models.workspaces.email.thread import EmailThread
from app.models.workspaces.goals import Goal, GoalUpdate
from app.models.workspaces.meetings import Meeting
from app.models.workspaces.posts import Post, PostComment
from app.prompts import build_prompt
from config import settings
from config.enums import AccessAction, ContentCategory, ContentType, JobQueue, Sharing
from infra.db import Change, GlobalID, Observer, RecordModel, SoftDeleteableMixin, allow_soft_deleted, transaction
from infra.jobs import JobDefinition, enqueue_job
from lib.email_reply_parser import strip_email_reply_quotes
from lib.markdown import markdown_to_plain_text

#
# In-app indexing
#
#

# Forward declarations for MODEL_TO_JOB_MAP, populated after job class definitions
MODEL_TO_JOB_MAP: dict[type[RecordModel], type[JobDefinition]] = {}


def _sum_reactions(comments: Iterable[CommentMixin]) -> int:
    return sum(len(user_ids) for comment in comments for user_ids in comment.reactions.values())


async def _index_workspace_decisions(organization_id: UUID, workspace_id: UUID) -> dict[str, Any]:
    """Refresh the workspace's decisions and return the parent resource's decision metadata.

    Called by each parent indexing job so that (a) the parent Content row records a
    decision_count plus the decided comment gids, and (b) every discrete decision row is
    re-indexed whenever its parent (or a comment within it) is, keeping the decision's
    indexed text — the anchored comment body — fresh after edits.

    decision_count counts all Decision rows in the workspace, including any whose anchor
    comment is tombstoned and therefore not individually retrievable as a decision row.
    The count is thus >= the number of retrievable decision rows; that asymmetry is
    intentional (it reflects how many decisions the content holds), not a bug.
    """
    decisions = await Decision.filter(workspace_id=workspace_id)
    # IndexDecisionJob.unique dedupes against the create/delete/cleanup enqueues; it never
    # enqueues the parent, so there is no re-index loop.
    for decision in decisions:
        await enqueue_job(IndexDecisionJob.from_model(organization_id, decision))
    return {
        "decision_count": len(decisions),
        "decided_comment_gids": [str(decision.comment_gid) for decision in decisions],
    }


class ContentIndexingJob(JobDefinition):
    default_queue = JobQueue.INDEXING
    retry_count: ClassVar[int] = 15
    indexing_id: IndexingID

    @classmethod
    def from_model(cls, organization_id: UUID, model: RecordModel):
        # If called on a specific subclass, create that instance directly
        if cls is not ContentIndexingJob:
            return cls(indexing_id=IndexingID(organization_id=organization_id, source_id=str(model.global_id)))

        # If called on base class, dispatch to appropriate specific job class
        job_class = MODEL_TO_JOB_MAP.get(model.__class__)
        if job_class and issubclass(job_class, ContentIndexingJob):
            return job_class.from_model(organization_id, model)

        raise ValueError(f"No indexing job defined for model type: {model.__class__.__name__}")

    async def fetch_model[T: RecordModel](self, expected_type: type[T]) -> T | None:
        """Fetches the model allowing soft deletes. Returns None if not found or wrong type."""
        async with allow_soft_deleted():
            model = await GlobalID.parse(self.indexing_id.source_id).get_or_none()

        if not model or not isinstance(model, expected_type):
            return None
        return model

    async def handle_deletion(self, model: RecordModel) -> bool:
        """
        Returns True if model was deleted (job should stop).
        Override for custom cleanup logic.
        """
        if hasattr(model, "is_deleted") and model.is_deleted:
            await Content.get_by_indexing_id(self.indexing_id).delete()
            return True
        return False


class IndexPostJob(ContentIndexingJob):
    async def handle_deletion(self, model: RecordModel) -> bool:
        if not isinstance(model, Post):
            return await super().handle_deletion(model)
        if model.is_deleted:
            await Content.get_by_indexing_id(self.indexing_id).delete()
            async with allow_soft_deleted():
                all_comments = await PostComment.filter(post_id=model.id)
                comment_global_ids = [str(comment.global_id) for comment in all_comments]
            if comment_global_ids:
                await Content.filter(
                    Content.filters.by_organization(model.organization_id)
                    & Content.filters.by_source_id_in(comment_global_ids)
                ).delete()
            return True
        return False

    async def perform(self):
        post = await self.fetch_model(Post)
        if not post or await self.handle_deletion(post):
            return

        await post.fetch_related("creator", "comments__user", "workspace__collaborators", "workspace__events")
        content_lines = [f"# Post: {post.title} - {post.created_at}\n"]
        if post.is_draft:
            content_lines.append("Status: draft")
        for comment in post.comments:
            content_lines.append(f"## Comment by {comment.user.display_name} at {comment.created_at}")
            content_lines.append(f"{comment.content}\n")

        if post.is_draft:
            force_sharing = Sharing.PRIVATE
            allowed_user_ids = post.collaboration.accessor_ids
        else:
            force_sharing = post.sharing
            allowed_user_ids = post.commenter_ids

        decision_metadata = await _index_workspace_decisions(post.organization_id, post.workspace_id)

        indexer = await self.indexing_id.fetch_indexer()
        await indexer.index(
            SearchableData(
                post.title,
                "\n".join(content_lines),
                str(post.global_id),
                post.creator.display_name,
                post.original_comment.content if post.original_comment else "",
            ),
            IndexMetadata(
                ContentCategory.DOCUMENT,
                ContentType.POST,
                force_sharing=force_sharing,
                allowed_user_ids=allowed_user_ids,
                created_at=post.created_at,
                updated_at=post.indexing_activity_at,
                reaction_count=_sum_reactions(post.comments),
                **decision_metadata,
            ),
        )

        async with allow_soft_deleted():
            all_comments = await PostComment.filter(post_id=post.id)
            all_comment_global_ids = [str(comment.global_id) for comment in all_comments]

        if all_comment_global_ids:
            await Content.filter(
                Content.filters.by_organization(post.organization_id)
                & Content.filters.by_source_id_in(all_comment_global_ids)
            ).delete()

        for comment in post.comments:
            indexing_id = IndexingID(
                organization_id=post.organization_id,
                source_id=str(comment.global_id),
            )
            indexer = await indexing_id.fetch_indexer()
            await indexer.index(
                SearchableData(
                    f"Commented on {post.title}",
                    comment.content,
                    str(comment.global_id),
                    comment.user.display_name,
                    comment.content,
                ),
                IndexMetadata(
                    ContentCategory.ACTIVITY,
                    ContentType.POST_COMMENT,
                    force_sharing=post.sharing,
                    allowed_user_ids=post.commenter_ids,
                    created_at=comment.created_at,
                    updated_at=comment.updated_at,
                    post_id=str(post.id),
                ),
            )


class IndexMeetingJob(ContentIndexingJob):
    def _get_meeting_lookup_metadata(self, meeting: Meeting) -> tuple[str, int]:
        lookup_key = f"meeting:{meeting.provider_meeting_id or meeting.id}"

        if not meeting.scheduled_at:
            return lookup_key, 0

        now = datetime.now(UTC)

        if meeting.scheduled_at > now:
            return lookup_key, 1

        lookup_priority = int(meeting.scheduled_at.timestamp())

        if meeting.processed_transcript:
            lookup_priority += 2
        elif meeting.summary:
            lookup_priority += 1

        return lookup_key, lookup_priority

    async def handle_deletion(self, model: RecordModel) -> bool:
        if not isinstance(model, Meeting):
            return await super().handle_deletion(model)
        if model.is_deleted:
            await Content.get_by_indexing_id(self.indexing_id).delete()
            # Raw SQL avoids Tortoise's CAST(source_id AS VARCHAR) which prevents index usage
            connection = Tortoise.get_connection("default")
            await connection.execute_query(
                'DELETE FROM "content" WHERE "organization_id" = $1 AND "source_id" LIKE $2',
                [str(model.organization_id), f"{model.global_id}%"],
            )
            return True
        return False

    async def perform(self):
        meeting = await self.fetch_model(Meeting)
        if not meeting or await self.handle_deletion(meeting):
            return

        await meeting.fetch_related("workspace__collaborators", "workspace__events")
        # Index the live agenda the editor writes; meeting.agenda (text field) is only set by an
        # explicit HTTP PATCH and is stale for agendas edited collaboratively.
        agenda_markdown = await meeting.get_agenda_markdown() or meeting.agenda or ""
        content = build_prompt("meetings/show.md.jinja", meeting=meeting, agenda=agenda_markdown)
        attendees = ", ".join([attendee.display_name for attendee in meeting.attendees if attendee.display_name])

        lookup_key, lookup_priority = self._get_meeting_lookup_metadata(meeting)
        # indexing_activity_at scans workspace.events, so compute it once rather than per transcript chunk.
        activity_at = meeting.indexing_activity_at

        indexer = await self.indexing_id.fetch_indexer()
        await indexer.index(
            SearchableData(
                meeting.title, content, str(meeting.global_id), attendees, meeting.summary or agenda_markdown
            ),
            IndexMetadata(
                ContentCategory.ACTIVITY,
                ContentType.MEETING,
                force_sharing=meeting.sharing,
                allowed_user_ids=meeting.collaboration.accessor_ids,
                created_at=meeting.created_at,
                updated_at=activity_at,
                lookup_key=lookup_key,
                lookup_priority=lookup_priority,
                scheduled_at=meeting.scheduled_at,
            ),
        )

        if meeting.processed_transcript:
            for chunk in meeting.processed_transcript.chunked():
                if not chunk.lines:
                    continue

                first_timestamp = chunk.lines[0].start_time
                source_id = f"{meeting.global_id}#timestamp-{first_timestamp}"
                content = str(chunk)

                indexer = IndexingID(
                    organization_id=meeting.organization_id,
                    source_id=source_id,
                )
                indexer = await indexer.fetch_indexer()
                await indexer.index(
                    SearchableData(
                        f"Transcript highlight from {meeting.title}",
                        content,
                        source_id,
                        attendees,
                        content[:500],
                    ),
                    IndexMetadata(
                        ContentCategory.ACTIVITY,
                        ContentType.MEETING_TRANSCRIPT,
                        force_sharing=meeting.sharing,
                        allowed_user_ids=meeting.collaboration.accessor_ids,
                        created_at=meeting.created_at,
                        updated_at=activity_at,
                        meeting_id=str(meeting.id),
                        lookup_key=None,
                        lookup_priority=0,
                    ),
                )


class IndexUserJob(ContentIndexingJob):
    async def perform(self):
        user = await self.fetch_model(User)
        if not user or await self.handle_deletion(user):
            return

        await user.fetch_related("email_aliases")
        emails = [alias.address for alias in user.email_aliases]
        content = f"{user.display_name}\n{'\n'.join(emails)}\n\n{user.bio}"

        indexer = await self.indexing_id.fetch_indexer()
        await indexer.index(
            SearchableData(user.display_name, content, str(user.global_id), user.display_name),
            IndexMetadata(
                ContentCategory.PERSON,
                ContentType.USER,
                force_sharing=Sharing.ORGANIZATION,
                created_at=user.created_at,
                updated_at=user.updated_at,
            ),
        )

        all_user_emails = [user.email] + emails
        duplicate_contacts = await EmailContact.filter(
            EmailContact.filters.by_organization(user.organization_id)
            & EmailContact.filters.by_emails(all_user_emails)
        )
        for duplicate_contact in duplicate_contacts:
            await enqueue_job(IndexEmailContactJob.from_model(user.organization_id, duplicate_contact))


class IndexEmailContactJob(ContentIndexingJob):
    async def perform(self):
        email_contact = await self.fetch_model(EmailContact)
        if not email_contact:
            return

        await email_contact.fetch_related("user")

        if len(email_contact.email) > USER_EMAIL_MAX_LENGTH:
            user_exists_with_email = False
        else:
            user_exists_with_email = await User.filter(
                User.filters.by_organization(email_contact.organization_id)
                & User.filters.by_any_email([email_contact.email])
                & User.filters.nondeleted
            ).exists()

        if user_exists_with_email:
            await Content.get_by_indexing_id(self.indexing_id).delete()
            return

        display_name = email_contact.name or email_contact.email
        content = f"{display_name}\n{email_contact.email}"

        indexer = await self.indexing_id.fetch_indexer()
        await indexer.index(
            SearchableData(display_name, content, str(email_contact.global_id), display_name),
            IndexMetadata(
                ContentCategory.PERSON,
                ContentType.EMAIL_CONTACT,
                force_sharing=Sharing.PRIVATE,
                allowed_user_ids=[email_contact.user_id],
                created_at=email_contact.created_at,
                # Use last_interacted_at so the lookup recency boost reflects how recently
                # the user actually emailed this contact, not when the record was synced.
                updated_at=email_contact.last_interacted_at or email_contact.updated_at,
                last_interacted_at=email_contact.last_interacted_at,
            ),
        )


class IndexDecisionJob(ContentIndexingJob):
    # Collapse redundant jobs for one decision: the create, delete, and comment
    # cleanup paths can each enqueue for the same indexing_id, and every path
    # re-reads live state, so deduping pending jobs on (org, source_id) is safe.
    unique: bool = True

    @classmethod
    def observe_delete(cls) -> Observer:
        # Wired to Decision DELETE in app/main.py. Any path that deletes a Decision
        # instance (router, comment cleanup, post republish) leaves an orphaned
        # Content row whose body keeps the decision text searchable; this enqueues
        # the cleanup, which resolves no Decision and drops it. The model layer fires
        # the delete and stays free of an app.jobs import this way.
        async def enqueue_on_delete(
            instance: RecordModel, changes: dict[str, Change] = {}, using_db: BaseDBAsyncClient | None = None
        ):
            if not isinstance(instance, Decision):
                return
            # The row is already gone, so the org is resolved from the still-present
            # workspace rather than the deleted decision.
            workspace = await Workspace.get_or_none(id=instance.workspace_id, using_db=using_db)
            if not workspace:
                return
            indexing_id = IndexingID(organization_id=workspace.organization_id, source_id=str(instance.global_id))
            await enqueue_job(cls(indexing_id=indexing_id), using_db=using_db)

        return enqueue_on_delete

    async def perform(self):
        decision = await self.fetch_model(Decision)
        if not decision:
            await Content.get_by_indexing_id(self.indexing_id).delete()
            return

        # decided_by is nullable (SET_NULL); collaborators drive access — both are
        # explicit because lazy access would raise once outside the request scope.
        await decision.fetch_related("workspace__collaborators", "decided_by")
        resource = await decision.workspace.fetch_resource_or_none()
        if not resource or resource.is_deleted:
            await Content.get_by_indexing_id(self.indexing_id).delete()
            return

        # Resolve the anchor comment unscoped: the default manager hides a
        # soft-deleted comment, but a tombstoned anchor must drop the decision row
        # (its body is no longer canonical) rather than keep stale text searchable.
        async with allow_soft_deleted():
            comment = await decision.comment_gid.get_or_none()
        if not isinstance(comment, CommentMixin) or (isinstance(comment, SoftDeleteableMixin) and comment.is_deleted):
            await Content.get_by_indexing_id(self.indexing_id).delete()
            return

        # Guard the deleted-decider case: str(None) / None.display_name would crash.
        author = decision.decided_by.display_name if decision.decided_by else None
        decided_by_id = str(decision.decided_by_id) if decision.decided_by_id else None

        title = f"Decision in {resource.title}"
        content = f"**{title}**\n\n{comment.content}"

        indexer = await self.indexing_id.fetch_indexer()
        await indexer.index(
            SearchableData(title, content, str(resource.global_id), author, comment.content),
            IndexMetadata(
                ContentCategory.ACTIVITY,
                ContentType.DECISION,
                force_sharing=resource.sharing,
                allowed_user_ids=resource.collaboration.accessor_ids,
                created_at=decision.decided_at,
                updated_at=decision.decided_at,
                decided_by_id=decided_by_id,
                comment_gid=str(decision.comment_gid),
                resource_gid=str(resource.global_id),
            ),
        )


class IndexGoalJob(ContentIndexingJob):
    def _build_goal_content_lines(self, goal: Goal, header_prefix: str = "# Goal:") -> list[str]:
        lines = [f"{header_prefix} {goal.title}"]
        lines.append(goal.description)
        lines.append(f"Creator: {goal.creator.display_name}")
        if goal.owner:
            lines.append(f"Owner: {goal.owner.display_name}")
        if goal.group:
            lines.append(f"Group: {goal.group.name}")

        if goal.target_date:
            lines.append(f"Target date: {goal.target_date}")
        if goal.start_date:
            lines.append(f"Start date: {goal.start_date}")

        status_display = goal.status.value.replace("_", " ")
        lines.append(f"Status: {status_display}")
        progress_display = f"{int(goal.progress * 100)}%" if goal.progress is not None else "Not tracked"
        lines.append(f"Progress: {progress_display}")

        if goal.is_completed and goal.completed_at:
            completed_line = f"Completed at: {goal.completed_at.date()}"
            if goal.target_date:
                days_diff = (goal.target_date - goal.completed_at.date()).days
                if days_diff > 0:
                    completed_line += f" ({days_diff} day{'s' if days_diff != 1 else ''} early)"
                elif days_diff < 0:
                    days_late = abs(days_diff)
                    completed_line += f" ({days_late} day{'s' if days_late != 1 else ''} late)"
                else:
                    completed_line += " (on target)"
            lines.append(completed_line)
        elif goal.is_closed:
            lines.append("Closed - incomplete")

        if goal.extras:
            for key, value in goal.extras.items():
                lines.append(f"{key}: {value}")

        return lines

    async def handle_deletion(self, model: RecordModel) -> bool:
        if not isinstance(model, Goal):
            return await super().handle_deletion(model)
        if model.is_deleted:
            await Content.get_by_indexing_id(self.indexing_id).delete()
            if not model.is_subgoal:
                async with allow_soft_deleted():
                    subgoals = await Goal.filter(parent_id=model.id)
                subgoal_global_ids = [str(subgoal.global_id) for subgoal in subgoals]
                if subgoal_global_ids:
                    await Content.filter(
                        Content.filters.by_organization(model.organization_id)
                        & Content.filters.by_source_id_in(subgoal_global_ids)
                    ).delete()
            return True
        return False

    async def perform(self):
        goal = await self.fetch_model(Goal)
        if not goal or await self.handle_deletion(goal):
            return

        if goal.is_subgoal:
            await goal.fetch_related(
                "creator", "parent", "comments", "workspace__collaborators", "workspace__events", "owner", "group"
            )
            # Re-index the parent so its embedded subgoal section stays current
            if goal.parent:
                await enqueue_job(
                    IndexGoalJob(
                        indexing_id=IndexingID(
                            organization_id=goal.organization_id, source_id=str(goal.parent.global_id)
                        )
                    )
                )
        else:
            await goal.fetch_related(
                "creator",
                "comments",
                "subgoals__creator",
                "subgoals__owner",
                "subgoals__group",
                "workspace__collaborators",
                "workspace__events",
                "owner",
                "group",
            )

        content_lines = self._build_goal_content_lines(goal)

        if goal.is_subgoal and goal.parent:
            content_lines.append(f"Parent goal: {goal.parent.title}")
        elif goal.subgoals:
            content_lines.append("\n## Subgoals\n")
            for subgoal in goal.subgoals:
                content_lines.append("")
                content_lines.extend(self._build_goal_content_lines(subgoal, header_prefix="### Subgoal:"))

        goal_updates = (
            await GoalUpdate.filter(GoalUpdate.filters.completed_for_goal(goal.id))
            .order_by("-created_at")
            .prefetch_related("creator")
        )
        if goal_updates:
            content_lines.append("\n## Updates\n")
            for update in goal_updates:
                if update.answer_text:
                    content_lines.append(f"### Update from {update.creator.display_name} at {update.updated_at}")
                    content_lines.append(f"**{update.question_text}**\n{update.answer_text}\n")

        indexer = await self.indexing_id.fetch_indexer()
        await indexer.index(
            SearchableData(goal.title or "", "\n".join(content_lines), str(goal.global_id), goal.creator.display_name),
            IndexMetadata(
                ContentCategory.DOCUMENT,
                ContentType.GOAL,
                force_sharing=goal.sharing,
                allowed_user_ids=goal.collaboration.accessor_ids,
                created_at=goal.created_at,
                updated_at=goal.indexing_activity_at,
                reaction_count=_sum_reactions(goal.comments),
            ),
        )


class IndexGoalUpdateJob(ContentIndexingJob):
    @classmethod
    def from_model(cls, organization_id: UUID, model: RecordModel):
        if isinstance(model, GoalUpdate):
            goal_global_id = GlobalID.create("Goal", model.goal_id)
            return IndexGoalJob(indexing_id=IndexingID(organization_id=organization_id, source_id=str(goal_global_id)))
        return super().from_model(organization_id, model)


class IndexDocumentJob(ContentIndexingJob):
    async def perform(self):
        document = await self.fetch_model(Document)
        if not document or await self.handle_deletion(document):
            return

        await document.fetch_related("creator", "document_comments", "workspace__collaborators", "workspace__events")
        content = await document.get_live_document_markdown()
        decision_metadata = await _index_workspace_decisions(document.organization_id, document.workspace_id)

        indexer = await self.indexing_id.fetch_indexer()
        await indexer.index(
            SearchableData(document.title, content, str(document.global_id), document.creator.display_name),
            IndexMetadata(
                ContentCategory.DOCUMENT,
                ContentType.DOCUMENT,
                force_sharing=document.sharing,
                allowed_user_ids=document.collaboration.accessor_ids,
                created_at=document.created_at,
                updated_at=document.indexing_activity_at,
                reaction_count=_sum_reactions(document.document_comments),
                **decision_metadata,
            ),
        )


CALENDAR_ATTACHMENT_CONTENT_TYPES = {"text/calendar", "application/ics"}
AUTOMATED_SENDER_REGEX = re.compile(
    r"\b(do-?not-?reply|no-?reply|mailer-daemon|postmaster|notifications|github-actions|newsletter|bot)\b",
    re.IGNORECASE,
)


class IndexEmailThreadJob(ContentIndexingJob):
    async def perform(self):
        email_thread = await self.fetch_model(EmailThread)
        if not email_thread:
            return

        await email_thread.fetch_related(
            "messages__attachments__file",
            "creator",
            "workspace__collaborators",
            "workspace__events",
            "comments__user",
            "workspace__assignee",
        )

        conversation = email_thread.sorted_conversation
        if not conversation:
            return

        # `comments` is the reverse relation, which bypasses EmailThreadComment's
        # NonDeletedManager — filter out soft-deleted comments so they're not indexed.
        active_comments = [comment for comment in email_thread.comments if not comment.is_deleted]

        # Skip indexing notification emails sent by this app — they duplicate content already
        # indexed as Posts/Goals/etc. Still index if users added thread comments, since those
        # are unique content not present on the original resource.
        if conversation[0].is_from(settings.email_from) and not active_comments:
            await Content.get_by_indexing_id(self.indexing_id).delete()
            # Still refresh the workspace's decisions on this early-return path: a decision
            # anchored to a comment that was just soft-deleted (leaving the thread with no
            # indexable content) must drop its now-stale searchable body, and only
            # IndexDecisionJob does that — reached via _index_workspace_decisions.
            await _index_workspace_decisions(email_thread.organization_id, email_thread.workspace_id)
            return

        content_lines = [f"# Email Thread: {email_thread.title}"]
        content_lines.append(f"Last message: {email_thread.last_message_at}")
        content_lines.append(f"Message count: {len(conversation)}")

        if email_thread.collaboration.is_assigned and email_thread.workspace.assignee:
            content_lines.append(f"Assigned to: {email_thread.workspace.assignee.display_name}")

        content_lines.append("## Messages:\n")
        for message in conversation:
            content_lines.append(f"## From: {message.sender or 'Unknown'}")
            content_lines.append(f"### To: {', '.join(message.to) if message.to else 'Unknown'}")
            if message.cc:
                content_lines.append(f"### Cc: {', '.join(message.cc)}")

            if message.sent_at:
                content_lines.append(f"### Sent at: {message.sent_at}")
            elif message.received_at:
                content_lines.append(f"### Received at: {message.received_at}")

            if message.body_plain:
                stripped_body = strip_email_reply_quotes(message.body_plain)
                content_lines.append(f"### Body:\n{stripped_body}")
            content_lines.append("\n---\n")

        if active_comments:
            content_lines.append("## Comments:\n")

            for comment in active_comments:
                content_lines.append(f"### Comment by {comment.user.display_name} at {comment.created_at}")
                content_lines.append(f"{comment.content}\n")

        content = "\n".join(content_lines)

        participants = email_thread.participant_addresses
        participant_emails = [participant.email for participant in participants]
        commenters = [
            EmailAddress(comment.user.display_name, comment.user.email)
            for comment in active_comments
            if comment.user.email not in participant_emails
        ]

        seen_emails: dict[str, EmailAddress] = {}
        for participant in participants + commenters:
            email_lower = participant.email.lower()
            if email_lower not in seen_emails or (
                participant.display_name and not seen_emails[email_lower].display_name
            ):
                seen_emails[email_lower] = participant

        authors_list = []
        # If present, the research email should be listed first in the authors to enable filtering to use the index.
        if research_email := seen_emails.pop(settings.research_email_from, None):
            authors_list.append(research_email.display_name or research_email.email)

        authors_list.extend(addr.display_name for addr in seen_emails.values() if addr.display_name)

        authors = ", ".join(authors_list)

        last_message = conversation[-1]
        stripped = strip_email_reply_quotes(last_message.body_plain) if last_message.body_plain else ""
        preview = stripped or last_message.body_plain or ""

        has_calendar_invite = any(
            (attachment.file.content_type or "").lower() in CALENDAR_ATTACHMENT_CONTENT_TYPES
            for message in conversation
            for attachment in message.attachments
        )
        is_automated_sender = bool(AUTOMATED_SENDER_REGEX.search(conversation[0].sender or ""))

        decision_metadata = await _index_workspace_decisions(email_thread.organization_id, email_thread.workspace_id)

        indexer = await self.indexing_id.fetch_indexer()
        await indexer.index(
            SearchableData(
                email_thread.title or "No Subject",
                content,
                str(email_thread.global_id),
                authors,
                preview,
            ),
            IndexMetadata(
                ContentCategory.DOCUMENT,
                ContentType.EMAIL_THREAD,
                force_sharing=Sharing.PRIVATE,
                allowed_user_ids=email_thread.collaboration.accessor_ids,
                created_at=email_thread.created_at,
                updated_at=email_thread.indexing_activity_at,
                owner_user_id=email_thread.creator_id,
                message_count=len(conversation),
                comment_count=len(active_comments),
                has_calendar_invite=has_calendar_invite,
                is_automated_sender=is_automated_sender,
                reaction_count=_sum_reactions(active_comments),
                **decision_metadata,
            ),
        )


CHAT_PREVIEW_MAX_LENGTH = 200


class IndexChatJob(ContentIndexingJob):
    async def handle_deletion(self, model: RecordModel) -> bool:
        assert isinstance(model, Chat)
        if model.is_deleted:
            await Content.filter(
                Content.filters.by_organization(model.organization_id)
                & Content.filters.by_source_id_startswith(str(model.global_id))
            ).delete()
            return True
        return False

    async def perform(self):
        chat = await self.fetch_model(Chat)
        if not chat or await self.handle_deletion(chat):
            return

        if not await ChatMessage.filter(chat_id=chat.id).exists():
            await Content.get_by_indexing_id(self.indexing_id).delete()
            return

        await chat.fetch_related(
            "workspace__collaborators__user", "workspace__events", "messages", "last_message__user"
        )

        title = chat.resolved_title(viewer_id=None)
        collaborators = list(chat.workspace.collaborators)
        authors = ", ".join(c.user.display_name for c in collaborators if c.user)
        allowed_user_ids = [c.user_id for c in collaborators]

        preview_content = chat.last_message_preview(max_length=CHAT_PREVIEW_MAX_LENGTH)
        message_body = markdown_to_plain_text(chat.last_message.content) if chat.last_message else ""
        index_content = f"{title}\n{authors}"
        if message_body:
            index_content = f"{index_content}\n{message_body}"

        decision_metadata = await _index_workspace_decisions(chat.organization_id, chat.workspace_id)

        indexer = await self.indexing_id.fetch_indexer()
        await indexer.index(
            SearchableData(
                title,
                index_content,
                str(chat.global_id),
                author=authors,
                preview_content=preview_content,
            ),
            IndexMetadata(
                ContentCategory.DOCUMENT,
                ContentType.CHAT,
                force_sharing=Sharing.PRIVATE,
                allowed_user_ids=allowed_user_ids,
                created_at=chat.created_at,
                updated_at=chat.indexing_activity_at,
                reaction_count=_sum_reactions(chat.messages),
                **decision_metadata,
            ),
        )


async def invalidate_chat_history_indexing(
    organization_id: UUID,
    chat_global_id: str,
    message_created_at: datetime,
    using_db: BaseDBAsyncClient | None = None,
) -> None:
    # Delete the window containing the deleted message and all later windows,
    # resetting the watermark so the recurring job rebuilds from that point forward.
    await (
        Content.filter(
            Content.filters.by_organization(organization_id)
            & Content.filters.by_source_id_startswith(chat_global_id)
            & Q(content_type=ContentType.CHAT_HISTORY)
            & Q(updated_at__gte=message_created_at)
        )
        .using_db(using_db)
        .delete()
    )


#
# Chat history indexing
#
#

MERGE_THRESHOLD = 5
SPLIT_THRESHOLD = 100
SPLIT_TARGET = 50

# Cap messages per job run to bound memory; the watermark advances so the next run continues
MAX_MESSAGES_PER_RUN = 1000

# Cap stale-chat enqueues per recurring run to keep the scheduler tick bounded
STALE_CHATS_BATCH_LIMIT = 500


@dataclass
class ChatWindow:
    messages: list[ChatMessage]
    start: datetime
    end: datetime
    merged_start_date: date
    merged_end_date: date
    sequence: int | None = None

    def source_id(self, global_id: str) -> str:
        if self.merged_start_date != self.merged_end_date:
            base = f"{global_id}#window-{self.merged_start_date}--{self.merged_end_date}"
            return f"{base}-{self.sequence}" if self.sequence is not None else base
        if self.sequence is not None:
            return f"{global_id}#window-{self.start.date()}-{self.sequence}"
        return f"{global_id}#window-{self.start.date()}"

    @property
    def label(self) -> str:
        if self.merged_start_date != self.merged_end_date:
            base = f"{self.merged_start_date} to {self.merged_end_date}"
            return f"{base} (part {self.sequence + 1})" if self.sequence is not None else base
        if self.sequence is not None:
            return f"{self.start.date()} (part {self.sequence + 1})"
        return str(self.start.date())


class IndexChatHistoryJob(ContentIndexingJob):
    chat_id: UUID

    @staticmethod
    def build_adaptive_windows(messages: Sequence[ChatMessage]) -> list[ChatWindow]:
        if not messages:
            return []
        days = IndexChatHistoryJob._group_by_date(messages)
        merged_buckets = IndexChatHistoryJob._merge_thin_days(days)
        return IndexChatHistoryJob._split_large_buckets(merged_buckets)

    @staticmethod
    def _group_by_date(messages: Sequence[ChatMessage]) -> dict[date, list[ChatMessage]]:
        days: dict[date, list[ChatMessage]] = {}
        for message in messages:
            days.setdefault(message.created_at.date(), []).append(message)
        return days

    @staticmethod
    def _merge_thin_days(
        days: dict[date, list[ChatMessage]],
    ) -> list[tuple[date, date, list[ChatMessage]]]:
        sorted_dates = sorted(days.keys())
        merged_buckets: list[tuple[date, date, list[ChatMessage]]] = []
        carry: list[ChatMessage] = []
        carry_start: date | None = None

        for d in sorted_dates:
            day_msgs = days[d]
            if carry:
                carry.extend(day_msgs)
                if len(carry) >= MERGE_THRESHOLD and carry_start is not None:
                    merged_buckets.append((carry_start, d, carry))
                    carry = []
                    carry_start = None
            elif len(day_msgs) < MERGE_THRESHOLD:
                carry = list(day_msgs)
                carry_start = d
            else:
                merged_buckets.append((d, d, day_msgs))

        if carry:
            if merged_buckets:
                prev_start, _, prev_msgs = merged_buckets[-1]
                prev_msgs.extend(carry)
                merged_buckets[-1] = (prev_start, sorted_dates[-1], prev_msgs)
            elif carry_start is not None:
                merged_buckets.append((carry_start, sorted_dates[-1], carry))

        return merged_buckets

    @staticmethod
    def _split_large_buckets(
        merged_buckets: list[tuple[date, date, list[ChatMessage]]],
    ) -> list[ChatWindow]:
        windows: list[ChatWindow] = []
        for start_date, end_date, bucket_msgs in merged_buckets:
            if len(bucket_msgs) > SPLIT_THRESHOLD:
                for i in range(0, len(bucket_msgs), SPLIT_TARGET):
                    chunk = bucket_msgs[i : i + SPLIT_TARGET]
                    windows.append(
                        ChatWindow(
                            messages=chunk,
                            start=chunk[0].created_at,
                            end=chunk[-1].created_at,
                            sequence=i // SPLIT_TARGET,
                            merged_start_date=start_date,
                            merged_end_date=end_date,
                        )
                    )
            else:
                windows.append(
                    ChatWindow(
                        messages=bucket_msgs,
                        start=bucket_msgs[0].created_at,
                        end=bucket_msgs[-1].created_at,
                        merged_start_date=start_date,
                        merged_end_date=end_date,
                    )
                )
        return windows

    async def _find_watermark(self, chat: Chat) -> datetime | None:
        latest_chunk = (
            await Content.filter(
                organization_id=chat.organization_id,
                content_type=ContentType.CHAT_HISTORY,
                source_id__startswith=str(chat.global_id),
            )
            .order_by("-updated_at")
            .first()
        )
        since_raw = latest_chunk.metadata.get("window_end") if latest_chunk else None
        return datetime.fromisoformat(since_raw) if since_raw else None

    async def _index_window(
        self,
        window: ChatWindow,
        chat: Chat,
        chat_title: str,
        collaborator_names: str,
        collaborator_ids: list[UUID],
    ) -> None:
        source_id = window.source_id(chat.global_id)
        index_lines = [f"{m.user.display_name}: {m.content}" for m in window.messages if m.user]
        index_content = "\n".join(index_lines)
        preview = "\n".join(index_lines[:5])
        title = f"{chat_title} — {window.label}"

        indexer = await IndexingID(
            organization_id=chat.organization_id,
            source_id=source_id,
        ).fetch_indexer()

        await indexer.index(
            SearchableData(title, index_content, str(chat.global_id), collaborator_names, preview),
            IndexMetadata(
                ContentCategory.ACTIVITY,
                ContentType.CHAT_HISTORY,
                force_sharing=Sharing.PRIVATE,
                allowed_user_ids=collaborator_ids,
                created_at=window.start,
                updated_at=window.end,
                chat_id=str(chat.id),
                window_start=window.start.isoformat(),
                window_end=window.end.isoformat(),
            ),
        )

    async def perform(self):
        chat = await Chat.get_or_none(id=self.chat_id).prefetch_related("workspace__collaborators__user")
        if not chat:
            return

        collaborators = list(chat.workspace.collaborators)
        collaborator_ids = [c.user_id for c in collaborators]
        collaborator_names = ", ".join(sorted(c.user.display_name for c in collaborators if c.user))
        chat_title = chat.resolved_title(viewer_id=None)

        since = await self._find_watermark(chat)
        query = ChatMessage.filter(chat_id=chat.id)
        if since:
            query = query.filter(created_at__gt=since)
        messages = list(await query.order_by("created_at").limit(MAX_MESSAGES_PER_RUN).prefetch_related("user"))

        if not messages:
            return

        windows = self.build_adaptive_windows(messages)
        for window in windows:
            await self._index_window(window, chat, chat_title, collaborator_names, collaborator_ids)


CHAT_CONTENT_ACCESS_BATCH_SIZE = 200


class UpdateChatContentAccessJob(JobDefinition):
    default_queue = JobQueue.INDEXING
    chat_id: UUID
    user_id: UUID
    action: AccessAction
    records_processed_so_far: int = 0

    async def perform(self):
        chat = await Chat.get_or_none(id=self.chat_id)
        if not chat:
            return

        async with transaction() as connection:
            contents = await (
                Content.filter(
                    Content.filters.by_organization(chat.organization_id)
                    & Content.filters.by_source_id_startswith(str(chat.global_id))
                )
                .using_db(connection)
                .order_by("id")
                .limit(CHAT_CONTENT_ACCESS_BATCH_SIZE)
                .offset(self.records_processed_so_far)
                .select_for_update()
            )

            if not contents:
                return

            for content in contents:
                if self.action == AccessAction.ADD:
                    content.add_user(self.user_id)
                elif self.action == AccessAction.REMOVE:
                    content.remove_user(self.user_id)
            await Content.bulk_update(contents, fields=["allowed_user_ids"], using_db=connection)

        if len(contents) == CHAT_CONTENT_ACCESS_BATCH_SIZE:
            await enqueue_job(
                UpdateChatContentAccessJob(
                    chat_id=self.chat_id,
                    user_id=self.user_id,
                    action=self.action,
                    records_processed_so_far=self.records_processed_so_far + CHAT_CONTENT_ACCESS_BATCH_SIZE,
                    unique=True,
                )
            )


class ScheduleChatHistoryIndexingJob(JobDefinition):
    is_recurring = True
    default_queue = JobQueue.INDEXING
    retry_count: ClassVar[int] = 0

    async def perform(self):
        stale_chats = await self._find_stale_chats()
        for chat_id, org_id in stale_chats:
            await enqueue_job(
                IndexChatHistoryJob(
                    chat_id=chat_id,
                    indexing_id=IndexingID(organization_id=org_id, source_id=str(GlobalID.create("Chat", chat_id))),
                    unique=True,
                )
            )

    async def _find_stale_chats(self) -> list[tuple[UUID, UUID]]:
        connection = Tortoise.get_connection("default")
        rows = await connection.execute_query_dict(
            """
            SELECT chat.id, chat.organization_id
            FROM chat
            LEFT JOIN (
                SELECT
                    (metadata->>'chat_id')::uuid AS chat_id,
                    MAX(updated_at) AS latest_indexed
                FROM content
                WHERE content_type = $1
                GROUP BY (metadata->>'chat_id')::uuid
            ) idx ON idx.chat_id = chat.id
            WHERE chat.last_message_at IS NOT NULL
              AND chat.deleted_at IS NULL
              AND (idx.latest_indexed IS NULL OR chat.last_message_at > idx.latest_indexed)
            LIMIT $2
            """,
            [ContentType.CHAT_HISTORY, STALE_CHATS_BATCH_LIMIT],
        )
        return [(row["id"], row["organization_id"]) for row in rows]


MODEL_TO_JOB_MAP.update(
    {
        Post: IndexPostJob,
        Meeting: IndexMeetingJob,
        User: IndexUserJob,
        EmailContact: IndexEmailContactJob,
        Document: IndexDocumentJob,
        Goal: IndexGoalJob,
        GoalUpdate: IndexGoalUpdateJob,
        EmailThread: IndexEmailThreadJob,
        Chat: IndexChatJob,
        Decision: IndexDecisionJob,
    }
)
