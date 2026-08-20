import json

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from svix.webhooks import Webhook, WebhookVerificationError

from app.jobs.meetings import MeetingProcessingCompleteCallbackJob
from app.models.accounts import User
from app.models.workspaces.meetings import MeetingJob
from app.routers.dependencies import Helpers, get_current_user, get_helpers
from config import logger, settings
from infra.jobs import enqueue_job, enqueue_job_group
from infra.messaging import Topic
from integrations.recall_ai.client import RecallAIClient
from integrations.recall_ai.jobs import (
    CreateMeetingFromBotIDJob,
    CreateUpcomingMeetingsForUserJob,
    SyncRecordingFromRecallAIJob,
    SyncTranscriptFromRecallAIJob,
)
from integrations.recall_ai.models import (
    RecallAIBotStatusCodes,
    RecallAIBotStatusPayload,
    RecallAICalendarPreferences,
    RecallAIMeeting,
)
from integrations.recall_ai.presenters import RecallAIBotStatusPresenter

#
# Dependencies
#
#


async def validate_recall_webhook(request: Request):
    """
    Validate the Recall.AI webhook signature.
    https://docs.svix.com/receiving/verifying-payloads/how
    """
    if not settings.recall_ai_webhook_signing_secret.get_secret_value():
        return True
    secret = settings.recall_ai_webhook_signing_secret.get_secret_value()
    headers = dict(request.headers)
    payload = await request.body()

    try:
        wh = Webhook(secret)
        wh.verify(payload, headers)
    except WebhookVerificationError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid signature")


router = APIRouter(tags=["skip_onboarding"])

#
# Webhook Routes
#
#


@router.post("/integrations/recall_ai/webhooks")
async def recall_ai_webhook(payload: RecallAIBotStatusPayload, valid_request: bool = Depends(validate_recall_webhook)):
    """
    This endpoint is used by Recall.AI webhooks to notify us of bot status changes.
    """
    recall_meetings = (
        await RecallAIMeeting.filter(bot_id=payload.data.bot_id, meeting__deleted_at__isnull=True)
        .prefetch_related("meeting")
        .order_by("-meeting__created_at")
        .all()
    )

    if len(recall_meetings) == 0:
        logger.info(f"Received bot status bot_id {payload.data.bot_id} no meeting exists for this bot")
        if payload.data.status.code == RecallAIBotStatusCodes.IN_CALL_NOT_RECORDING:
            # This should not happen, but we don't want to miss syncing completed meetings
            # TODO: Check the logs to see if this is happening - ideally we can remove this.
            logger.warning(f"Bot status is completed but no meeting exists for bot_id {payload.data.bot_id}")
            await enqueue_job(CreateMeetingFromBotIDJob(bot_id=payload.data.bot_id, bot_status=payload.data))
        return {"status": "ok"}

    for recall_meeting in recall_meetings:
        # If the meeting is not in a valid state, skip it. Happens when bot status events happen in quick succession
        if not recall_meeting.meeting_id:
            logger.exception(f"Meeting ID not found for RecallAIMeeting: {recall_meeting.id}")
            continue

        # Update the meeting with the bot status
        recall_meeting.bot_status = payload.data.status.code
        if payload.data.status.sub_code:
            recall_meeting.bot_sub_status = payload.data.status.sub_code
        await recall_meeting.save(update_fields=["bot_status", "bot_sub_status"])

        bot_status_presenter = await RecallAIBotStatusPresenter.create(recall_meeting)
        if bot_status_presenter.is_failed:
            recall_meeting.meeting.did_recording_fail = True
            await recall_meeting.meeting.save(update_fields=["did_recording_fail"])

        await Topic("meeting_bot", meeting_id=recall_meeting.meeting_id).broadcast()

        if payload.data.status.code.is_completed:
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

    # We always return a 200 to Recall.AI to acknowledge the webhook
    return {"status": "ok"}


#
# Calendar Auth redirect routes
#
#


