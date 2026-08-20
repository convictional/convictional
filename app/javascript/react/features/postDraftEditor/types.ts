import type { PostMailboxEntry } from "~/react/shared/types"

export interface DraftGroup {
  id: string
  name: string
}

// Mirrors PostDraftShowResponse in app/routers/api/post_drafts.py — everything the
// editor needs beyond the route params: header metadata (title, audience,
// permissions), the attachment upload URL, and the mailbox entry when opened from
// the inbox. The editor body waits for this (title comes from here too).
export interface PostDraftMetadata {
  id: string
  title: string
  group: DraftGroup | null
  is_announcement: boolean
  can_announce: boolean
  is_creator: boolean
  can_delete: boolean
  workspace_id: string
  org_groups: DraftGroup[]
  upload_url: string
  mailbox_entry: PostMailboxEntry | null
}
