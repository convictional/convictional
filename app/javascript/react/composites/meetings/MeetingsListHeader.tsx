import type { MeetingResponse } from "~/react/shared/types"
import { StickyHeader } from "~/react/ui/StickyHeader"
import { MeetingsViewSwitcher } from "./MeetingsViewSwitcher"
import { StartRecordingForm } from "./StartRecordingForm"
import { UploadTranscriptForm } from "./UploadTranscriptForm"

interface MeetingsListHeaderProps {
  current: "collections" | "upcoming"
  onMeetingCreated: (meeting: MeetingResponse) => void
}

// Sticky toolbar shared by the meetings list pages (/meetings,
// /meetings/upcoming, /meetings_collections): a Collections/Upcoming view
// switcher on the left, the "Start recording from link" and "Upload
// transcript" entry actions on the right.
export function MeetingsListHeader({ current, onMeetingCreated }: MeetingsListHeaderProps) {
  return (
    <StickyHeader>
      <div className="flex items-center justify-between gap-2 p-2">
        <MeetingsViewSwitcher current={current} />
        <div className="flex items-center gap-2">
          <StartRecordingForm onCreated={onMeetingCreated} />
          <div className="hidden md:block">
            <UploadTranscriptForm onCreated={onMeetingCreated} />
          </div>
        </div>
      </div>
    </StickyHeader>
  )
}
