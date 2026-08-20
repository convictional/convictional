import { useMemo } from "react"

import { markdownToPreviewNodes } from "~/react/composites/markdown/toPreviewNodes"
import { UserDateTime } from "~/react/composites/UserDateTime"
import type { MailboxEntry } from "~/react/features/mailboxIndex/types"
import { useCurrentUser } from "~/react/shared/hooks/useCurrentUser"
import { useOrganizationMembers } from "~/react/shared/hooks/useOrganizationMembers"
import { Avatar } from "~/react/ui/Avatar"

import { describeChatActivity } from "./chatActivityPreview"

interface ChatEntryBodyProps {
  entry: MailboxEntry
}

export function ChatEntryBody({ entry }: ChatEntryBodyProps) {
  const detail = entry.chat
  const isUnread = entry.is_unread
  const { users } = useOrganizationMembers()
  const { user } = useCurrentUser()
  const preview = useMemo(
    () =>
      detail?.last_comment
        ? markdownToPreviewNodes(detail.last_comment, {
            mentionClassName: isUnread ? "text-info-content" : "text-base-500",
          })
        : null,
    [detail?.last_comment, isUnread]
  )
  if (!detail) return null

  const activity =
    detail.preview_kind === "activity"
      ? describeChatActivity(detail.event_action, detail.event_details, {
          actorName: detail.event_actor?.display_name,
          actorId: detail.event_actor?.id,
          currentUserId: user?.id,
          resolveUserName: id => users.find(u => u.id === id)?.display_name,
        })
      : null

  return (
    <div className="flex items-center gap-3">
      <div className={`shrink-0 ${isUnread ? "" : "grayscale opacity-75"}`}>
        {detail.is_group_chat ? (
          <div className="relative">
            <div className="w-8 h-8 rounded-full bg-base-300 flex items-center justify-center">
              <span className="material-symbols-outlined text-base-content/50">group</span>
            </div>
            {detail.last_message_author && (
              <div className="absolute -bottom-0.5 -right-1 ring-2 ring-base-100 rounded-full">
                <Avatar
                  displayName={detail.last_message_author.display_name}
                  picture={detail.last_message_author.picture}
                  size="xs"
                />
              </div>
            )}
          </div>
        ) : detail.member_avatars.length > 0 ? (
          <div className="relative w-8 h-4">
            {detail.member_avatars.map((member, i) => (
              <div
                key={member.id}
                className="absolute ring-2 ring-base-100 rounded-full"
                style={{ left: `${i * 8}px`, zIndex: i }}
              >
                <Avatar displayName={member.display_name} picture={member.picture} size="xs" />
              </div>
            ))}
            {detail.overflow_count > 0 && (
              <div
                className="absolute w-4 h-4 rounded-full bg-base-300 flex items-center justify-center ring-2 ring-base-100 text-[9px] text-base-content/70 font-medium"
                style={{ left: `${detail.member_avatars.length * 8}px`, top: 0, zIndex: detail.member_avatars.length }}
              >
                +{detail.overflow_count}
              </div>
            )}
          </div>
        ) : detail.counterparty ? (
          <Avatar displayName={detail.counterparty.display_name} picture={detail.counterparty.picture} size="large" />
        ) : (
          <div className="w-8 h-8 rounded-full bg-neutral-300" />
        )}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between gap-2">
          <span
            className={`text-sm truncate flex items-center gap-1 ${
              isUnread ? "font-semibold text-base-700" : "font-medium text-base-600/70"
            }`}
          >
            {entry.title || "Chat"}
            {detail.is_group_chat || detail.collaborator_count > 2 ? (
              <span className="font-normal text-base-500 bg-base-200 rounded-full px-1.5 py-0.5 inline-flex items-center gap-0.5 text-[11px]">
                <span className="material-symbols-outlined leading-none text-[12px]">person</span>
                <span className="leading-none">{detail.collaborator_count}</span>
              </span>
            ) : null}
          </span>
          <UserDateTime
            datetime={entry.last_activity_at}
            format="relative"
            className="text-xs text-base-500 shrink-0 group-hover:hidden"
          />
        </div>
        {activity ? (
          <p className={`text-xs truncate mt-0.5 ${isUnread ? "text-base-600" : "text-base-500"}`}>{activity}</p>
        ) : (
          detail.last_comment && (
            <p className={`text-xs truncate mt-0.5 ${isUnread ? "text-base-600" : "text-base-500"}`}>
              {detail.last_comment_author_name && (
                <span className="font-medium">{detail.last_comment_author_name}: </span>
              )}
              {preview}
            </p>
          )
        )}
      </div>
    </div>
  )
}
