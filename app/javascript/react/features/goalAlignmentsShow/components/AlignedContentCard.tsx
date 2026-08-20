import { Markdown } from "~/react/composites/markdown/Markdown"
import { CONTENT_TYPE_ICONS } from "~/react/shared/contentTypes"
import { Avatar } from "~/react/ui/Avatar"
import type { GoalAlignment } from "../types"

const SIGNAL_LABELS: Record<string, string> = {
  strong: "Strong",
  medium: "Medium",
  weak: "Weak",
}

export function AlignedContentCard({
  alignment,
  onTogglePin,
  onDelete,
}: {
  alignment: GoalAlignment
  onTogglePin: (alignment: GoalAlignment) => void
  onDelete: (alignment: GoalAlignment) => void
}) {
  const { content, pinned, signal, score, description } = alignment
  const creator = alignment.created_by
  const icon = CONTENT_TYPE_ICONS[content.content_type] ?? "description"

  return (
    <div className={`card card-compact bg-base-200 transition group ${pinned ? "ring-1 ring-warning/30" : ""}`}>
      <div className="card-body px-4 py-3">
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="material-symbols-outlined text-lg text-base-400 shrink-0">{icon}</span>
              <a href={content.source_url} className="text-sm font-semibold group-hover:underline line-clamp-2">
                {content.title}
              </a>
            </div>
            <div className="flex items-center gap-2 mt-1 text-xs text-base-500">
              <span className="badge badge-sm badge-ghost">{SIGNAL_LABELS[signal] ?? signal}</span>
              <span>{Math.round(score * 100)}% match</span>
              {creator && (
                <span className="flex items-center gap-1">
                  <Avatar displayName={creator.display_name} picture={creator.picture} size="xs" />
                  {creator.display_name}
                </span>
              )}
            </div>
            {description && (
              <div className="mt-2 text-sm text-base-600">
                <Markdown source={description} variant="compact" />
              </div>
            )}
          </div>
          <div className="flex items-center gap-1 shrink-0">
            <button
              type="button"
              className="btn btn-ghost btn-xs btn-circle"
              aria-label={pinned ? "Unpin" : "Pin"}
              onClick={() => onTogglePin(alignment)}
            >
              <span className={`material-symbols-outlined text-base ${pinned ? "text-primary" : "text-base-400"}`}>
                push_pin
              </span>
            </button>
            <button
              type="button"
              className="btn btn-ghost btn-xs btn-circle"
              aria-label="Remove"
              onClick={() => onDelete(alignment)}
            >
              <span className="material-symbols-outlined text-base text-base-400">delete</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
