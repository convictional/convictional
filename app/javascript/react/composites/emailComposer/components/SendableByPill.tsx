import { useIsMobile } from "~/react/shared/hooks/useIsMobile"
import { Dropdown } from "~/react/ui/Dropdown"

interface SendableByPillProps {
  isShared: boolean
  sendableBy: string
}

export function SendableByPill({ isShared, sendableBy }: SendableByPillProps) {
  const isMobile = useIsMobile()

  return (
    <div
      id="draft-sendable-by-pill"
      className="ml-3 -mt-3 dropdown-card rounded-lg bg-base-200 flex items-center gap-2 px-2 py-1 shadow-sm border-t-0"
    >
      {isShared ? (
        <>
          <span className="text-xs text-base-600/70 font-semibold">Shared draft</span>
          {/* On mobile the full inline label overflows the viewport (w-max), so
              collapse the extra metadata behind a tappable info popover. */}
          {isMobile ? (
            <Dropdown
              placement="bottom-start"
              ariaLabel="Draft sharing details"
              trigger={
                <button
                  type="button"
                  aria-label="Show draft sharing details"
                  className="flex items-center text-base-600/70"
                >
                  <span className="material-symbols-outlined text-sm">info</span>
                </button>
              }
            >
              <div className="flex flex-col gap-1 px-2 py-1">
                <span className="text-xs text-base-600/70">{sendableBy}</span>
                <span className="text-xs text-base-600/70">Editable by collaborators</span>
              </div>
            </Dropdown>
          ) : (
            <>
              <div className="h-1 w-1 bg-base-500 rounded-full" />
              <span className="text-xs text-base-600/70">{sendableBy}</span>
              <div className="h-1 w-1 bg-base-500 rounded-full" />
              <span className="text-xs text-base-600/70">Editable by collaborators</span>
            </>
          )}
        </>
      ) : (
        <span className="text-xs text-base-600/70 font-semibold">Draft</span>
      )}
    </div>
  )
}
