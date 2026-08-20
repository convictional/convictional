import { Dialog } from "~/react/ui/Dialog"

interface HelpDialogProps {
  open: boolean
  onClose: () => void
}

interface ShortcutGroup {
  title: string
  shortcuts: ReadonlyArray<readonly [string, string]>
}

const SHORTCUT_GROUPS: ReadonlyArray<ShortcutGroup> = [
  {
    title: "Thread",
    shortcuts: [
      ["Reply", "r"],
      ["Reply all", "a"],
      ["Forward", "f"],
      ["Archive", "e"],
      ["Snooze", "b"],
      ["Return to inbox", "u"],
      ["Show shortcuts", "?"],
    ],
  },
  {
    title: "Comments",
    shortcuts: [
      ["Send comment", "Enter"],
      ["Edit your last comment", "↑"],
      ["Cancel editing", "Esc"],
    ],
  },
]

// Keyboard shortcuts dialog. Triggered by Shift+? via useEmailThreadHotkeys.
export function HelpDialog({ open, onClose }: HelpDialogProps) {
  if (!open) return null
  return (
    <Dialog isOpen={open} onClose={onClose} className="bg-base-100 rounded-lg max-w-md w-full p-6 shadow-xl">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold">Keyboard Shortcuts</h3>
        <button type="button" onClick={onClose} className="btn btn-sm btn-circle btn-ghost" aria-label="Close">
          <span className="material-symbols-outlined">close</span>
        </button>
      </div>
      <div className="space-y-4 text-sm">
        {SHORTCUT_GROUPS.map(group => (
          <div key={group.title} className="space-y-2">
            <h4 className="text-xs font-semibold uppercase tracking-wide text-base-content/60">{group.title}</h4>
            {group.shortcuts.map(([label, key]) => (
              <div key={key} className="flex justify-between">
                <span>{label}</span>
                <kbd className="kbd kbd-sm">{key}</kbd>
              </div>
            ))}
          </div>
        ))}
      </div>
    </Dialog>
  )
}
