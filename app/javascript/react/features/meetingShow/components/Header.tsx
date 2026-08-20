import { BackButton } from "~/react/composites/BackButton"
import { CollectionPicker } from "~/react/composites/meetings/CollectionPicker"
import { SharingDropdown, type SharingOption } from "~/react/composites/SharingDropdown"
import { WorkspaceCollaborators } from "~/react/composites/workspaceCollaborators/WorkspaceCollaborators"
import type { BackNavigation } from "~/react/shared/types"

import type { MeetingDetail } from "../types"

import { DeleteButton } from "./DeleteButton"

const MEETING_SHARING_OPTIONS: SharingOption[] = [
  { value: "private", label: "Private", description: "Only visible to collaborators", icon: "visibility_off" },
  {
    value: "organization",
    label: "Organization",
    description: "Visible to anyone in the organization",
    icon: "visibility",
  },
]

interface HeaderProps {
  meeting: MeetingDetail
  back: BackNavigation
  onServerUpdate: (meeting: MeetingDetail) => void
}

// The sticky-header actions row. The meeting title, schedule, and recurring nav
// live in MeetingTitle, rendered in the content area below the header.
export function Header({ meeting, back, onServerUpdate }: HeaderProps) {
  return (
    <div className="flex items-center justify-between gap-2 p-2">
      <ul className="flex items-center gap-1">
        <li>
          <BackButton back={back} />
        </li>
        {meeting.is_recurring && meeting.previous_meeting_id && (
          <li>
            <a href={`/meetings/${meeting.previous_meeting_id}`} className="btn">
              <span className="material-symbols-outlined text-lg transition -ml-1">arrow_back</span>
              Previous meeting
            </a>
          </li>
        )}
        <li>
          <CollectionPicker<MeetingDetail>
            meetingId={meeting.id}
            collection={meeting.collection}
            onMeetingUpdated={onServerUpdate}
          />
        </li>
      </ul>
      <div className="flex items-center gap-3 md:gap-2">
        <SharingDropdown<MeetingDetail>
          patchUrl={`/api/meetings/${meeting.id}`}
          sharing={meeting.sharing}
          options={MEETING_SHARING_OPTIONS}
          triggerIcon={s => (s === "organization" ? "visibility" : "visibility_off")}
          errorMessage="Could not update sharing. Please try again."
          onUpdated={onServerUpdate}
          // Confirm in both directions before flipping visibility.
          confirmChange={next =>
            next.value === "private"
              ? {
                  title: "Make this meeting private?",
                  message: "Only collaborators will be able to view it.",
                  confirmLabel: "Make private",
                }
              : {
                  title: "Make this meeting public?",
                  message: "Anyone in the organization will be able to view it.",
                  confirmLabel: "Make public",
                }
          }
        />
        <WorkspaceCollaborators workspaceId={meeting.workspace_id} />
        {/* Upcoming meetings can't be deleted in Convictional (manage them in
            the calendar) — the API 409s — so the control only shows once a
            meeting is past. Sits last so delete is the furthest-right action. */}
        {!meeting.is_upcoming && <DeleteButton meetingId={meeting.id} />}
      </div>
    </div>
  )
}
