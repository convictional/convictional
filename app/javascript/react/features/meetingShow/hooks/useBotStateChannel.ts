import { useChannel } from "~/react/shared/hooks/useChannel"
import { ChannelEventAction, ChannelEventResource, ChannelStream } from "~/types/channels"

import type { MeetingBotState } from "../types"

// Subscribes to the meeting_bot channel for live bot state updates from
// Recall.ai webhooks. The server publishes the full MeetingBotState as
// `data.state` on UPDATED events (see integrations/recall_ai/api.py:
// handle_meeting_bot_json_events) — the client just hands it to onUpdate.
//
// Channel pushes win unconditionally ("last write wins"). The will_record
// toggle (RecordingControls) mutates bot state without an optimistic-merge
// guard; a botMutatedAt ref would be needed to make those edits survive races.
export function useBotStateChannel(meetingId: string | null, onUpdate: (state: MeetingBotState) => void) {
  useChannel(
    meetingId ? { stream: ChannelStream.MEETING_BOT, params: { meeting_id: meetingId } } : null,
    ChannelEventResource.MEETING_BOT,
    (action, data) => {
      if (action !== ChannelEventAction.UPDATED) return
      const state = data.state as MeetingBotState | undefined
      if (!state) return
      onUpdate(state)
    }
  )
}
