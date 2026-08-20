import { ReplyQuote } from "~/react/composites/comment/ReplyQuote"
import { Markdown } from "~/react/composites/markdown/Markdown"
import { stripPreviewedAttachmentLink } from "~/react/composites/stripAttachmentLink"

import type { ChatMessage } from "~/react/shared/types"
import { ChatImage } from "~/react/ui/ChatImage"
import { ChatImageGallery } from "~/react/ui/ChatImageGallery"
import { UserAvatar } from "../UserAvatar"
import { LinkPreviewCard } from "./LinkPreviewCard"

interface MessageBubbleProps {
  message: ChatMessage
  children?: React.ReactNode
  afterBubble?: React.ReactNode
  replaceBubble?: React.ReactNode
  // Required so the ReplyQuote button can never render clickable yet no-op.
  onScrollTo: (id: string) => void
  scrollingToId?: string | null
  isGrouped?: boolean
  // Brief tonal emphasis on the bubble, e.g. at the mobile long-press trigger.
  highlight?: boolean
}

export function MessageBubble({
  message,
  children,
  afterBubble,
  replaceBubble,
  onScrollTo,
  scrollingToId,
  isGrouped,
  highlight,
}: MessageBubbleProps) {
  const hideUsername = isGrouped && !message.edited_at

  return (
    <div>
      {!hideUsername && (
        <div className="text-xs text-base-content/50 ml-8 mb-0.5">
          {message.user.display_name}
          {message.edited_at && <span className="opacity-50"> (edited)</span>}
        </div>
      )}
      <div className="flex gap-2 items-start">
        {isGrouped ? <div className="w-6 h-6 shrink-0" /> : <UserAvatar user={message.user} size="medium" />}
        {replaceBubble ?? (
          <div
            className={`text-base-content rounded-xl px-3 py-1.5 text-sm break-words max-w-[calc(100%-40px)] min-w-0 transition-colors duration-150 ${
              highlight ? "bg-primary/15" : "bg-base-200"
            }`}
          >
            {message.reply_to && (
              <ReplyQuote
                replyTo={message.reply_to}
                onScrollTo={onScrollTo}
                loading={scrollingToId === message.reply_to.id}
                deletedClickable
              />
            )}
            <Markdown
              source={stripPreviewedAttachmentLink(message.content, message.link_preview)}
              variant="compact"
              imageComponent={ChatImage}
              imageGroupComponent={ChatImageGallery}
            />
            {message.link_preview && (
              <div className="mt-1.5">
                <LinkPreviewCard linkPreview={message.link_preview} />
              </div>
            )}
            {children}
          </div>
        )}
        {afterBubble}
      </div>
    </div>
  )
}
