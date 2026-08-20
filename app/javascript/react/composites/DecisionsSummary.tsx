import { markdownToPlainText } from "~/react/composites/markdown/toPlainText"
import type { Decision } from "~/react/shared/types"
import { Avatar } from "~/react/ui/Avatar"

interface DecisionsSummaryProps {
  decisions: Decision[]
  // The island scrolls/highlights its own rendered comment for this gid.
  onJump: (commentGid: string) => void
}

function DecisionRow({ decision, onJump }: { decision: Decision; onJump: (commentGid: string) => void }) {
  // null preview means the anchored comment was deleted — the decision stands, so show a tombstone rather than dropping the row.
  const preview =
    decision.comment_preview === null ? "This comment was deleted" : markdownToPlainText(decision.comment_preview)
  const isTombstone = decision.comment_preview === null

  return (
    <button
      type="button"
      onClick={() => onJump(decision.comment_gid)}
      className="w-full flex items-center gap-2 py-1 px-1 -mx-1 rounded hover:bg-base-200 transition group/item text-left"
    >
      {decision.decided_by && (
        <Avatar picture={decision.decided_by.picture} displayName={decision.decided_by.display_name} size="small" />
      )}
      <span className={`text-xs truncate flex-1 ${isTombstone ? "italic text-base-500" : "text-base-content"}`}>
        {preview}
      </span>
      {decision.decided_by && (
        <span className="text-xs text-base-content/40 shrink-0">marked by {decision.decided_by.display_name}</span>
      )}
      <span className="material-symbols-outlined text-sm text-base-content/40 group-hover/item:text-base-content transition">
        arrow_forward
      </span>
    </button>
  )
}

// At-a-glance roll-up of every decision recorded in a workspace. Presentational
// and prop-driven (no API/channel/thread knowledge) so every island can reuse
// it. Renders nothing when there are no decisions — the island shows no shell.
export function DecisionsSummary({ decisions, onJump }: DecisionsSummaryProps) {
  if (decisions.length === 0) return null

  return (
    <div className="border-t border-base-300">
      <div className="flex items-center gap-1.5 px-3 pt-2.5 text-xs font-semibold text-decision-content">
        <span className="material-symbols-outlined text-[16px]">alt_route</span>
        {decisions.length === 1 ? "Decision" : `${decisions.length} decisions`}
      </div>
      <div className="px-3 py-2 space-y-0.5">
        {decisions.map(decision => (
          <DecisionRow key={decision.id} decision={decision} onJump={onJump} />
        ))}
      </div>
    </div>
  )
}
