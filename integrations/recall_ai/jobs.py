import asyncio
from datetime import UTC, date, datetime, timedelta
from urllib.parse import parse_qs, urlparse
from uuid import UUID

import httpx
from fastapi import status
from tortoise import BaseDBAsyncClient
from tortoise.expressions import Q

from app.jobs.content import ContentIndexingJob
from app.jobs.meetings import MeetingProcessingCompleteCallbackJob, ProcessTranscriptJob
from app.models.accounts import User
from app.models.workspaces.meetings import Meeting, MeetingJob
from config import logger
from config.enums import JobQueue
from infra.db import Change, Observer, RecordModel, allow_soft_deleted, transaction
from infra.jobs import JobDefinition, bulk_enqueue_jobs, enqueue_job, enqueue_job_group, enqueue_job_in_group
from infra.storage import store_file_from_stream
from integrations.recall_ai.client import RecallAIClient
from integrations.recall_ai.models import (
    RecallAIBotStatusCodes,
    RecallAIBotStatusData,
    RecallAIBotStatusSubCodes,
    RecallAICalendarEvent,
    RecallAICalendarUser,
    RecallAIMeeting,
)

#
# Bot Scheduling jobs
#
#


class ScheduleRecallAIBotJob(JobDefinition):
    default_queue = JobQueue.MISCELLANEOUS
    meeting_id: UUID

    @classmethod
    def observe_create(cls) -> Observer:
        async def enqueue_on_create(
            instance: RecordModel, changes: dict[str, Change] = {}, using_db: BaseDBAsyncClient | None = None
        ):
            global_id = instance.global_id
            if not global_id.record_id:
                return
            meeting = await global_id.get_or_none(using_db=using_db)
            if not isinstance(meeting, Meeting) or not meeting.is_joinable_by_recall:
                return

            recall_meeting = await RecallAIMeeting.get_or_none(meeting_id=global_id.record_id, using_db=using_db)
            if recall_meeting and recall_meeting.bot_id:
                logger.info(
                    f"Recall AI bot with bot ID already scheduled for meeting {global_id.record_id}", exc_info=True
                )
            if recall_meeting:
                logger.info(f"Recall AI bot already scheduled for meeting {global_id.record_id}", exc_info=True)
                return

            if meeting.manually_created_at:
                logger.info(f"Enqueuing ScheduleRecallAIBotJob for meeting {global_id.record_id}", exc_info=True)
                job = await enqueue_job(cls(meeting_id=global_id.record_id), using_db=using_db)
                await MeetingJob.create(meeting_id=global_id.record_id, job=job, using_db=using_db)

        return enqueue_on_create

    async def perform(self):
        meeting = await Meeting.get_or_none(id=self.meeting_id).prefetch_related("organization", "organization__users")
        if not meeting:
            return
        logger.info(f"Scheduling Recall.AI bot for meeting {str(meeting.id)}")

        if not meeting.is_joinable_by_recall or not meeting.manually_created_at:
            return
        recall_meeting, _ = await RecallAIMeeting.get_or_create(meeting_id=self.meeting_id)
        # Set the meeting instance in memory to avoid multiple database queries.
        # get_or_create does not support prefetch_related
        recall_meeting.meeting = meeting

        client = RecallAIClient()
        if not meeting.scheduled_at:
            logger.warning(f"Meeting {meeting.id} has no scheduled_at date")
            recall_meeting.mark_recall_ai_bot_unschedulable()
            if recall_meeting.is_unsaved:
                await recall_meeting.save(update_fields=recall_meeting.changes.keys())
            return
        elif meeting.is_happening_now and meeting.conferencing_url:
            recall_meeting.will_record = True
            bot = await client.create_bot(meeting.conferencing_url)
        elif meeting.is_upcoming and recall_meeting.is_schedulable and meeting.conferencing_url:
            bot = await client.create_scheduled_bot(meeting.conferencing_url, join_at=meeting.scheduled_at)
            recall_meeting.will_record = True
            recall_meeting.mark_recall_ai_bot_scheduled()
        else:
            logger.warning(f"Meeting {meeting.id} cannot be scheduled in recall")
            recall_meeting.will_record = False
            recall_meeting.mark_recall_ai_bot_unschedulable()
            if recall_meeting.is_unsaved:
                await recall_meeting.save(update_fields=recall_meeting.changes.keys())
            return

        try:
            recall_meeting.bot_id = bot["id"]
            recall_meeting.will_record = bot["id"] is not None

            if recall_meeting.is_unsaved:
                await recall_meeting.save(update_fields=recall_meeting.changes.keys())
        except KeyError:
            logger.error(f"Failed to create bot for meeting {meeting.id} - {bot}")
            return


