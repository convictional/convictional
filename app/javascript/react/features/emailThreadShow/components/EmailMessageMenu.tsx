import { useBoundaryNavigate } from "~/react/shared/hooks/useBoundaryNavigate"
import { Dropdown } from "~/react/ui/Dropdown"

interface EmailMessageMenuProps {
  viewOriginalUrl: string
  // Whether to show Reply / Reply All / Forward items (gated by the
  // collaboration check `can_be_accessed_by`).
  showReply: boolean
  // Whether to show "View Original" (superuser only).
  showViewOriginal: boolean
  onReply: (replyType: "reply" | "reply_all") => void
  onForward: () => void
}

// Overflow menu attached to each message (the "more_horiz" button in
// `_message_menu.html.jinja`). Reply / Reply All / Forward delegate to the
// JSON POST endpoints via the supplied callbacks; the parent owns the 409
// conflict modal.
export function EmailMessageMenu({
  viewOriginalUrl,
  showReply,
  showViewOriginal,
  onReply,
  onForward,
}: EmailMessageMenuProps) {
  // The original view is a registered SPA route on a concrete parameterized path,
  // which NavLink can't match (it keys off route templates); boundary-navigate
  // matches the template and client-routes, falling back to a full load otherwise.
  const navigate = useBoundaryNavigate()

  if (!showReply && !showViewOriginal) return null

  return (
    <Dropdown
      ariaLabel="Message actions"
      trigger={
        <button type="button" className="btn btn-square btn-ghost shadow-none">
          <span className="material-symbols-outlined text-lg">more_horiz</span>
        </button>
      }
    >
      {({ close }) => (
        <ul>
          {showReply && (
            <>
              <li>
                <button
                  type="button"
                  className="dropdown-item w-full text-left"
                  onClick={() => {
                    onReply("reply")
                    close()
                  }}
                >
                  Reply
                </button>
              </li>
              <li>
                <button
                  type="button"
                  className="dropdown-item w-full text-left"
                  onClick={() => {
                    onReply("reply_all")
                    close()
                  }}
                >
                  Reply All
                </button>
              </li>
              <li>
                <button
                  type="button"
                  className="dropdown-item w-full text-left"
                  onClick={() => {
                    onForward()
                    close()
                  }}
                >
                  Forward
                </button>
              </li>
            </>
          )}
          {showViewOriginal && (
            <li>
              {/* Keep the href for right-click / open-in-new-tab; the click
                  client-routes within the SPA shell. */}
              <a
                href={viewOriginalUrl}
                className="dropdown-item"
                onClick={e => {
                  e.preventDefault()
                  navigate(viewOriginalUrl)
                  close()
                }}
              >
                View Original
              </a>
            </li>
          )}
        </ul>
      )}
    </Dropdown>
  )
}
