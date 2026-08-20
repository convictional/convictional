import { useEffect, useState } from "react"

import { CollectionForm } from "~/react/composites/meetings/CollectionForm"
import { apiFetch, ApiError } from "~/react/shared/apiFetch"
import { fetchAllCollections } from "~/react/shared/collections"
import type { MeetingCollectionListItem, MeetingCollectionRef } from "~/react/shared/types"
import { Dialog } from "~/react/ui/Dialog"
import { Dropdown } from "~/react/ui/Dropdown"
import { Tooltip } from "~/react/ui/Tooltip"
import { showFlash } from "~/shared/flash"

interface CollectionPickerProps<TMeeting> {
  meetingId: string
  collection: MeetingCollectionRef | null
  onMeetingUpdated: (meeting: TMeeting) => void
}

export function CollectionPicker<TMeeting = unknown>({
  meetingId,
  collection,
  onMeetingUpdated,
}: CollectionPickerProps<TMeeting>) {
  const [open, setOpen] = useState(false)
  const [collections, setCollections] = useState<MeetingCollectionListItem[] | null>(null)
  const [query, setQuery] = useState("")
  const [saving, setSaving] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)

  // Lazy-fetch the full list on first open. The endpoint paginates, so
  // fetchAllCollections drains every page — the in-memory filter searches only
  // what we load, and collections past the first page would otherwise be
  // unreachable.
  useEffect(() => {
    if (!open || collections !== null) return
    const controller = new AbortController()
    void (async () => {
      try {
        const { collections: all } = await fetchAllCollections(controller.signal)
        setCollections(all)
      } catch (e) {
        if (e instanceof DOMException && e.name === "AbortError") return
        setCollections([])
      }
    })()
    return () => controller.abort()
  }, [open, collections])

  async function assign(targetCollectionId: string | null) {
    setSaving(true)
    try {
      const updated = await apiFetch<TMeeting>(`/api/meetings/${meetingId}`, {
        method: "PATCH",
        body: JSON.stringify({ collection_id: targetCollectionId }),
      })
      onMeetingUpdated(updated)
    } catch (err) {
      const detail = err instanceof ApiError && typeof err.body?.detail === "string" ? err.body.detail : null
      showFlash(detail ?? "Could not move this meeting.", "error")
    } finally {
      setSaving(false)
    }
  }

  function refetchCollections() {
    setCollections(null)
  }

  // Creating a collection only creates it — it does not move the current meeting
  // into it. Refetch so the new collection appears in the list, where the user
  // can then choose to assign it.
  function handleCollectionCreated() {
    setCreateOpen(false)
    refetchCollections()
  }

  const filtered = (collections ?? []).filter(c => c.title.toLowerCase().includes(query.toLowerCase()))

  const triggerLabel = collection ? collection.title : "No collection"

  return (
    <>
      <Dropdown
        open={open}
        onOpenChange={setOpen}
        placement="bottom-start"
        trigger={
          <button type="button" className="btn" disabled={saving}>
            {triggerLabel}
            {collection?.auto_assigned ? (
              <Tooltip content="Auto-assigned by AI">
                <span className="material-symbols-outlined text-lg transition -mr-1">auto_awesome</span>
              </Tooltip>
            ) : (
              <span className="material-symbols-outlined text-lg transition -mr-1">drive_file_move</span>
            )}
          </button>
        }
      >
        {({ close }) => (
          <div className="w-72 flex flex-col">
            {collection && (
              <>
                <div className="p-2">
                  <span className="text-xs font-semibold opacity-75 pl-1">Current Collection</span>
                  <div className="grid grid-cols-[auto_1fr_auto_auto] items-center gap-2 px-2 py-1">
                    <span className="material-symbols-outlined text-lg">folder</span>
                    <span className="text-xs font-semibold truncate">{collection.title}</span>
                    <a
                      href={`/meetings?collection_id=${collection.id}`}
                      className="btn btn-sm btn-ghost btn-square"
                      aria-label="View collection"
                    >
                      <span className="material-symbols-outlined text-lg">open_in_new</span>
                    </a>
                    <button
                      type="button"
                      className="btn btn-sm btn-ghost btn-square"
                      aria-label="Remove from this collection"
                      onClick={() => {
                        void assign(null)
                        close()
                      }}
                    >
                      <span className="material-symbols-outlined text-lg">close</span>
                    </button>
                  </div>
                </div>
                <p className="text-xs flex items-center justify-center gap-1 text-base-500 mx-3">
                  Recurring meetings will be added to the same collection
                </p>
                <div className="divider my-0" />
              </>
            )}
            <div className="p-2">
              <div className="pb-2">
                <input
                  type="text"
                  autoFocus
                  value={query}
                  onChange={e => setQuery(e.target.value)}
                  placeholder="Filter collections..."
                  className="input input-sm input-bordered !outline-none bg-base-50 w-full"
                />
              </div>
              <span className="text-xs font-semibold opacity-75 px-1">
                {collection ? "Move to Collection" : "Add to Collection"}
              </span>
              <ul className="max-h-48 overflow-y-auto grid gap-1 mt-1">
                {collections === null && <li className="text-center py-2 text-sm text-base-500">Loading…</li>}
                {collections !== null && filtered.length === 0 && (
                  <li className="text-center py-2 text-sm text-base-500">No collections match your filter</li>
                )}
                {filtered
                  .filter(c => c.id !== collection?.id)
                  .map(c => (
                    <li key={c.id}>
                      <button
                        type="button"
                        onClick={() => {
                          void assign(c.id)
                          close()
                        }}
                        className="dropdown-item p-1 w-full text-left"
                      >
                        <div className="grid grid-cols-[auto_1fr] items-center gap-2">
                          <span className="material-symbols-outlined text-lg">folder</span>
                          <div className="flex flex-col min-w-0">
                            <span className="text-xs font-semibold truncate">{c.title}</span>
                            {c.description && <span className="text-xs opacity-60 truncate">{c.description}</span>}
                          </div>
                        </div>
                      </button>
                    </li>
                  ))}
              </ul>
            </div>
            <div className="divider my-0" />
            <div className="p-2">
              <button
                type="button"
                onClick={() => {
                  setCreateOpen(true)
                  close()
                }}
                className="dropdown-item p-2 flex items-center gap-2 text-sm w-full text-left"
              >
                <span className="material-symbols-outlined text-lg">add</span>
                Create new collection
              </button>
            </div>
          </div>
        )}
      </Dropdown>
      <CreateCollectionDialog
        isOpen={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={handleCollectionCreated}
      />
    </>
  )
}

interface CreateCollectionDialogProps {
  isOpen: boolean
  onClose: () => void
  onCreated: (collection: MeetingCollectionListItem) => void | Promise<void>
}

function CreateCollectionDialog({ isOpen, onClose, onCreated }: CreateCollectionDialogProps) {
  return (
    <Dialog
      isOpen={isOpen}
      onClose={onClose}
      ariaLabel="Create new collection"
      className="max-w-md bg-base-100 rounded-xl p-6"
    >
      <h3 className="text-lg font-semibold mb-4">Create New Collection</h3>
      <CollectionForm
        submitLabel="Create collection"
        onSubmit={async (title, description) => {
          try {
            const created = await apiFetch<MeetingCollectionListItem>("/api/meetings_collections", {
              method: "POST",
              body: JSON.stringify({ title, description }),
            })
            await onCreated(created)
            onClose()
            return null
          } catch (err) {
            return err instanceof ApiError && typeof err.body?.detail === "string"
              ? err.body.detail
              : "Could not create collection."
          }
        }}
        onCancel={onClose}
      />
    </Dialog>
  )
}