class SyncTranscriptFromRecallAIJob(JobDefinition):
    default_queue = JobQueue.MISCELLANEOUS
    meeting_id: UUID

    async def perform(self):
        recall_meeting = await RecallAIMeeting.get_or_none(meeting_id=self.meeting_id).prefetch_related(
            "meeting__organization__users"
        )
        if not recall_meeting or not recall_meeting.bot_id:
            return

        meeting = recall_meeting.meeting

        client = RecallAIClient()
        transcript = await client.get_bot_transcript(recall_meeting.bot_id)

        if not transcript or not transcript.chunks:
            logger.warning(f"Transcript for meeting {recall_meeting.id} is empty")
            return

        meeting.transcript = transcript.model_dump_json()

        # Fetch meeting chat messages
        meeting_chat = await client.get_meeting_chat_messages(recall_meeting.bot_id)
        chat_messages = meeting_chat.results
        while True:
            if not meeting_chat.next:
                break
            meeting_chat = await client.get_meeting_chat_messages(recall_meeting.bot_id, cursor=meeting_chat.next)
            chat_messages += meeting_chat.results

        for message in chat_messages:
            message.created_at = datetime.fromisoformat(message.created_at)

        meeting.chat_messages = chat_messages
        meeting.did_recording_fail = False
        await meeting.save(update_fields=["transcript", "chat_messages", "did_recording_fail"])

        should_update_title = meeting.title == meeting.conferencing_url

        job = await enqueue_job_in_group(
            ProcessTranscriptJob(meeting_id=meeting.id, should_update_title=should_update_title, unique=True)
        )
        await MeetingJob.create(meeting=meeting, job=job)


class SyncRecordingFromRecallAIJob(JobDefinition):
    default_queue = JobQueue.MISCELLANEOUS
    meeting_id: UUID

    async def perform(self):
        recall_meeting = await RecallAIMeeting.get_or_none(meeting_id=self.meeting_id).prefetch_related(
            "meeting__organization__users"
        )

        if not recall_meeting or not recall_meeting.bot_id:
            return

        meeting = recall_meeting.meeting

        client = RecallAIClient()
        bot = await client.get_bot(recall_meeting.bot_id)

        if not bot.video_url:
            logger.warning(f"Recording for meeting {meeting.id} is empty")
            return

        video_timeout = httpx.Timeout(5.0, read=540.0, write=30.0)
        try:
            async with httpx.AsyncClient(timeout=video_timeout) as http_client:
                async with http_client.stream("GET", bot.video_url) as response:
                    file_ref = await store_file_from_stream(
                        streaming_response=response, filename=f"{meeting.id}.mp4", content_type="video/mp4"
                    )
        except httpx.ReadTimeout:
            logger.error(f"Timeout downloading video for meeting {meeting.id}")
            raise
        except Exception as e:
            logger.error(f"Error downloading video for meeting {meeting.id}: {str(e)}")
            raise

        if not file_ref:
            logger.error(f"Failed to store recording for meeting {meeting.id}")
            return

        meeting.recording_id = file_ref.id
        await meeting.save(update_fields=["recording_id"])


#
# Calendar v1 jobs
#
#


