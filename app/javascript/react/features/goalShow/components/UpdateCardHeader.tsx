import { StatusPie } from "~/react/composites/goals/StatusPie"
import { UserAvatar } from "~/react/composites/UserAvatar"
import { STATUS_CONFIG } from "~/react/shared/statusConfig"
import type { User } from "~/react/shared/types"
import { DateTime } from "~/react/ui/DateTime"

interface UpdateCardHeaderProps {
  creator: User | null
  status: string
  progress: number | null
  createdAt: string
  // The latest update shows status as a filled pill; timeline entries show it as plain text.
  statusVariant: "pill" | "text"
  requestedBy?: User | null
}

// Shared top row for goal update cards: author on the left, status + progress + freshness on the
// right. Used by both the latest-update card and every timeline update so they read identically.
export function UpdateCardHeader({
  creator,
  status,
  progress,
  createdAt,
  statusVariant,
  requestedBy,
}: UpdateCardHeaderProps) {
  const statusConfig = STATUS_CONFIG[status]
  const percent = progress != null ? Math.round(progress * 100) : null
  const progressTip = percent != null ? `${percent}% complete` : "Progress not tracked"

  return (
    <div className="flex justify-between items-center gap-4">
      <div className="flex items-center gap-2 flex-1 min-w-0">
        {creator && <UserAvatar user={creator} size="medium" />}
        <div className="min-w-0">
          <span className="text-sm font-medium text-base-content">{creator?.display_name}</span>
          {requestedBy && <p className="text-xs text-base-content/50">Responding to {requestedBy.display_name}</p>}
        </div>
      </div>

      <div className="flex items-center gap-2 shrink-0">
        {statusConfig &&
          (statusVariant === "pill" ? (
            <span
              className={`inline-flex items-center text-xs font-medium px-2.5 py-1 rounded-full border ${statusConfig.classes}`}
            >
              {statusConfig.text}
            </span>
          ) : (
            <span className={`text-xs font-medium ${statusConfig.textClass}`}>{statusConfig.text}</span>
          ))}
        <StatusPie progress={progress} size={20} tooltipContent={progressTip} />
        <DateTime datetime={createdAt} format="relative" className="text-xs text-base-content/40 whitespace-nowrap" />
      </div>
    </div>
  )
}