@router.get("/integrations/google_calendar/auth")
async def integrations_recall_ai_google_calendar_auth(
    request: Request,
    current_user: User = Depends(get_current_user),
    helpers: Helpers = Depends(get_helpers),
):
    timeout = httpx.Timeout(5.0, read=30.0, write=30.0, connect=60.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        # Redirect the request to recall.ai to register the user's calendar with Recall.AI
        # https://docs.recall.ai/docs/calendar-v1-google-calendar#going-to-production-getting-approval
        # Note: We cannot get the auth_token because that would result in an invalid code when it's passed to Recall.AI
        recall_url = "https://us-east-1.recall.ai/api/v1/calendar/google_oauth_callback/"
        recall_url += "?" + str(request.query_params)
        logger.info(f"Redirecting to Recall.AI for calendar auth: {recall_url}")
        recall_response = await client.get(recall_url)
        if recall_response.status_code >= status.HTTP_400_BAD_REQUEST:
            logger.error(f"Error with Recall.AI auth: {recall_response.text}")
            # Expecting a 302 redirect from Recall.AI but any sub 400 status code is okay
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=recall_response.text or "Error with Recall.AI auth",
            )
        logger.info(f"Recall.AI auth response: {recall_response.text}")

    recall_ai_client = RecallAIClient()
    # Update the user with the calendar user
    await recall_ai_client.get_calendar_user(user_id=current_user.id)

    state = request.query_params.get("state", "{}")
    state_obj: dict = json.loads(state)
    recall_calendar_preference = RecallAICalendarPreferences(
        state_obj.get("recall_calendar_preference", RecallAICalendarPreferences.NONE)
    )

    await recall_ai_client.update_calendar_user_recording_preferences(
        user_id=current_user.id, recording_preference=recall_calendar_preference
    )

    await enqueue_job(CreateUpcomingMeetingsForUserJob(user_id=current_user.id))

    next_url = state_obj.get("success_url", helpers.url_for("meetings_index"))
    return await helpers.redirect_back_or(to=next_url)


@router.get("/integrations/microsoft_calendar/auth")
async def integrations_recall_ai_microsoft_calendar_auth(
    request: Request,
    current_user: User = Depends(get_current_user),
    helpers: Helpers = Depends(get_helpers),
):
    timeout = httpx.Timeout(5.0, read=30.0, write=30.0, connect=60.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        # Redirect the request to recall.ai to register the user's calendar with Recall.AI
        # https://docs.recall.ai/docs/calendar-v1-microsoft-outlook
        recall_url = "https://us-east-1.recall.ai/api/v1/calendar/ms_oauth_callback/"
        recall_url += "?" + str(request.query_params)
        logger.info(f"Redirecting to Recall.AI for Microsoft calendar auth: {recall_url}")
        recall_response = await client.get(recall_url)
        if recall_response.status_code >= status.HTTP_400_BAD_REQUEST:
            logger.error(f"Error with Recall.AI Microsoft auth: {recall_response.text}")
            # Expecting a 302 redirect from Recall.AI but any sub 400 status code is okay
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=recall_response.text or "Error with Recall.AI Microsoft auth",
            )
        logger.info(f"Recall.AI Microsoft auth response: {recall_response.text}")

    recall_ai_client = RecallAIClient()
    # Update the user with the calendar user
    await recall_ai_client.get_calendar_user(user_id=current_user.id)

    state = request.query_params.get("state", "{}")
    state_obj: dict = json.loads(state)
    recall_calendar_preference = RecallAICalendarPreferences(
        state_obj.get("recall_calendar_preference", RecallAICalendarPreferences.NONE)
    )

    await recall_ai_client.update_calendar_user_recording_preferences(
        user_id=current_user.id, recording_preference=recall_calendar_preference
    )

    await enqueue_job(CreateUpcomingMeetingsForUserJob(user_id=current_user.id))

    next_url = state_obj.get("success_url", helpers.url_for("meetings_index"))
    return await helpers.redirect_back_or(to=next_url)