class CreateMeetingFromBotIDJob(JobDefinition):
    """
    This job is responsible for creating a meeting when a bot status event is first received from Recall.AI
    And there is no existing meeting for the bot. This is a fallback for meetings that were not created from
    calendar polling in advance.

    My hope was that this would not be necessary, but we still see it being called in the wild.
    If/when we migrate to the calendar v2 API, this should become redundant as we will be able to use webhooks
    for calendar events, instead of polling.
    """

    default_queue = JobQueue.MISCELLANEOUS
    bot_id: UUID
    bot_status: RecallAIBotStatusData

    async def perform(self):
        client = RecallAIClient()
        recall_ai_bot = await client.get_bot(str(self.bot_id))

        calendar_meetings = [cm for cm in recall_ai_bot.calendar_meetings]
        if not calendar_meetings:
            return

        for calendar_meeting in calendar_meetings:
            event = await client.get_calendar_event(
                user_id=calendar_meeting.calendar_user.external_id, event_id=calendar_meeting.id
            )
            async with transaction() as connection:
                user = await User.get_or_none(id=calendar_meeting.calendar_user.external_id, using_db=connection)
                if not user:
                    return

                recall_meeting: RecallAIMeeting | None = await RecallAIMeeting.get_or_none(
                    external_id=event.unique_event_id(user.organization_id), using_db=connection
                ).prefetch_related("meeting")
                if recall_meeting:
                    meeting = recall_meeting.meeting
                else:
                    meeting = await Meeting.create(
                        title=event.title,
                        scheduled_at=event.start_time,
                        ical_uid=event.ical_uid,
                        provider_meeting_id=event.provider_meeting_id,
                        creator_id=user.id,
                        organization_id=user.organization_id,
                        using_db=connection,
                    )
                    sub_status = (
                        self.bot_status.status.sub_code
                        if self.bot_status.status.sub_code is not None
                        else RecallAIBotStatusSubCodes.NONE
                    )
                    recall_meeting = await RecallAIMeeting.create(
                        meeting=meeting,
                        external_id=event.unique_event_id(user.organization_id),
                        provider_meeting_id=event.provider_meeting_id,
                        bot_id=str(self.bot_id),
                        bot_status=self.bot_status.status.code,
                        bot_sub_status=sub_status,
                        meeting_platform=event.meeting_platform,
                        will_record=event.will_record,
                        using_db=connection,
                    )

                if meeting.is_deleted:
                    await meeting.restore(using_db=connection)

                previous_meeting = await meeting.get_previous_meeting(using_db=connection)
                if previous_meeting and previous_meeting.collection_id:
                    meeting.collection_id = previous_meeting.collection_id

                users = (
                    await User.filter(
                        User.filters.by_any_email(event.attendee_and_organizer_emails)
                        & User.filters.by_organization(meeting.organization_id)
                    )
                    .prefetch_related("email_aliases")
                    .using_db(connection)
                )

                for attendee in event.attendees:
                    if attendee.declined_event or not attendee.email:
                        continue
                    meeting_attendee = await meeting.add_attendee(attendee.as_meeting_attendee(users))
                    if attendee.is_organizer:
                        meeting.organizer = meeting_attendee
                        meeting.ensure_internal_organizer_is_creator()

                recall_meeting.bot_id = str(self.bot_id)
                recall_meeting.bot_status = self.bot_status.status.code
                if self.bot_status.status.sub_code:
                    recall_meeting.bot_sub_status = self.bot_status.status.sub_code

                if meeting.is_unsaved:
                    await meeting.save(update_fields=meeting.changes.keys(), using_db=connection)
                    await enqueue_job(
                        ContentIndexingJob.from_model(user.organization_id, meeting), using_db=connection
                    )
                if recall_meeting.is_unsaved:
                    await recall_meeting.save(update_fields=recall_meeting.changes.keys(), using_db=connection)


class CreateUpcomingMeetingsJob(JobDefinition):
    default_queue = JobQueue.MISCELLANEOUS
    is_recurring = True
    retry_count = 0

    async def perform(self):
        calendar_users = await RecallAICalendarUser.all()
        connected_calendar_users = [calendar_user for calendar_user in calendar_users if calendar_user.is_connected]
        users = await User.filter(id__in=[calendar_user.user_id for calendar_user in connected_calendar_users])
        await bulk_enqueue_jobs([CreateUpcomingMeetingsForUserJob(user_id=user.id) for user in users])


