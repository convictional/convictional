import { useState } from "react"

import { confirm } from "~/react/composites/confirmationDialog/confirm"
import { CollectionForm } from "~/react/composites/meetings/CollectionForm"
import { boostedNavigate } from "~/react/shared/boostedNavigate"
import type { MeetingCollectionListItem } from "~/react/shared/types"
import { Tooltip } from "~/react/ui/Tooltip"
import { showFlash } from "~/shared/flash"

interface CollectionHeaderProps {
  collection: MeetingCollectionListItem
  collectionsIndexUrl: string
  onUpdate: (changes: { title?: string; description?: string | null }) => Promise<string | null>
  onDelete: () => Promise<string | null>
}

export function CollectionHeader({ collection, collectionsIndexUrl, onUpdate, onDelete }: CollectionHeaderProps) {
  const [editing, setEditing] = useState(false)

  return (
    <div className="mb-4">
      <div className="flex items-center justify-between gap-2 px-1">
        <nav aria-label="Breadcrumb" className="flex items-center gap-2 text-sm min-w-0">
          <a
            href={collectionsIndexUrl}
            className="text-base-content/60 hover:text-base-content transition-colors shrink-0"
          >
            All Collections
          </a>
          <span className="text-base-content/30 shrink-0">/</span>
          <span className="font-semibold truncate text-base-content">{collection.title}</span>
        </nav>
        {!collection.auto_assigned && (
          <div className="flex items-center gap-1 shrink-0">
            <Tooltip content="Edit collection" placement="bottom">
              <button
                type="button"
                onClick={() => setEditing(true)}
                aria-label="Edit collection"
                className="btn btn-ghost btn-circle btn-sm"
              >
                <span className="material-symbols-outlined text-lg">edit</span>
              </button>
            </Tooltip>
            <Tooltip content="Delete collection - contents will remain available in recent" placement="bottom">
              <button
                type="button"
                onClick={async () => {
                  const ok = await confirm({
                    title: "Delete collection?",
                    message: "Are you sure you want to delete this collection?",
                    confirmLabel: "Delete",
                  })
                  if (!ok) return
                  const err = await onDelete()
                  if (err) {
                    showFlash(err, "error")
                    return
                  }
                  boostedNavigate(collectionsIndexUrl)
                }}
                aria-label="Delete collection"
                className="btn btn-ghost btn-circle btn-sm"
              >
                <span className="material-symbols-outlined text-lg">delete</span>
              </button>
            </Tooltip>
          </div>
        )}
      </div>
      {collection.description && !editing && (
        <p className="text-sm text-base-content/60 mt-1 px-1">{collection.description}</p>
      )}
      {editing && (
        <div className="mt-3 px-1">
          <CollectionForm
            initialTitle={collection.title}
            initialDescription={collection.description ?? ""}
            submitLabel="Save"
            onSubmit={async (title, description) => {
              const err = await onUpdate({ title, description })
              if (!err) setEditing(false)
              return err
            }}
            onCancel={() => setEditing(false)}
          />
        </div>
      )}
    </div>
  )
}
