// The show endpoint, forwarding mailbox_entry_id from the route so the API
// resolves the (owner-scoped) entry and the header can render its mailbox variant.
export function postShowUrl(postId: string, mailboxEntryId?: string): string {
  return mailboxEntryId
    ? `/api/posts/${postId}?mailbox_entry_id=${encodeURIComponent(mailboxEntryId)}`
    : `/api/posts/${postId}`
}
