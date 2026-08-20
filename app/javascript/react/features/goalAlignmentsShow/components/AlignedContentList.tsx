import { EmptyState } from "~/react/ui/EmptyState"
import type { GoalAlignment } from "../types"
import { AlignedContentCard } from "./AlignedContentCard"

export function AlignedContentList({
  alignments,
  onTogglePin,
  onDelete,
}: {
  alignments: GoalAlignment[]
  onTogglePin: (alignment: GoalAlignment) => void
  onDelete: (alignment: GoalAlignment) => void
}) {
  if (alignments.length === 0) {
    return (
      <EmptyState
        title="No aligned content"
        text="Goal alignment is calculated weekly. New content will be added automatically on Monday."
      />
    )
  }

  return (
    <div className="flex flex-col gap-3">
      {alignments.map(alignment => (
        <AlignedContentCard key={alignment.id} alignment={alignment} onTogglePin={onTogglePin} onDelete={onDelete} />
      ))}
    </div>
  )
}
