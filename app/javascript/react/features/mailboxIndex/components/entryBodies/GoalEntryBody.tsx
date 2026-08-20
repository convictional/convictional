import { useMemo } from "react"

import { describeGoalActivity } from "~/react/composites/goals/goalActivityPreview"
import { StatusPie } from "~/react/composites/goals/StatusPie"
import { markdownToPreviewNodes } from "~/react/composites/markdown/toPreviewNodes"
import { UserDateTime } from "~/react/composites/UserDateTime"
import type { MailboxEntry } from "~/react/features/mailboxIndex/types"
import { useCurrentUser } from "~/react/shared/hooks/useCurrentUser"
import { useOrganizationMembers } from "~/react/shared/hooks/useOrganizationMembers"
import { STATUS_CONFIG } from "~/react/shared/statusConfig"
import { Avatar } from "~/react/ui/Avatar"
import { Tooltip } from "~/react/ui/Tooltip"

interface GoalEntryBodyProps {
  entry: MailboxEntry
}

export function GoalEntryBody({ entry }: GoalEntryBodyProps) {
  const detail = entry.goal
  const isUnread = entry.is_unread
  const { user } = useCurrentUser()
  const { users, groups } = useOrganizationMembers()
  const userNames = useMemo(() => new Map(users.map(u => [u.id, u.display_name])), [users])
  const groupNames = useMemo(() => new Map(groups.map(g => [g.id, g.name])), [groups])
  const previewNodes = useMemo(
    () =>
      detail?.last_comment
        ? markdownToPreviewNodes(detail.last_comment, {
            mentionClassName: isUnread ? "text-info-content" : "text-base-700",
          })
        : null,
    [detail?.last_comment, isUnread]
  )
  if (!detail) return null

  const status = STATUS_CONFIG[detail.status]
  const author = detail.last_comment_author
  const titleClasses = `text-sm truncate min-w-0 ${isUnread ? "font-semibold text-base-700" : "text-base-600"}`
  const activity =
    detail.preview_kind === "activity"
      ? describeGoalActivity(detail.event_action, detail.event_details, {
          actorName: detail.event_actor?.display_name,
          actorId: detail.event_actor?.id,
          currentUserId: user?.id,
          resolveUserName: id => userNames.get(id),
          resolveGroupName: id => groupNames.get(id),
        })
      : null

  return (
    <>
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          {/* The description lives in a tooltip revealed on title hover, keeping the row to two
              lines. Tooltip renders its trigger unwrapped when content is empty. */}
          {entry.preview ? (
            <Tooltip content={entry.preview} className={titleClasses}>
              {entry.title || "Goal"}
            </Tooltip>
          ) : (
            <span className={titleClasses}>{entry.title || "Goal"}</span>
          )}
          {detail.is_completed ? (
            <span className="inline-flex items-center gap-0.5 text-xs text-success-content shrink-0">
              <span className="material-symbols-outlined text-sm leading-none">check</span>
              Complete
            </span>
          ) : (
            status && (
              <span className={`shrink-0 text-xs rounded-full px-2 py-0.5 border ${status.classes}`}>
                {status.text}
              </span>
            )
          )}
          {detail.progress != null && (
            <StatusPie
              progress={detail.progress}
              size={16}
              tooltipContent={`${Math.round(detail.progress * 100)}% complete`}
            />
          )}
        </div>
        <UserDateTime datetime={entry.last_activity_at} format="relative" className="text-xs text-base-500 shrink-0" />
      </div>
      {/* The second line summarizes the latest event, rendered three ways: a comment gets the
          author's avatar and a chip bubble; a posted update gets the avatar but plain text (no
          chip); everything else (state changes, update requests) is a plain muted line the client
          phrases from the event itself. */}
      {activity ? (
        <div className="text-sm/6 truncate min-w-0">
          <span className={`text-xs ${isUnread ? "text-base-700" : "text-base-500"}`}>
            {activity.text}
            {activity.date && <UserDateTime datetime={activity.date} format="date_medium" className="ml-1" />}
          </span>
        </div>
      ) : (
        detail.last_comment && (
          <div className="text-sm/6 flex items-center overflow-hidden min-w-0">
            {author && <Avatar displayName={author.display_name} picture={author.picture} size="small" />}
            <span
              className={
                detail.preview_kind === "comment"
                  ? `ml-1 truncate py-0.5 px-2 bg-base-50 rounded-full text-xs border border-neutral ${
                      isUnread ? "text-base-700" : "text-base-600/70"
                    }`
                  : `ml-1 truncate text-xs ${isUnread ? "text-base-700" : "text-base-600/70"}`
              }
            >
              {previewNodes}
            </span>
          </div>
        )
      )}
    </>
  )
}
