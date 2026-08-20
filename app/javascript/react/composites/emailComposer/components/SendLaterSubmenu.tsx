import { useState } from "react"

import { DateTimePicker } from "~/react/ui/DateTimePicker"

import { isDayDisabled, isSchedulableAt, sendLaterValidationMessage } from "./sendLaterSchedule"

interface SendLaterSubmenuProps {
  timezone: string | null
  onSelect: (scheduledForIso: string) => void
}

// Schedules a draft by revealing the shared DateTimePicker behind an inline disclosure.
// (The parallel snooze picker takes over its whole popover rather than disclosing
// inline — see SnoozeDropdown.) The 30-day scheduling horizon lives in sendLaterSchedule.
export function SendLaterSubmenu({ timezone, onSelect }: SendLaterSubmenuProps) {
  const [open, setOpen] = useState(false)

  return (
    <>
      <button
        type="button"
        className="dropdown-item flex items-center justify-between w-full"
        onClick={() => setOpen(o => !o)}
      >
        <span className="flex items-center gap-2">
          <span className="material-symbols-outlined text-lg">schedule_send</span>
          Send later
        </span>
        <span className={`material-symbols-outlined text-base ${open ? "rotate-180" : ""}`}>expand_more</span>
      </button>
      {open && (
        <DateTimePicker
          timezone={timezone}
          isDayDisabled={(dayIso, nowMs) => isDayDisabled(dayIso, nowMs, timezone)}
          isConfirmable={isSchedulableAt}
          validationMessage={sendLaterValidationMessage}
          confirmLabel="Schedule"
          onConfirm={onSelect}
        />
      )}
    </>
  )
}