class CreateUpcomingMeetingsForUserJob(JobDefinition):
    """
    This job is responsible for creating meeting records for upcoming calendar events.
    The state management for calendar events is entirely handled by Recall.AI - we will need to poll for updates to
    calendar events and update the meeting records accordingly, but we will not be responsible for creating or deleting
    calendar events.

    We poll because the v1 API in use does not support webhooks; the v2 API does and would eliminate polling.
    """

    default_queue = JobQueue.MISCELLANEOUS
    user_id: UUID

    async def perform(self):
        user = await User.get_or_none(id=self.user_id)
        if not user:
            return

        client = RecallAIClient()
        # list_calendar_events includes all upcoming calendar events for the next 30 days
        calendar_meetings = await client.list_calendar_events(user_id=self.user_id)

        if not calendar_meetings:
            # Still fall through to _handle_deleted_events so meetings removed from Recall get cleaned up
            logger.info(f"No upcoming calendar events found for user {user.id}")

        for event in calendar_meetings:
            if event.is_happening_now:
                continue

            await self._upsert_meeting_from_calendar_event(event, user)

        await self._handle_deleted_events(
            user, [event.unique_event_id(user.organization_id) for event in calendar_meetings]
        )

    async def _upsert_meeting_from_calendar_event(self, event: RecallAICalendarEvent, user: User):
        async with transaction() as connection:
            recall_meeting: RecallAIMeeting | None = await RecallAIMeeting.get_or_none(
                external_id=event.unique_event_id(user.organization_id), using_db=connection
            )

            if recall_meeting:
                async with allow_soft_deleted():
                    meeting = await Meeting.get_or_none(id=recall_meeting.meeting_id, using_db=connection)

                if not meeting:
                    logger.warning(f"Recall meeting {recall_meeting.id} does not exist")
                    return

                # Update the meeting with event details
                meeting.title = event.title
                meeting.scheduled_at = event.start_time
                meeting.scheduled_end_at = event.end_time
                meeting.ical_uid = event.ical_uid
                meeting.provider_meeting_id = event.provider_meeting_id
                meeting.conferencing_url = event.meeting_url
                # Calendar is the source of truth for upcoming meetings, restore deleted meetings that are still on the
                # user's calendar to prevent inconsistency in the application
                meeting.deleted_at = None

                # Update recall meeting with the latest bot status
                if recall_meeting.bot_status == RecallAIBotStatusCodes.NONE and event.bot_id:
                    recall_meeting.bot_status = RecallAIBotStatusCodes.SCHEDULED
                # Persist bot_id if it is set - calendar events are user-scoped but this
                # should be global state. When User B syncs, their event may have bot_id=None
                # even though User A already triggered recording for the same meeting.
                if event.bot_id:
                    recall_meeting.bot_id = str(event.bot_id)
                recall_meeting.meeting_platform = event.meeting_platform
                recall_meeting.provider_meeting_id = event.provider_meeting_id
                # Persist will_record status if it is true - calendar events are user-scoped but this
                # should be global state. will_record can only be set to False by explicitly updating
                # the calendar recording preference.
                recall_meeting.will_record = recall_meeting.will_record or event.will_record
                if recall_meeting.is_unsaved:
                    await recall_meeting.save(update_fields=recall_meeting.changes.keys(), using_db=connection)
            else:
                meeting = await self._create_meeting(event, user, using_db=connection)

            # Automatically organize recurring meetings into collections based on the previous meeting
            previous_meeting = await meeting.get_previous_meeting(using_db=connection)
            if previous_meeting and previous_meeting.collection_id:
                meeting.collection_id = previous_meeting.collection_id

            await self._refresh_meeting_attendees(meeting, event)

            if meeting.is_unsaved:
                await meeting.save(update_fields=meeting.changes.keys(), using_db=connection)

    async def _refresh_meeting_attendees(self, meeting: Meeting, event: RecallAICalendarEvent):
        # Always full-refresh attendees to ensure they are up-to-date
        meeting.attendees = []
        users = await User.filter(
            User.filters.by_any_email(event.attendee_and_organizer_emails)
            & User.filters.by_organization(meeting.organization_id)
        ).prefetch_related("email_aliases")

        for attendee in event.attendees:
            if not attendee.email:
                continue

            meeting_attendee = await meeting.add_attendee(attendee.as_meeting_attendee(users))
            if attendee.is_organizer and meeting.organizer != meeting_attendee:
                meeting.organizer = meeting_attendee
                meeting.ensure_internal_organizer_is_creator()

    async def _create_meeting(
        self, event: RecallAICalendarEvent, user: User, using_db: BaseDBAsyncClient | None = None
    ) -> Meeting:
        meeting = await Meeting.create(
            title=event.title,
            scheduled_at=event.start_time,
            scheduled_end_at=event.end_time,
            ical_uid=event.ical_uid,
            provider_meeting_id=event.provider_meeting_id,
            conferencing_url=event.meeting_url,
            creator_id=user.id,
            organization_id=user.organization_id,
            using_db=using_db,
        )
        await RecallAIMeeting.create(
            meeting_id=meeting.id,
            external_id=event.unique_event_id(user.organization_id),
            provider_meeting_id=event.provider_meeting_id,
            bot_id=str(event.bot_id) if event.bot_id else None,
            bot_status=RecallAIBotStatusCodes.SCHEDULED if event.bot_id else RecallAIBotStatusCodes.NONE,
            meeting_platform=event.meeting_platform,
            will_record=event.will_record,
            using_db=using_db,
        )

        await enqueue_job(ContentIndexingJob.from_model(user.organization_id, meeting))

        return meeting

    async def _handle_deleted_events(self, user: User, event_ids: list[str]):
        # Delete future meetings that are not included in recall calendar events
        # This is a little naive - if the creator declines the event but other attendees still meet, we might not
        # have a future record of the meeting.
        async with transaction() as connection:
            recall_meetings = await RecallAIMeeting.filter(external_id__in=event_ids)

            deleted_meetings = (
                await Meeting.by_organization_or_user(organization_id=user.organization_id, user_id=user.id)
                .filter(Meeting.filters.by_future() & Meeting.filters.by_not_started())
                .exclude(id__in=[rm.meeting_id for rm in recall_meetings])
                .filter(creator_id=user.id)
                .using_db(connection)
            )
            if not deleted_meetings:
                return

            logger.info(f"Deleting {len(deleted_meetings)} upcoming meetings for user {user.id}")

            jobs = []
            for meeting in deleted_meetings:
                await meeting.soft_delete(using_db=connection)
                jobs.append(ContentIndexingJob.from_model(user.organization_id, meeting))

            if jobs:
                await bulk_enqueue_jobs(jobs)


