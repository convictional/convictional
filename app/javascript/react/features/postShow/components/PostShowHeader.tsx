import { BackButton } from "~/react/composites/BackButton"
import { MailboxActionBar, mailboxActionUrls } from "~/react/composites/MailboxActionBar"
import type { MailboxState } from "~/react/composites/MailboxActionBar"
import { SubscriptionBell } from "~/react/composites/SubscriptionBell"
import { apiFetch } from "~/react/shared/apiFetch"
import type { BackNavigation, Post, PostMailboxEntry } from "~/react/shared/types"
import { StickyHeader } from "~/react/ui/StickyHeader"
import { showFlash } from "~/shared/flash"

import { PostHeaderActions } from "./PostHeaderActions"

interface PostShowHeaderProps {
  post: Post
  mailboxEntry: PostMailboxEntry | null
  back: BackNavigation
  onPinChange: (post: Post) => void
  onMailboxStateChange: (entry: PostMailboxEntry) => void
}

export function PostShowHeader({ post, mailboxEntry, back, onPinChange, onMailboxStateChange }: PostShowHeaderProps) {
  async function setPinned(pinned: boolean) {
    try {
      const updated = await apiFetch<Post>(`/api/posts/${post.id}/pin`, {
        method: "PATCH",
        body: JSON.stringify({ pinned }),
      })
      onPinChange(updated)
    } catch {
      showFlash(pinned ? "Couldn't pin the post." : "Couldn't unpin the post.")
    }
  }

  if (mailboxEntry) {
    const state: MailboxState = {
      isUnread: mailboxEntry.is_unread,
      isArchived: mailboxEntry.is_archived,
      isSnoozed: mailboxEntry.is_snoozed,
      snoozedUntil: mailboxEntry.snoozed_until,
    }
    return (
      <StickyHeader>
        <div className="flex items-center justify-between gap-2 p-2">
          <MailboxActionBar
            state={state}
            actionUrls={mailboxActionUrls(mailboxEntry.id)}
            mailboxEntryId={mailboxEntry.id}
            back={back}
            trailingSlot={
              <SubscriptionBell
                workspaceId={post.workspace_id}
                subtitle={post.is_announcement ? "Sent to everyone." : undefined}
              />
            }
            onStateChange={next =>
              onMailboxStateChange({
                id: mailboxEntry.id,
                is_unread: next.isUnread,
                is_archived: next.isArchived,
                is_snoozed: next.isSnoozed,
                snoozed_until: next.snoozedUntil,
              })
            }
          />
        </div>
      </StickyHeader>
    )
  }

  return (
    <StickyHeader>
      <div className="flex items-center justify-between gap-2 p-2">
        <ul className="flex items-center gap-1">
          <li>
            <BackButton back={back} navLink />
          </li>
        </ul>
        <div className="flex items-center gap-1">
          {post.permissions.pin &&
            (post.is_pinned ? (
              <button type="button" className="btn" onClick={() => void setPinned(false)}>
                <span className="material-symbols-outlined text-lg">push_pin</span>
                Unpin
              </button>
            ) : (
              <button type="button" className="btn" onClick={() => void setPinned(true)}>
                <span className="material-symbols-outlined text-lg">push_pin</span>
                Pin
              </button>
            ))}
          <SubscriptionBell
            workspaceId={post.workspace_id}
            subtitle={post.is_announcement ? "Sent to everyone." : undefined}
          />
          {post.permissions.delete && <PostHeaderActions postId={post.id} />}
        </div>
      </div>
    </StickyHeader>
  )
}
