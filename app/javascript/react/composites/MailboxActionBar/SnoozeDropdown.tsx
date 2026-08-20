import { useEffect, useMemo, useRef, useState } from "react"

import { useIsMobile } from "~/react/shared/hooks/useIsMobile"
import { BottomSheet } from "~/react/ui/BottomSheet"
import { DateTimePicker } from "~/react/ui/DateTimePicker"
import { Dropdown } from "~/react/ui/Dropdown"
import { Tooltip } from "~/react/ui/Tooltip"

import { isSnoozeableAt, isSnoozeDayDisabled, snoozeValidationMessage } from "./snoozeSchedule"

interface SnoozePreset {
  value: string
  description: string
}

// Mirrors app/helpers/datetimes.py:default_snooze_times — three relative-to-now
// presets that don't depend on server-side i18n. Computed each time the popover
// opens so "Tomorrow morning" stays correct around midnight.
function buildSnoozePresets(now: Date = new Date()): SnoozePreset[] {
  const twoHours = new Date(now.getTime() + 2 * 60 * 60 * 1000)

  const tomorrowMorning = new Date(now)
  tomorrowMorning.setDate(tomorrowMorning.getDate() + 1)
  tomorrowMorning.setHours(9, 0, 0, 0)

  const nextWeek = new Date(now)
  // Match Python: replace day with (today + (7 - weekday)). JS Date.getDay() is
  // 0=Sun, but Python's weekday() is 0=Mon — adjust so Monday is base.
  const pyWeekday = (now.getDay() + 6) % 7
  nextWeek.setDate(nextWeek.getDate() + (7 - pyWeekday))
  nextWeek.setHours(9, 0, 0, 0)

  return [
    { value: twoHours.toISOString(), description: "Two hours from now" },
    { value: tomorrowMorning.toISOString(), description: "Tomorrow morning (9am)" },
    { value: nextWeek.toISOString(), description: "Next week (Monday 9am)" },
  ]
}

interface SnoozeDropdownProps {
  isOpen: boolean
  onOpenChange: (open: boolean) => void
  onSnooze: (snoozedUntil: string) => Promise<void> | void
  // The user's configured timezone. Interprets the custom picker's wall-clock date/time
  // and anchors its "today"; browser-local when null.
  timezone: string | null
  buttonClassName?: string
  // The inbox renders one SnoozeDropdown per row inside hidden hover containers,
  // so it routes "b" through a single MailboxIndex-level trigger instead.
  withHotkey?: boolean
}

