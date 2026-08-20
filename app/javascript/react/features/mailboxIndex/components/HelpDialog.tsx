import { useEffect, useRef } from "react"

interface HelpDialogProps {
  isOpen: boolean
  onClose: () => void
}

const SHORTCUTS: { label: string; keys: string[] }[] = [
  { label: "Navigate up/down", keys: ["↑/↓"] },
  { label: "Open thread", keys: ["Enter"] },
  { label: "Archive thread", keys: ["e"] },
  { label: "Mark read/unread", keys: ["r"] },
  { label: "Snooze thread", keys: ["b"] },
  { label: "Compose email", keys: ["c"] },
  { label: "Go to Inbox", keys: ["g", "i"] },
  { label: "Go to Unread", keys: ["g", "u"] },
  { label: "Go to Posts", keys: ["g", "p"] },
  { label: "Go to Assigned to me", keys: ["g", "m"] },
  { label: "Go to Sent", keys: ["g", "s"] },
  { label: "Go to Drafts", keys: ["g", "d"] },
  { label: "Go to Archived", keys: ["g", "a"] },
  { label: "Go to Snoozed", keys: ["g", "z"] },
  { label: "Undo last archive or snooze", keys: ["⌘Z"] },
  { label: "Show shortcuts", keys: ["?"] },
]

export function HelpDialog({ isOpen, onClose }: HelpDialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return
    if (isOpen && !dialog.open) dialog.showModal()
    if (!isOpen && dialog.open) dialog.close()
  }, [isOpen])

  return (
    <dialog ref={dialogRef} className="modal" onClose={onClose}>
      <div className="modal-box">
        <div tabIndex={0} className="outline-none">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold">Keyboard Shortcuts</h3>
            <button onClick={onClose} className="btn btn-sm btn-circle btn-ghost" tabIndex={-1}>
              <span className="material-symbols-outlined">close</span>
            </button>
          </div>
          <div className="space-y-2 text-sm">
            {SHORTCUTS.map(s => (
              <div key={s.label} className="flex justify-between">
                <span>{s.label}</span>
                <div className="flex gap-1">
                  {s.keys.map(k => (
                    <kbd key={k} className="kbd kbd-sm">
                      {k}
                    </kbd>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
      <form method="dialog" className="modal-backdrop">
        <button>close</button>
      </form>
    </dialog>
  )
}
