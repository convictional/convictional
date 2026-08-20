import { useMemo } from "react"

import { markdownToPreviewNodes } from "~/react/composites/markdown/toPreviewNodes"
import { UserDateTime } from "~/react/composites/UserDateTime"
import type { MailboxEntry } from "~/react/features/mailboxIndex/types"
import { useCurrentUser } from "~/react/shared/hooks/useCurrentUser"
import { useIsMobile } from "~/react/shared/hooks/useIsMobile"
import { Avatar } from "~/react/ui/Avatar"

import { describePostActivity } from "./postActivityPreview"

interface PostEntryBodyProps {
  entry: MailboxEntry
}

export function PostEntryBody({ entry }: PostEntryBodyProps) {
  const { user } = useCurrentUser()
  const isMobile = useIsMobile()
  const detail = entry.post
  const isUnread = entry.is_unread
  const mentionClassName = isUnread ? "text-info-content" : "text-base-700"
  const previewNodes = useMemo(
    () => (detail?.last_comment ? markdownToPreviewNodes(detail.last_comment, { mentionClassName }) : null),
    [detail?.last_comment, mentionClassName]
  )
  if (!detail) return null

  const author = detail.last_comment_author
  const titleClasses = `font-accent text-base truncate min-w-0 ${isUnread ? "text-base-700" : "text-base-600"}`
  const previewTextClasses = `truncate text-xs ${isUnread ? "text-base-700" : "text-base-500"}`
  const activity =
    detail.preview_kind === "activity"
      ? describePostActivity(detail.event_action, detail.event_details, {
          actorName: detail.event_actor?.display_name,
          actorId: detail.event_actor?.id,
          currentUserId: user?.id,
        })
      : null

  return (
    <>
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className={titleClasses}>{entry.title || "Untitled post"}</span>
          {/* On mobile the title is the primary data and space is tight, so drop the byline entirely.
              On desktop it stays shrink-0 so it's always fully visible; the title truncates first. */}
          {!isMobile && (
            <span className="flex items-center gap-1 text-xs shrink-0">
              <span className="text-base-500">by</span>
              <span className={isUnread ? "text-primary" : "text-base-600"}>@{detail.creator_name}</span>
              {detail.group_name && (
                <>
                  <span className="text-base-500">for</span>
                  <span className={isUnread ? "text-primary" : "text-base-600"}>@{detail.group_name}</span>
                </>
              )}
            </span>
          )}
          {detail.is_decided && (
            <span className="inline-flex items-center gap-0.5 text-xs text-base-600/70 shrink-0">
              <span className="material-symbols-outlined text-sm leading-none">check_circle</span>
              Decision
            </span>
          )}
        </div>
        <UserDateTime datetime={entry.last_activity_at} format="relative" className="text-xs text-base-500 shrink-0" />
      </div>
      {/* The second line summarizes the latest event. Authored text (the post body or a discussion
          comment) reads as a plain message preview — not a chip (see EmailThreadEntryBody) — led by
          the author's avatar. Everything else is a client-phrased activity line. */}
      <div className="flex items-center gap-2">
        <span className="dropdown-card rounded-lg inline-flex items-center px-1.5 py-0.5 shadow-sm text-xs text-base-600/70 font-semibold shrink-0 whitespace-nowrap">
          {detail.is_announcement ? "Announcement" : "Post"}
        </span>
        {(previewNodes || activity) && (
          <div className="text-sm/6 flex items-center overflow-hidden min-w-0">
            {previewNodes ? (
              <>
                {author && <Avatar displayName={author.display_name} picture={author.picture} size="small" />}
                <span className={`ml-1 ${previewTextClasses}`}>{previewNodes}</span>
              </>
            ) : (
              <span className={previewTextClasses}>{activity}</span>
            )}
          </div>
        )}
      </div>
    </>
  )
}
