def recall_substatus_description(bot_sub_status) -> str | None:
    # From https://docs.recall.ai/docs/sub-codes
    status_descriptions: dict[str, str] = {
        "zoom_local_recording_disabled": (
            "The meeting host has their global user-level local recording setting disabled. "
            "The host was not presented with the recording consent popup."
        ),
        "zoom_local_recording_request_disabled": (
            "The meeting host has their user-level local recording setting enabled, but has disabled the advanced "
            "recording option labelled 'Hosts can give meeting participants permission to record locally'. "
            "The host was not presented with the recording consent popup."
        ),
        "zoom_local_recording_request_disabled_by_host": (
            "The meeting host has disabled participants from requesting local recording permission or has denied "
            "all future requests. The host was not presented with the recording consent popup."
        ),
        "zoom_bot_in_waiting_room": (
            "The bot is in the waiting room due to which local recording cannot be requested. "
            "The host was not presented with the recording consent popup."
        ),
        "zoom_host_not_present": (
            "The host was not present in the meeting when the bot requested local recording permission. "
            "This only occurs in very rare cases where the bot does request permission when the host isn't "
            "present. One example is when a host leaves/disconnects right as the bot requests permissions."
        ),
        "zoom_local_recording_request_denied_by_host": (
            "The host denied the bot's local recording request. "
            "The host was presented with the recording consent popup."
        ),
        "zoom_local_recording_denied": (
            "The request to record was denied by the user. "
            "This indicates that the user has local recording disabled in their global user settings, the "
            "recording request popup was presented and denied, or that the popup was presented but the request "
            "timed out."
        ),
        "zoom_local_recording_grant_not_supported": (
            "The meeting host is using Zoom Room or other Zoom client that does not support local recording "
            "permission."
        ),
        "zoom_sdk_key_blocked_by_host_admin": (
            "The Zoom SDK key used by the bot is blocked by the Zoom user's workspace admin."
        ),
        "call_ended_by_host": "The call has been ended by the meeting host.",
        "call_ended_by_platform_idle": "The call has been ended by the meeting platform, because it was idle.",
        "call_ended_by_platform_max_length": (
            "The call has been ended by the meeting platform because it reached the maximum meeting length."
        ),
        "call_ended_by_platform_waiting_room_timeout": (
            "The bot could not join the call because meeting platform's maximum waiting room time exceeded. "
            "For Google Meet, this is 10 minutes. Zoom and Teams don't have a timeout."
        ),
        "timeout_exceeded_waiting_room": "The bot left the call because it was in the waiting room for too long.",
        "timeout_exceeded_noone_joined": "The bot left the call because nobody joined the call for too long.",
        "timeout_exceeded_everyone_left": "The bot left the call because everyone else left.",
        "timeout_exceeded_silence_detected": (
            "The bot left the call because all other participants were likely bots based off continuous silence "
            "detection heuristic."
        ),
        "timeout_exceeded_only_bots_detected_using_participant_names": (
            "The bot left the call because all other participants were likely bots based off participant names "
            "heuristic."
        ),
        "timeout_exceeded_only_bots_detected_using_participant_events": (
            "The bot left the call because all other participants were likely bots based off participant events "
            "heuristic."
        ),
        "timeout_exceeded_only_bots_in_call": (
            "The bot left the call because all other participants were likely bots."
        ),
        "timeout_exceeded_in_call_not_recording": (
            "The bot left the call because it never started recording e.g. remained in the in_call_not_recording"
        ),
        "timeout_exceeded_in_call_recording": ("The bot left the call because it exceeded the timeout"),
        "timeout_exceeded_max_duration": "The bot exceeded its maximum duration.",
        "bot_kicked_from_call": "The bot was removed from the call by the host.",
        "bot_kicked_from_waiting_room": "The bot was removed from the waiting room by the host.",
        "bot_received_leave_call": "The bot received leave call request.",
        "bot_errored": "The bot ran into an unexpected error.",
        "meeting_not_found": "No meeting was found at the given link.",
        "meeting_not_started": "The meeting has not started yet.",
        "meeting_requires_registration": "The meeting requires registration.",
        "meeting_requires_sign_in": "The meeting can only be joined by signed in users.",
        "meeting_link_expired": "The meeting link has expired.",
        "meeting_link_invalid": "The meeting does not exist or the link is invalid.",
        "meeting_password_incorrect": "The meeting password is incorrect.",
        "meeting_locked": "The meeting is locked.",
        "meeting_full": "The meeting is full.",
        "meeting_ended": "The bot attempted to join a meeting that has already ended and can no longer be joined.",
        "google_meet_internal_error": "The bot was unable to join the call due to a Google Meet internal error.",
        "google_meet_sign_in_failed": "The bot was not able to sign in to google.",
        "google_meet_sign_in_captcha_failed": "The bot was not able to sign in to google because of captcha.",
        "google_meet_bot_blocked": "The bot was disallowed from joining the meeting.",
        "google_meet_sso_sign_in_failed": "The bot was not able to sign in to google with SSO.",
        "google_meet_sign_in_missing_login_credentials": (
            "The bot was not able to sign in to google because login credentials were not configured."
        ),
        "google_meet_sign_in_missing_recovery_credentials": (
            "The bot was not able to sign in to google because recovery credentials were not configured."
        ),
        "google_meet_sso_sign_in_missing_login_credentials": (
            "The bot was not able to sign in to google with SSO because login credentials were not configured."
        ),
        "google_meet_sso_sign_in_missing_totp_secret": (
            "The bot was not able to sign in in to google with SSO because TOTP secret was missing from password."
        ),
        "google_meet_video_error": "The bot was not able to join the call due to Google Meet video error.",
        "google_meet_meeting_room_not_ready": (
            "The bot was not able to join the call as the meeting room was not ready."
        ),
        "google_meet_login_not_available": (
            "There were not enough available logins (Google accounts) in the supplied google_login_group_id for "
            "the bot to use."
        ),
        "zoom_sdk_credentials_missing": (
            "The bot was not able to join because Zoom SDK credentials were not configured."
        ),
        "zoom_sdk_update_required": "A newer version of the Zoom SDK is required to join this meeting.",
        "zoom_sdk_app_not_published": "The SDK credentials configured in have not been approved by Zoom.",
        "zoom_email_blocked_by_admin": (
            "The Zoom account this bot is joining from has been disallowed to join this meeting by the Zoom "
            "workspace administrator."
        ),
        "zoom_registration_required": (
            "The bot failed to join because registration is required for this Zoom meeting."
        ),
        "zoom_captcha_required": "The bot failed to join because captcha is required for this Zoom meeting.",
        "zoom_account_blocked": "The account this bot is joining from has been blocked by Zoom.",
        "zoom_invalid_signature": "The Zoom SDK was not able to generate a valid meeting-join signature.",
        "zoom_internal_error": "The bot failed to join due to an internal Zoom error.",
        "zoom_join_timeout": "The request to join the Zoom meeting timed out.",
        "zoom_email_required": (
            "The bot failed to join because providing an email is required to join this Zoom meeting. "
            "Provide a zoom.user_email when creating the bot as outlined in Email Required Meetings."
        ),
        "zoom_web_disallowed": (
            "The Zoom meeting host has disallowed joining from the web which prevents the bot from joining the "
            "meeting. Have the host disable E2E encryption for the meeting."
        ),
        "zoom_connection_failed": "The bot failed to join the meeting due to a Zoom server error.",
        "zoom_error_multiple_device_join": (
            "The bot failed to join the meeting due to another participant with the same credentials having "
            "joined the meeting."
        ),
        "zoom_meeting_not_accessible": "The Zoom meeting was not accessible for the bot.",
        "zoom_meeting_host_inactive": (
            "The request to join the Zoom meeting failed, as the meeting host has been disabled or restricted. "
            "You will not be able to join this meeting."
        ),
        "microsoft_teams_call_dropped": (
            "The bot got call dropped error from MS Teams and was unable to re-join the call."
        ),
        "microsoft_teams_sign_in_credentials_missing": (
            "The bot failed to join a Microsoft Teams meeting requiring all participants to be signed-in. "
            "The bot was not signed in and thus was not able to join the call."
        ),
        "microsoft_teams_sign_in_failed": (
            "The bot failed to join a Microsoft Teams meeting requiring all participants to be signed-in. "
            "The bot was not signed in or failed to sign in to its configured Microsoft account."
        ),
        "microsoft_teams_internal_error": "The bot failed to join the call due to a Microsoft Teams server error.",
        "microsoft_teams_captcha_detected": (
            "The bot failed to join due to captcha being enabled for anonymous participants."
        ),
        "microsoft_teams_bot_not_invited": (
            "The bot failed to join a Microsoft Teams meeting as it was not the account that was invited. "
        ),
        "webex_join_meeting_error": ("The bot failed to join a Webex meeting because the meeting was invalid"),
        "timeout_exceeded_recording_permission_denied": (
            "The bot left the call because it was not granted recording permission."
        ),
    }
    return status_descriptions.get(bot_sub_status, None)
