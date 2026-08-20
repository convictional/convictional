import { useCurrentUser } from "~/react/shared/hooks/useCurrentUser"
import { Dropdown } from "~/react/ui/Dropdown"

import type { SnoozePreset } from "../types"
import { SendLaterSubmenu } from "./SendLaterSubmenu"
import { SnoozeSubmenu } from "./SnoozeSubmenu"

interface SendMenuProps {
  canSend: boolean
  sending: boolean
  cannotSendReason: string
  defaultSnoozeTimes: SnoozePreset[]
  onSend: (options: { archive?: boolean; snooze?: boolean; snoozedUntil?: string }) => void
  onSchedule: (scheduledFor: string) => void
}

export function SendMenu({
  canSend,
  sending,
  cannotSendReason,
  defaultSnoozeTimes,
  onSend,
  onSchedule,
}: SendMenuProps) {
  const { user } = useCurrentUser()
  // UI-only launch gate: scheduling is hidden until release. The endpoints stay
  // open; nothing else surfaces them.
  const canSchedule = user?.is_superuser ?? false
  const disabled = !canSend || sending
  const buttonClass = disabled ? "btn-disabled" : "btn-primary"

  return (
    <div className="relative" title={cannotSendReason || undefined}>
      {/* Round the outer corners explicitly instead of via join's :last-child:
          floating-ui inserts a focus-guard span as the join's last child while
          the dropdown is open, which would strip the caret's pill corners. */}
      <div className="join">
        <button
          type="button"
          data-testid="send-and-archive"
          className={`btn join-item !rounded-l-full ${buttonClass}`}
          disabled={disabled}
          onClick={() => onSend({ archive: true })}
        >
          <span className="material-symbols-outlined text-base">send</span>
          Send and archive
        </button>
        <Dropdown
          placement="bottom-end"
          className="dropdown-card p-2 w-56 z-40"
          ariaLabel="More send options"
          trigger={
            <button
              type="button"
              className={`btn join-item !rounded-r-full ${buttonClass}`}
              disabled={disabled}
              aria-label="More send options"
            >
              <span className="material-symbols-outlined text-lg">arrow_drop_down</span>
            </button>
          }
        >
          {({ close }) => (
            <ul>
              <li>
                <button
                  type="button"
                  className="dropdown-item flex items-center gap-2 w-full"
                  onClick={() => {
                    close()
                    onSend({})
                  }}
                >
                  <span className="material-symbols-outlined text-lg">send</span>
                  Send
                </button>
              </li>
              <li>
                <SnoozeSubmenu
                  presets={defaultSnoozeTimes}
                  onSelect={snoozedUntil => {
                    close()
                    onSend({ snooze: true, snoozedUntil })
                  }}
                />
              </li>
              {canSchedule && (
                <li>
                  <SendLaterSubmenu
                    timezone={user?.time_zone ?? null}
                    onSelect={scheduledFor => {
                      close()
                      onSchedule(scheduledFor)
                    }}
                  />
                </li>
              )}
            </ul>
          )}
        </Dropdown>
      </div>
    </div>
  )
}
