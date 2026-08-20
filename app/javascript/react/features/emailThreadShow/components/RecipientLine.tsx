import { useState } from "react"

interface RecipientLineProps {
  to: string[]
  cc: string[]
  currentUserEmail: string | null
  // How many recipients to display in the condensed form before showing
  // "(+N others)". Matches `format_condensed_recipients` in app/helpers/email.py.
  condensedLimit?: number
}

function condense(to: string[], cc: string[], currentUserEmail: string | null, limit: number): string {
  const all = [...to, ...cc]
  const visible = all.slice(0, limit).map(r => (r === currentUserEmail ? "me" : r))
  const extra = all.length - limit
  return extra > 0 ? `${visible.join(", ")} (+${extra} others)` : visible.join(", ")
}

// Toggles between a condensed "to me, alice@example.com (+2 others)" line and
// the full to/cc breakdown.
export function RecipientLine({ to, cc, currentUserEmail, condensedLimit = 2 }: RecipientLineProps) {
  const [expanded, setExpanded] = useState(false)
  if (to.length === 0 && cc.length === 0) return null

  // stopPropagation keeps the click from toggling the surrounding header,
  // which has its own onClick handler.
  if (!expanded) {
    return (
      <div className="text-xs">
        <button
          type="button"
          onClick={e => {
            e.stopPropagation()
            setExpanded(true)
          }}
          className="inline-flex items-center gap-1 cursor-pointer text-left"
        >
          <span className="text-base-500">to</span> {condense(to, cc, currentUserEmail, condensedLimit)}
          <span className="ml-1 text-base-500 hover:text-base-600 hidden sm:inline-block">
            <span className="material-symbols-outlined text-sm">keyboard_arrow_down</span>
          </span>
        </button>
      </div>
    )
  }

  return (
    <div className="text-xs">
      <div>
        <span className="text-base-500">to</span> {to.join(", ")}
      </div>
      {cc.length > 0 && (
        <div>
          <span className="text-base-500">cc</span> {cc.join(", ")}
        </div>
      )}
      <div>
        <button
          type="button"
          onClick={e => {
            e.stopPropagation()
            setExpanded(false)
          }}
          className="text-base-500 hover:text-base-600 cursor-pointer"
        >
          <span className="text-xs">(hide)</span>
        </button>
      </div>
    </div>
  )
}