#
# Maintenance jobs
#
#


class RenameRecallBotJob(JobDefinition):
    default_queue = JobQueue.MAINTENANCE

    async def perform(self):
        calendar_users = await RecallAICalendarUser.all()

        for calendar_user in calendar_users:
            if not calendar_user.preference_name:
                continue

            recall_ai_client = RecallAIClient()
            await recall_ai_client.update_calendar_user_recording_preferences(
                user_id=calendar_user.user_id, recording_preference=calendar_user.preference_name
            )


class DeleteUserFromRecallJob(JobDefinition):
    default_queue = JobQueue.MAINTENANCE
    user_id: UUID

    async def perform(self):
        recall_ai_client = RecallAIClient()
        await recall_ai_client.delete_calendar_user(user_id=self.user_id)


class ReprocessLostMeetingsJob(JobDefinition):
    default_queue = JobQueue.MAINTENANCE
    scheduled_end_at_hours_ago: int = 1

    async def perform(self):
        # All meetings scheduled around now that are missing content
        meetings = await Meeting.filter(
            Q(scheduled_end_at__lte=datetime.now(UTC))
            & Q(scheduled_end_at__gt=datetime.now(UTC) - timedelta(hours=self.scheduled_end_at_hours_ago))
            & (Q(summary__isnull=True) | Q(transcript__isnull=True) | Q(recording_id__isnull=True))
            & Q(deleted_at__isnull=True)
        )

        meeting_ids = [meeting.id for meeting in meetings]

        recall_meetings = await RecallAIMeeting.filter(
            meeting_id__in=meeting_ids,
        ).prefetch_related("meeting")
        for recall_meeting in recall_meetings:
            client = RecallAIClient()
            if not recall_meeting.bot_id:
                continue
            bot = await client.get_bot(recall_meeting.bot_id)
            if not bot.status_changes:
                continue
            last_status = RecallAIBotStatusCodes(bot.status_changes[-1]["code"])
            if not last_status.is_completed:
                continue

            # If the bot is in any 'completed' state sync the transcript and recording
            transcript_job_definition = SyncTranscriptFromRecallAIJob(meeting_id=recall_meeting.meeting_id)
            recording_job_definition = SyncRecordingFromRecallAIJob(meeting_id=recall_meeting.meeting_id)
            callback_job_definition = MeetingProcessingCompleteCallbackJob(meeting_id=recall_meeting.meeting_id)
            job_group = await enqueue_job_group(
                [transcript_job_definition, recording_job_definition],
                callback=callback_job_definition,
            )
            transcript_job = job_group.jobs[0]
            recording_job = job_group.jobs[1]
            await MeetingJob.create(meeting=recall_meeting.meeting, job=transcript_job)
            await MeetingJob.create(meeting=recall_meeting.meeting, job=recording_job)


