// The search contract shared by the content routes reachable from the inbox
// (posts show, post draft editor, chat show): `return_to` (the "back" target) and
// `mailbox_entry_id` (present when opened from an inbox entry, gating the header's
// mailbox variant). Both must be declared so a client navigation to a neighbor
// preserves them — TanStack drops undeclared search params. Route-specific meaning
// lives in the comment above each route's validateSearch.
export interface BackAndMailboxSearch {
  return_to?: string
  mailbox_entry_id?: string
}

export function backAndMailboxSearch(search: Record<string, unknown>): BackAndMailboxSearch {
  return {
    return_to: typeof search.return_to === "string" ? search.return_to : undefined,
    mailbox_entry_id: typeof search.mailbox_entry_id === "string" ? search.mailbox_entry_id : undefined,
  }
}
