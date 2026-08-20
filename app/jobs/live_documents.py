from pydantic import Field

from app.jobs.content import ContentIndexingJob
from app.jobs.notifications import Notifier
from app.models.accounts import User
from app.models.collaboration.live import LiveDocument
from app.models.collaboration.workspace import Attachment, WorkspaceMixin
from app.models.workspaces.documents import Document
from app.models.workspaces.meetings import Meeting
from config import logger
from config.enums import EventAction, JobQueue
from infra.jobs import JobDefinition, enqueue_job
from infra.messaging import Topic


class MergeAndNotifyLiveDocuments(JobDefinition):
    minutes: int = Field(15)
    default_queue = JobQueue.MISCELLANEOUS
    is_recurring = True
    retry_count = 0

    async def perform(self):
        await self._notify_meeting_agenda_updates()
        await self._notify_document_mentions()

    async def _notify_meeting_agenda_updates(self):
        async for topic, editors, markdown in LiveDocument.merge_stable_topics(self.minutes, stream="meeting_agenda"):
            resource = await self._resolve_resource(topic)
            if not resource:
                logger.warning(f"Could not resolve resource for topic {topic.name}, skipping notification")
                continue

            editor_users = await User.filter(id__in=editors)
            # Single editor → attribute the notification to them; multiple → system notification (no creator)
            creator = editor_users[0] if len(editor_users) == 1 else None

            notifier = Notifier(resource, creator)
            async with notifier.record_and_notify(EventAction.MEETING_AGENDA_UPDATED) as recording:
                recording.event.details.update(
                    {
                        "editor_ids": [str(user.id) for user in editor_users],
                        "document_content": markdown,
                        "topic_params": topic.params,
                    }
                )

            await Attachment.claim_for_live_document_content(resource.workspace_id, markdown)

            # Live agenda edits arrive over WebSocket and never hit the HTTP index dependency, so
            # re-index here — the one path that observes settled collaborative edits.
            await self._reindex_resource(resource)

    async def _notify_document_mentions(self):
        async for topic, editors, markdown in LiveDocument.merge_stable_topics(self.minutes, stream="document"):
            resource = await self._resolve_resource(topic)
            if not resource:
                logger.warning(f"Could not resolve resource for topic {topic.name}, skipping notification")
                continue

            editor_users = await User.filter(id__in=editors)

            # The editors set has no ordering, so when multiple editors collaborated we pick
            # the last one arbitrarily as the mention "creator" (shown in the notification email).
            # With a single editor we know exactly who typed the mention.
            creator = editor_users[0] if editor_users else None
            creator_id = creator.id if creator else resource.creator_id

            # Mentions are created without an associated Event since documents don't generate
            # content-updated events. This works for email delivery but would need a Recording
            # context if Document.email_delivery ever changes to SKIP.
            mentions = await resource.workspace.resolve_mentions(markdown, creator_id, recordable=resource)
            await Notifier(resource).notify_mentions(mentions)

            await Attachment.claim_for_live_document_content(resource.workspace_id, markdown)

            # Body edits arrive over WebSocket and never hit the HTTP index dependency, so
            # re-index here — the one path that observes settled collaborative edits.
            await self._reindex_resource(resource)

    async def _reindex_resource(self, resource: WorkspaceMixin) -> None:
        job = ContentIndexingJob.from_model(resource.organization_id, resource)
        job.unique = True
        await enqueue_job(job)

    async def _resolve_resource(self, topic: Topic) -> WorkspaceMixin | None:
        if topic.stream == "meeting_agenda":
            meeting_id = topic.params.get("meeting_id")
            if not meeting_id:
                return None
            return await Meeting.get_or_none(id=meeting_id).prefetch_related("workspace__collaborators__user")

        if topic.stream == "document":
            document_id = topic.params.get("document_id")
            if not document_id:
                return None
            return await Document.get_or_none(id=document_id).prefetch_related("workspace__collaborators__user")

        logger.warning(f"Unexpected stream '{topic.stream}' in MergeAndNotifyLiveDocuments")
        return None
