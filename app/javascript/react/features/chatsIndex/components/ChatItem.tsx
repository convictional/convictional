import { useMemo } from "react"

import { AvatarGroup } from "~/react/composites/AvatarGroup"
import { markdownToPlainText } from "~/react/composites/markdown/toPlainText"
import { withReturnTo } from "~/react/shared/returnTo"
import { Avatar } from "~/react/ui/Avatar"
import { DateTime } from "~/react/ui/DateTime"
import type { ChatListItem } from "../types"

interface ChatItemProps {
  chat: ChatListItem
  isSelected: boolean
  isHovered: boolean
  isNavigating: boolean
  navigatingDisabled: boolean
  inputFocused?: boolean
  onSelect: () => void
  onHover: () => void
}

export function ChatItem({
  chat,
  isSelected,
  isHovered,
  isNavigating,
  navigatingDisabled,
  inputFocused = false,
  onSelect,
  onHover,
}: ChatItemProps) {
  const latestMessage = chat.latest_message
  const authorName = latestMessage?.user.display_name.split(" ")[0] ?? ""
  const latestMessageContent = latestMessage?.content
  const previewContent = useMemo(
    () => (latestMessageContent ? markdownToPlainText(latestMessageContent) : ""),
    [latestMessageContent]
  )
  // Mute only the avatars and message text on read chats — not the row's hover
  // background, selection bar, or keyboard hint, which must match unread rows.
  const mutedWhenRead = chat.is_unread ? "" : "grayscale"

  return (
    <a
      href={withReturnTo(`/chats/${chat.id}`)}
      onClick={e => {
        e.preventDefault()
        onSelect()
      }}
      onMouseEnter={onHover}
      className={`flex items-center gap-3 py-3 pl-2 pr-3 rounded-lg hover:bg-base-200 transition-colors duration-75 ${
        isHovered ? "bg-base-200" : ""
      } ${navigatingDisabled && !isNavigating ? "opacity-50 pointer-events-none" : ""}`}
    >
      <div className="w-3 flex items-center justify-center shrink-0 -mr-1.5">
        {isSelected && inputFocused ? (
          <div className="w-1.5 h-8 bg-primary rounded-full @mobile:hidden" />
        ) : (
          chat.is_unread && <div className="w-1.5 h-1.5 rounded-full bg-info-content" />
        )}
      </div>
      <div className={`shrink-0 ${chat.is_unread ? "" : "opacity-75"} ${mutedWhenRead}`}>
        {chat.type === "group" ? (
          <div className="relative">
            <div className="w-8 h-8 rounded-full bg-base-300 flex items-center justify-center">
              <span className="material-symbols-outlined text-base-content/50">group</span>
            </div>
            {latestMessage && (
              <div className="absolute -bottom-0.5 -right-1 ring-2 ring-base-100 rounded-full">
                <Avatar displayName={latestMessage.user.display_name} picture={latestMessage.user.picture} size="xs" />
              </div>
            )}
          </div>
        ) : chat.type === "self" ? (
          <div className="w-8 h-8 rounded-full bg-base-300 flex items-center justify-center">
            <span className="material-symbols-outlined text-base-content/50">edit_note</span>
          </div>
        ) : chat.type === "multi" ? (
          <AvatarGroup users={(chat.collaborators ?? []).map(m => m.user)} />
        ) : chat.user ? (
          <Avatar displayName={chat.user.display_name} picture={chat.user.picture} size="large" />
        ) : (
          <div className="w-8 h-8 rounded-full bg-neutral-300" />
        )}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between gap-2">
          <span
            className={`text-sm truncate flex items-center gap-1 ${chat.is_unread ? "font-semibold" : "font-medium"} ${mutedWhenRead}`}
          >
            {chat.name}
            {(chat.type === "group" || chat.type === "multi") && (
              <span className="font-normal text-base-500 bg-base-200 rounded-full px-1.5 py-0.5 inline-flex items-center gap-0.5 text-[11px]">
                <span className="material-symbols-outlined leading-none text-[12px]">person</span>
                <span className="leading-none">{chat.collaborator_count}</span>
              </span>
            )}
          </span>
          <div className="shrink-0 text-right relative">
            {latestMessage && (
              <DateTime
                datetime={latestMessage.created_at}
                format="relative"
                className={`text-xs text-base-500 ${isSelected && inputFocused && !isNavigating ? "@desktop:opacity-0" : ""}`}
              />
            )}
            {isNavigating ? (
              <span
                className={`loading loading-spinner loading-xs ${latestMessage ? "absolute top-0 right-0" : ""}`}
              ></span>
            ) : (
              isSelected &&
              inputFocused && (
                <span
                  className={`text-sm text-primary-themed @mobile:hidden ${latestMessage ? "absolute top-0 right-0" : ""}`}
                >
                  <kbd className="kbd kbd-sm kbd-primary">↵</kbd> open
                </span>
              )
            )}
          </div>
        </div>
        {latestMessage && (
          <p className={`text-xs text-base-500 truncate mt-0.5 ${mutedWhenRead}`}>
            <span className="font-medium">{authorName}:</span> {previewContent}
          </p>
        )}
      </div>
    </a>
  )
}
