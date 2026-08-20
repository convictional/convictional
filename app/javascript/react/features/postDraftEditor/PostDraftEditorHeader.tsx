import { useState } from "react"

import { BackButton } from "~/react/composites/BackButton"
import { confirm } from "~/react/composites/confirmationDialog/confirm"
import { MailboxActionBar, mailboxActionUrls } from "~/react/composites/MailboxActionBar"
import type { MailboxState } from "~/react/composites/MailboxActionBar"
import { SearchablePicker } from "~/react/composites/SearchablePicker"
import { WorkspaceCollaborators } from "~/react/composites/workspaceCollaborators/WorkspaceCollaborators"
import { ApiError, apiFetch } from "~/react/shared/apiFetch"
import { boostedNavigate } from "~/react/shared/boostedNavigate"
import type { BackNavigation, PostMailboxEntry } from "~/react/shared/types"
import { StickyHeader } from "~/react/ui/StickyHeader"
import { showFlash } from "~/shared/flash"

import type { PostDraftMetadata } from "./types"

interface Props {
  postId: string
  back: BackNavigation
  metadata: PostDraftMetadata | null
  onMetadataChange: (next: PostDraftMetadata) => void
  savingTitle: boolean
  titleEverChanged: boolean
  publishing: boolean
  onPublish: () => void
}

export function PostDraftEditorHeader({
  postId,
  back,
  metadata,
  onMetadataChange,
  savingTitle,
  titleEverChanged,
  publishing,
  onPublish,
}: Props) {
  const canDelete = metadata?.can_delete ?? false
  // The mailbox entry rides on the same draft query as the rest of the metadata,
  // so it's null until that resolves (header shows the plain back button first).
  const mailboxEntry = metadata?.mailbox_entry ?? null

  return (
    <StickyHeader>
      <div className="flex items-center justify-between gap-2 p-2 border-b border-neutral">
        {mailboxEntry ? (
          <div className="flex-1 min-w-0">
            <MailboxActionBar
              state={mailboxState(mailboxEntry)}
              actionUrls={mailboxActionUrls(mailboxEntry.id)}
              mailboxEntryId={mailboxEntry.id}
              back={back}
            />
          </div>
        ) : (
          <BackButton back={back} />
        )}
        <div className="flex items-center gap-2 ml-2">
          {metadata && <WorkspaceCollaborators workspaceId={metadata.workspace_id} />}
        </div>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2 p-2">
        <div id="draft-toolbar-target" className="flex flex-wrap items-center gap-1" />
        <div className="flex items-center gap-2">
          <div id="draft-sync-status-target" />
          {titleEverChanged && <SaveIndicator saving={savingTitle} />}
          {canDelete && <DeleteButton postId={postId} back={back} />}
          <div className="join">
            {metadata?.is_creator && (
              <GroupAnnouncementPicker postId={postId} metadata={metadata} onMetadataChange={onMetadataChange} />
            )}
            <button
              type="button"
              className="btn btn-primary join-item"
              title="⌘↵ to submit"
              onClick={onPublish}
              disabled={publishing}
            >
              Post
            </button>
          </div>
        </div>
      </div>
    </StickyHeader>
  )
}

function mailboxState(entry: PostMailboxEntry): MailboxState {
  return {
    isUnread: entry.is_unread,
    isArchived: entry.is_archived,
    isSnoozed: entry.is_snoozed,
    snoozedUntil: entry.snoozed_until,
  }
}

function SaveIndicator({ saving }: { saving: boolean }) {
  return (
    <div className="text-base-500 flex items-center gap-1">
      {saving ? (
        <span className="loading loading-spinner loading-xs" />
      ) : (
        <span className="material-symbols-outlined text-lg">check</span>
      )}
      <p className="text-sm hidden sm:block">{saving ? "Saving..." : "Saved"}</p>
    </div>
  )
}

function GroupAnnouncementPicker({
  postId,
  metadata,
  onMetadataChange,
}: {
  postId: string
  metadata: PostDraftMetadata
  onMetadataChange: (next: PostDraftMetadata) => void
}) {
  const icon = metadata.is_announcement ? "campaign" : "group"
  const label = metadata.is_announcement ? "Announcement" : metadata.group ? `@${metadata.group.name}` : "Everyone"

  async function select(next: Partial<PostDraftMetadata>, body: object, close: () => void) {
    close()
    const previous = metadata
    onMetadataChange({ ...metadata, ...next })
    try {
      await apiFetch(`/api/posts/${postId}/draft`, { method: "PATCH", body: JSON.stringify(body) })
    } catch {
      onMetadataChange(previous)
      showFlash("Failed to update audience. Please try again.")
    }
  }

  const trigger = (
    <button type="button" className="btn join-item">
      <span className="material-symbols-outlined text-base">{icon}</span>
      <span>{label}</span>
      <span className="material-symbols-outlined text-sm">keyboard_arrow_down</span>
    </button>
  )

  return (
    <SearchablePicker
      trigger={trigger}
      title="Audience"
      ariaLabel="Audience options"
      items={metadata.org_groups}
      getKey={g => g.id}
      getSearchText={g => g.name}
      searchPlaceholder="Search groups…"
      renderHeader={close => (
        <div className="px-2">
          <button
            type="button"
            onClick={() =>
              void select({ group: null, is_announcement: false }, { group_id: null, is_announcement: false }, close)
            }
            className="dropdown-item w-full text-left text-sm"
          >
            Everyone
          </button>
        </div>
      )}
      renderItem={(group, close) => (
        <button
          type="button"
          onClick={() =>
            void select({ group, is_announcement: false }, { group_id: group.id, is_announcement: false }, close)
          }
          className="dropdown-item w-full text-left text-sm"
        >
          {group.name}
        </button>
      )}
      renderFooter={close =>
        metadata.can_announce ? (
          <div className="px-2">
            <button
              type="button"
              onClick={() =>
                void select({ group: null, is_announcement: true }, { group_id: null, is_announcement: true }, close)
              }
              className="dropdown-item w-full text-left text-sm"
            >
              <div>Announcement</div>
              <div className="text-xs opacity-50">Everyone, even if unsubscribed</div>
            </button>
          </div>
        ) : null
      }
    />
  )
}

function DeleteButton({ postId, back }: { postId: string; back: BackNavigation }) {
  const [deleting, setDeleting] = useState(false)

  async function handleDelete() {
    if (deleting) return
    if (!(await confirm({ message: "Are you sure you want to delete this draft?" }))) return
    setDeleting(true)
    try {
      await apiFetch(`/api/posts/${postId}`, { method: "DELETE" })
      boostedNavigate(back.url)
    } catch (error) {
      setDeleting(false)
      const status = error instanceof ApiError ? error.status : 0
      showFlash(
        status === 403 ? "Only the creator or an admin can delete this draft." : "Failed to delete. Please try again."
      )
    }
  }

  return (
    <button type="button" className="btn" onClick={handleDelete} disabled={deleting}>
      Delete
    </button>
  )
}
