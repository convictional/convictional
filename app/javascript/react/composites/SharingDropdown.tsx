import { confirm } from "~/react/composites/confirmationDialog/confirm"
import { apiFetch } from "~/react/shared/apiFetch"
import type { Sharing } from "~/react/shared/types"
import { Dropdown } from "~/react/ui/Dropdown"
import { showFlash } from "~/shared/flash"

export interface SharingOption {
  value: Sharing
  label: string
  description: string
  icon: string
}

export interface SharingConfirmation {
  title?: string
  message: string
  confirmLabel?: string
}

interface SharingDropdownProps<T> {
  // Resource endpoint to PATCH, e.g. `/api/meetings/${id}` or `/api/documents/${id}`.
  patchUrl: string
  sharing: Sharing
  options: SharingOption[]
  triggerIcon: (sharing: Sharing) => string
  triggerIconClassName?: string
  errorMessage?: string
  // Fired with the parsed PATCH response on success — consumers that need the
  // full updated resource (e.g. a meeting) read it here.
  onUpdated?: (response: T) => void
  // Optimistic style: `onOptimisticChange` runs synchronously before the request
  // and `onRevert` restores the previous value if it fails. Consumers that own
  // their own sharing state (e.g. a document) use this pair instead of onUpdated.
  onOptimisticChange?: (next: Sharing) => void
  onRevert?: (previous: Sharing) => void
  // When provided, selecting a different option asks the user to confirm before
  // the change is applied. Return null to skip confirmation for a transition.
  confirmChange?: (next: SharingOption) => SharingConfirmation | null
}

export function SharingDropdown<T = unknown>({
  patchUrl,
  sharing,
  options,
  triggerIcon,
  triggerIconClassName = "text-lg",
  errorMessage,
  onUpdated,
  onOptimisticChange,
  onRevert,
  confirmChange,
}: SharingDropdownProps<T>) {
  const trigger = (
    <button type="button" className="btn btn-square" aria-label="Sharing">
      <span className={`material-symbols-outlined ${triggerIconClassName}`}>{triggerIcon(sharing)}</span>
    </button>
  )

  async function select(next: Sharing, close: () => void) {
    close()
    if (next === sharing) return

    if (confirmChange) {
      const option = options.find(o => o.value === next)
      const confirmation = option ? confirmChange(option) : null
      if (confirmation && !(await confirm(confirmation))) return
    }

    const previous = sharing
    onOptimisticChange?.(next)
    try {
      const response = await apiFetch<T>(patchUrl, {
        method: "PATCH",
        body: JSON.stringify({ sharing: next }),
      })
      onUpdated?.(response)
    } catch {
      onRevert?.(previous)
      showFlash(errorMessage ?? "Could not update sharing. Please try again.", "error")
    }
  }

  return (
    <Dropdown trigger={trigger} placement="bottom-end" ariaLabel="Sharing options">
      {({ close }) => (
        <ul className="p-2 w-56">
          {options.map(option => (
            <li key={option.value}>
              <button
                type="button"
                onClick={() => void select(option.value, close)}
                className="dropdown-item w-full text-left text-sm py-2"
              >
                <div className="flex items-center gap-2">
                  <span className="material-symbols-outlined text-base">{option.icon}</span>
                  <div>
                    <div>{option.label}</div>
                    <div className="text-xs opacity-50">{option.description}</div>
                  </div>
                  {sharing === option.value && (
                    <span className="material-symbols-outlined text-sm ml-auto">check</span>
                  )}
                </div>
              </button>
            </li>
          ))}
        </ul>
      )}
    </Dropdown>
  )
}