export function SnoozeDropdown({
  isOpen,
  onOpenChange,
  onSnooze,
  timezone,
  buttonClassName = "btn btn-square",
  withHotkey = true,
}: SnoozeDropdownProps) {
  const isMobile = useIsMobile()
  const presets = useMemo(() => (isOpen ? buildSnoozePresets() : []), [isOpen])

  // The custom picker isn't shown inline beside the presets; a "Custom"
  // option swaps the whole popover over to it, with a back affordance
  // returning to the preset list. Reset to the list whenever the popover closes
  // so it always reopens on the presets.
  const [view, setView] = useState<"list" | "custom">("list")
  useEffect(() => {
    if (!isOpen) setView("list")
  }, [isOpen])

  // Entering the custom view unmounts the "Custom" trigger the click landed on;
  // move focus to the back button so keyboard users keep their place and Escape
  // still dismisses through the focus manager.
  const backButtonRef = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    if (view === "custom") backButtonRef.current?.focus()
  }, [view])

  const select = (value: string) => {
    onSnooze(value)
    onOpenChange(false)
  }

  // Parent-page hotkey handlers can preventDefault on Enter while the popover is
  // open, suppressing native button activation. Handle the activation keys
  // ourselves so a keyboard user can pick a preset regardless (desktop dropdown
  // and mobile sheet alike).
  const activateOnKey = (fn: () => void) => (event: React.KeyboardEvent<HTMLButtonElement>) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault()
      fn()
    }
  }

  const backButton = (
    <button
      ref={backButtonRef}
      type="button"
      className="btn btn-ghost btn-sm btn-square"
      aria-label="Back to snooze options"
      onClick={() => setView("list")}
      onKeyDown={activateOnKey(() => setView("list"))}
    >
      <span className="material-symbols-outlined text-lg leading-none">arrow_back</span>
    </button>
  )

  const endSnoozeNote = <li className="text-xs italic text-base-500 p-2">New activity will end snooze</li>

  // On mobile, floating-ui's inline top/left fought the bottom-sheet override
  // classes and stretched the popover into a full-height box. Use the shared
  // BottomSheet instead, matching the assignment picker.
  if (isMobile) {
    return (
      <>
        <button
          type="button"
          className={buttonClassName}
          aria-label="Snooze"
          {...(withHotkey ? { "data-hotkey": "b" } : {})}
          onClick={() => onOpenChange(true)}
        >
          <span className="material-symbols-outlined text-xl text-base-600 hover:text-base-800">snooze</span>
        </button>
        {isOpen && (
          <BottomSheet
            title="Snooze until"
            onClose={() => onOpenChange(false)}
            headerStart={view === "custom" ? backButton : undefined}
          >
            {view === "custom" ? (
              <div className="pb-4">
                <DateTimePicker
                  timezone={timezone}
                  isDayDisabled={(dayIso, nowMs) => isSnoozeDayDisabled(dayIso, nowMs, timezone)}
                  isConfirmable={isSnoozeableAt}
                  validationMessage={snoozeValidationMessage}
                  confirmLabel="Snooze"
                  onConfirm={select}
                />
              </div>
            ) : (
              <ul className="px-2 pb-4">
                {presets.map(preset => (
                  <li key={preset.value}>
                    <button
                      type="button"
                      className="btn btn-ghost pl-2 w-full justify-start"
                      onClick={() => select(preset.value)}
                      onKeyDown={activateOnKey(() => select(preset.value))}
                    >
                      {preset.description}
                    </button>
                  </li>
                ))}
                <li>
                  <button
                    type="button"
                    className="btn btn-ghost pl-2 w-full justify-start"
                    onClick={() => setView("custom")}
                    onKeyDown={activateOnKey(() => setView("custom"))}
                  >
                    Custom…
                  </button>
                </li>
                {endSnoozeNote}
              </ul>
            )}
          </BottomSheet>
        )}
      </>
    )
  }

  return (
    <Dropdown
      open={isOpen}
      onOpenChange={onOpenChange}
      placement="bottom-start"
      // Arrow-key list navigation only applies to the preset list; the custom
      // view drives its own calendar/time focus and would otherwise trip over
      // the now-unmounted preset item refs.
      listNavigation={view === "list"}
      ariaLabel="Snooze until"
      className="dropdown-card p-2 z-50"
      trigger={({ ref, ...refProps }) => (
        <Tooltip content={isOpen ? null : "Snooze"} placement="bottom">
          <button
            ref={ref as React.Ref<HTMLButtonElement>}
            type="button"
            className={buttonClassName}
            aria-label="Snooze"
            {...(withHotkey ? { "data-hotkey": "b" } : {})}
            {...refProps}
          >
            <span className="material-symbols-outlined text-xl text-base-600 hover:text-base-800">snooze</span>
          </button>
        </Tooltip>
      )}
    >
      {({ list }) =>
        view === "custom" ? (
          <div>
            <div className="flex items-center gap-1 px-1 pb-1">
              {backButton}
              <span className="text-sm text-base-500">Snooze until</span>
            </div>
            <DateTimePicker
              timezone={timezone}
              isDayDisabled={(dayIso, nowMs) => isSnoozeDayDisabled(dayIso, nowMs, timezone)}
              isConfirmable={isSnoozeableAt}
              validationMessage={snoozeValidationMessage}
              confirmLabel="Snooze"
              onConfirm={select}
            />
          </div>
        ) : (
          <ul>
            <li className="text-sm text-base-500 px-2">Snooze until</li>
            {presets.map((preset, index) => (
              <li key={preset.value}>
                <button
                  ref={list?.setItemRef(index)}
                  type="button"
                  role="menuitem"
                  tabIndex={list?.activeIndex === index ? 0 : -1}
                  className="btn btn-ghost btn-sm w-full justify-start"
                  {...list?.getItemProps({
                    onClick: () => select(preset.value),
                    onKeyDown: activateOnKey(() => select(preset.value)),
                  })}
                >
                  {preset.description}
                </button>
              </li>
            ))}
            <li role="separator" className="my-1 border-t border-base-300" />
            <li>
              <button
                ref={list?.setItemRef(presets.length)}
                type="button"
                role="menuitem"
                tabIndex={list?.activeIndex === presets.length ? 0 : -1}
                className="btn btn-ghost btn-sm w-full justify-start"
                {...list?.getItemProps({
                  onClick: () => setView("custom"),
                  onKeyDown: activateOnKey(() => setView("custom")),
                })}
              >
                <span className="material-symbols-outlined text-lg leading-none">calendar_month</span>
                Custom…
              </button>
            </li>
            {endSnoozeNote}
          </ul>
        )
      }
    </Dropdown>
  )
}
