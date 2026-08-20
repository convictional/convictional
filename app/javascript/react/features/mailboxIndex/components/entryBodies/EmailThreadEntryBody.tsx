import { useMemo } from "react"

import { MailboxStateBadge } from "~/react/composites/MailboxStateBadge"
import { markdownToPreviewNodes } from "~/react/composites/markdown/toPreviewNodes"
import { UserDateTime } from "~/react/composites/UserDateTime"
import type { MailboxEntry } from "~/react/features/mailboxIndex/types"
import { useCurrentUser } from "~/react/shared/hooks/useCurrentUser"
import { Avatar } from "~/react/ui/Avatar"
import { formatScheduledFor, formatSnoozedUntil } from "~/react/ui/DateTime"
import { Tooltip } from "~/react/ui/Tooltip"

import { describeEmailActivity } from "./emailActivityPreview"

interface EmailThreadEntryBodyProps {
  entry: MailboxEntry
}

export function EmailThreadEntryBody({ entry }: EmailThreadEntryBodyProps) {
  const { user } = useCurrentUser()
  const detail = entry.email
  const isUnread = entry.is_unread
  const preview = useMemo(
    () =>
      detail?.last_comment
        ? markdownToPreviewNodes(detail.last_comment, {
            mentionClassName: isUnread ? "text-info-content" : "text-base-700",
          })
        : null,
    [detail?.last_comment, isUnread]
  )
  if (!detail) return null

  // Activity (a collaborator add / assignment / decision newer than the last message and comment)
  // is a client-phrased line; message and comment keep their existing rendering. Draft
  // schedule/unschedule returns null here so the row keeps the draft's snippet, not a "scheduled" line.
  const activity =
    detail.preview_kind === "activity"
      ? describeEmailActivity(detail.event_action, detail.event_details, {
          actorName: detail.event_actor?.display_name,
          actorId: detail.event_actor?.id,
          currentUserId: user?.id,
        })
      : null

  return (
    <>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1 min-w-0">
          <p className={`text-sm truncate ${isUnread ? "font-semibold text-base-700" : "text-base-600"}`}>
            {detail.sender_display}
          </p>
          <span className="text-xs bg-base-50 border border-base-300 rounded-sm px-1 text-base-700">
            {detail.message_count}
          </span>
          {detail.attachment_count > 0 && (
            <span className="bg-base-50 border border-base-300 rounded-sm px-1 text-base-700 inline-flex items-center gap-1">
              <span className="material-symbols-outlined text-sm -my-1">attachment</span>
              <span className="text-xs">{detail.attachment_count}</span>
            </span>
          )}
        </div>
        <UserDateTime
          datetime={entry.last_activity_at}
          format="relative"
          className={`text-xs whitespace-nowrap ${isUnread ? "text-base-600" : "text-base-600/70"}`}
        />
      </div>
      <div className="text-sm/6 flex items-center overflow-hidden min-w-0">
        {entry.is_snoozed && (
          <Tooltip content={formatSnoozedUntil(entry.snoozed_until, user?.time_zone ?? null)}>
            <span className="material-symbols-outlined text-sm text-warning-content mr-1 p-1">snooze</span>
          </Tooltip>
        )}
        {/* UI-only launch gate: scheduled drafts are marked for superusers until release. */}
        {user?.is_superuser && detail.scheduled_for && (
          <Tooltip content={formatScheduledFor(detail.scheduled_for, user?.time_zone ?? null)}>
            <span className="material-symbols-outlined text-sm text-warning-content mr-1 p-1">schedule_send</span>
          </Tooltip>
        )}
        {entry.is_assigned_to_me ? (
          <MailboxStateBadge variant="assigned" className="mr-1" />
        ) : entry.is_shared ? (
          <MailboxStateBadge variant="shared" className="mr-1" />
        ) : null}
        <span className={`pr-2 flex-shrink-0 ${isUnread ? "font-medium text-base-700" : "text-base-600/70"}`}>
          {entry.title || "No subject"}
        </span>
        <div className="w-1 h-1 rounded-full bg-base-500 aspect-square" />
        {detail.preview_kind === "comment" && detail.last_comment ? (
          <div
            className={`text-base-600 ml-2 grid grid-cols-[auto_1fr] items-center gap-1 ${
              isUnread ? "" : "text-base-600/70"
            }`}
          >
            {detail.last_comment_author && (
              <Avatar
                displayName={detail.last_comment_author.display_name}
                picture={detail.last_comment_author.picture}
                size="small"
              />
            )}
            <span className="text-base-700 truncate py-0.5 px-2 bg-base-50 rounded-full text-xs border border-neutral">
              {preview}
            </span>
          </div>
        ) : (
          <span className={`text-base-600/70 ml-2 truncate min-w-0 gap-2 ${isUnread ? "" : "text-base-600/50"}`}>
            {activity ?? entry.preview}
          </span>
        )}
      </div>
    </>
  )
}