class CleanupOrphanedRecallBotJob(JobDefinition):
    default_queue = JobQueue.MAINTENANCE
    is_recurring = True
    retry_count = 0
    page_number: int = 1

    async def perform(self):
        client = RecallAIClient()

        # Get a list of bots scheduled in the future, one page is 100 bots.
        # Exclude bots managed by the calendar integration - these may not have a
        # RecallAIMeeting.bot_id yet due to timing between Recall scheduling the bot
        # and our calendar sync polling.
        today = date.today()
        yesterday = today - timedelta(days=1)
        response: dict = await client.list_bots(join_at_after=yesterday, page=self.page_number)
        bot_ids = [bot["id"] for bot in response.get("results", []) if not bot.get("calendar_meetings")]
        next_page_url = response.get("next", "")
        next_page = None

        # Extract next page number from URL if it exists
        if next_page_url:
            parsed = urlparse(next_page_url)
            next_page = parse_qs(parsed.query).get("page", [None])[0]

        # Find all recall meetings with these bot IDs
        found_bot_ids = await RecallAIMeeting.filter(bot_id__in=bot_ids).values_list("bot_id", flat=True)

        # Identify orphaned bots (bots without a corresponding meeting)
        orphaned_bots = set(bot_ids) - set(found_bot_ids)

        if orphaned_bots:
            logger.warning(f"Found {len(orphaned_bots)} orphaned Recall.AI bots to delete")

        # Delete orphaned bots
        for bot_id in orphaned_bots:
            try:
                await client.delete_bot(bot_id)
                logger.info(f"Deleted orphaned Recall.AI bot {bot_id}")
            except httpx.HTTPStatusError as e:
                if e.response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED:
                    logger.info(f"Skipping bot {bot_id}: already joined call, cannot delete")
                else:
                    raise

        if next_page:
            # Calculate delay seconds based on the number of orphaned bots deleted, to avoid rate limiting
            # If no orphaned bots were found, delay 1 second.
            # If orphaned bots were found, delay 2 seconds per bot up to 60 seconds.
            delay_seconds = min(1 + len(orphaned_bots) * 2, 60)
            await enqueue_job(
                CleanupOrphanedRecallBotJob(
                    page_number=int(next_page), perform_at=datetime.now(UTC) + timedelta(seconds=delay_seconds)
                )
            )


class RefreshAllRecallCalendarUsersJob(JobDefinition):
    default_queue = JobQueue.MAINTENANCE
    is_recurring = True
    retry_count = 0

    async def perform(self):
        client = RecallAIClient()
        calendar_users = await RecallAICalendarUser.all().prefetch_related("user")
        for calendar_user in calendar_users:
            if not calendar_user.is_connected:
                continue
            # Refresh the calendar meetings for this user - this will reschedule any bots as necessary
            try:
                await client.refresh_calendar_meetings(calendar_user.user_id)
            except httpx.HTTPStatusError as e:
                if e.response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT:
                    logger.warning(f"Calendar disconnected for user {calendar_user.user_id}, syncing state")
                    await client.get_calendar_user(calendar_user.user_id)
                    continue
                raise

        # Wait a few seconds to allow Recall to process the refresh requests
        await asyncio.sleep(5)

        # Force upsert to re-run, so we get the refreshed bot IDs
        users = [calendar_user.user for calendar_user in calendar_users]
        await bulk_enqueue_jobs([CreateUpcomingMeetingsForUserJob(user_id=calendar_user.user_id) for user in users])
