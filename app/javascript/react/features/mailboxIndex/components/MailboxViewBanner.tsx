interface MailboxViewBannerProps {
  newMessagesCount: number
  // Inbox items left outside the organized slice; reachable only by regenerating.
  uncoveredCount: number
  cleared: boolean
  onRefresh: () => void
}

// One banner, not two: both staleness conditions can hold at once and the same refresh answers both,
// so stacking a second would just repeat the button.
function bannerMessage({
  newMessagesCount,
  uncoveredCount,
  cleared,
}: Omit<MailboxViewBannerProps, "onRefresh">): string | null {
  if (cleared && uncoveredCount > 0)
    return "You've cleared everything here. Refresh to organize the rest of your inbox."
  if (newMessagesCount > 0)
    return `${newMessagesCount} new conversation${newMessagesCount === 1 ? "" : "s"} not included.`
  return null
}

export function MailboxViewBanner({ newMessagesCount, uncoveredCount, cleared, onRefresh }: MailboxViewBannerProps) {
  const message = bannerMessage({ newMessagesCount, uncoveredCount, cleared })
  if (message === null) return null
  return (
    <div className="px-4 py-2 text-center text-sm text-base-600 border-b border-neutral bg-base-100">
      <span>{message}</span>
      <button type="button" className="btn btn-sm ml-2" onClick={onRefresh}>
        Refresh
      </button>
    </div>
  )
}
