import { Link } from "@tanstack/react-router"

import type { DocumentListItem } from "~/react/features/documentsIndex/types"
import { DateTime } from "~/react/ui/DateTime"
import { Tooltip } from "~/react/ui/Tooltip"
import { pluralize } from "~/shared/strings"

interface DocumentRowProps {
  document: DocumentListItem
  // The index URL to return to, stamped onto the show page's back link.
  returnTo: string
}

export function DocumentRow({ document, returnTo }: DocumentRowProps) {
  return (
    <Link
      to="/documents/$documentId"
      params={{ documentId: document.id }}
      search={{ return_to: returnTo }}
      className="grid grid-cols-[1fr] md:grid-cols-[1fr_180px_180px] border-b border-base-300 hover:bg-base-200/60 transition-colors"
    >
      <div className="flex flex-col gap-1.5 px-4 py-4 min-w-0 md:flex-row md:items-center md:gap-2 md:py-3">
        <div className="flex items-center gap-2 min-w-0">
          <span className="truncate text-base">{document.title}</span>
          <div className="hidden md:flex items-center gap-2 shrink-0">
            {document.comment_count > 0 && (
              <Tooltip content={`${document.comment_count} open ${pluralize(document.comment_count, "comment")}`}>
                <span className="shrink-0 w-5 h-5 rounded-full bg-info border border-primary/20 text-xs font-medium text-primary flex items-center justify-center">
                  {document.comment_count}
                </span>
              </Tooltip>
            )}
            {document.sharing === "organization" && (
              <Tooltip content="Visible to everyone">
                <span className="material-symbols-outlined text-lg text-base-500">public</span>
              </Tooltip>
            )}
            {document.collaborator_count > 1 && (
              <Tooltip content="Shared with collaborators">
                <span className="material-symbols-outlined text-lg text-base-500">group</span>
              </Tooltip>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2 flex-wrap md:hidden text-xs">
          <span className="text-base-content/80">{document.author_display_name}</span>
          <span className="text-base-content/60">
            {document.last_viewed_at ? (
              <DateTime datetime={document.last_viewed_at} format="relative" />
            ) : (
              "Never viewed"
            )}
          </span>
          {document.comment_count > 0 && (
            <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-info border border-primary/20 text-xs font-medium text-primary">
              {document.comment_count}
            </span>
          )}
          {document.sharing === "organization" && (
            <span className="inline-flex items-center text-base-content/60">
              <span className="material-symbols-outlined text-sm">public</span>
            </span>
          )}
          {document.collaborator_count > 1 && (
            <span className="inline-flex items-center gap-1 text-base-content/60">
              <span className="material-symbols-outlined text-sm">group</span>
              Shared
            </span>
          )}
        </div>
      </div>
      <div className="hidden md:flex items-center px-4 py-3 text-sm text-base-600">{document.author_display_name}</div>
      <div className="hidden md:flex items-center px-4 py-3 text-sm text-base-600">
        {document.last_viewed_at ? <DateTime datetime={document.last_viewed_at} format="relative" /> : "—"}
      </div>
    </Link>
  )
}
