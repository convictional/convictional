import { confirm } from "~/react/composites/confirmationDialog/confirm"

import type { AttachmentResponse } from "../types"

interface AttachmentListProps {
  attachments: AttachmentResponse[]
  onDelete: (attachment: AttachmentResponse) => void
}

export function AttachmentList({ attachments, onDelete }: AttachmentListProps) {
  const items = attachments.filter(a => !a.is_inline)
  if (items.length === 0) return null

  return (
    <div className="px-4 pb-4">
      <h3 className="text-sm font-medium mb-2">Attachments</h3>
      <ul className="list-disc pl-5 space-y-1">
        {items.map(attachment => (
          <li key={attachment.id} className="flex items-center gap-2 max-w-96">
            <a href={attachment.download_url} className="link truncate" target="_blank" rel="noopener noreferrer">
              {attachment.filename}
            </a>
            <button
              type="button"
              className="btn btn-sm btn-ghost"
              onClick={async () => {
                if (await confirm({ message: "Are you sure you want to delete this attachment?" })) {
                  onDelete(attachment)
                }
              }}
              aria-label={`Delete ${attachment.filename}`}
            >
              <span className="material-symbols-outlined text-lg">delete</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}
