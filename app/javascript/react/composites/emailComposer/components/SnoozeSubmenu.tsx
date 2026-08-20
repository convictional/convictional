import { useEffect, useState } from "react"

import type { SnoozePreset } from "../types"

interface SnoozeSubmenuProps {
  presets: SnoozePreset[]
  onSelect: (snoozedUntil: string) => void
}

interface SnoozePresetButtonProps {
  preset: SnoozePreset
  onSelect: (snoozedUntil: string) => void
}

// Presets render from server-computed timestamps. If the page sits open past a
// preset's value the option must disable proactively — checking on each render
// is "impure," so we read Date.now() in an effect and re-render once per minute.
function SnoozePresetButton({ preset, onSelect }: SnoozePresetButtonProps) {
  const [isPast, setIsPast] = useState(false)
  useEffect(() => {
    const target = new Date(preset.value).getTime()
    const update = () => setIsPast(Date.now() >= target)
    update()
    const interval = window.setInterval(update, 60_000)
    return () => window.clearInterval(interval)
  }, [preset.value])

  return (
    <li>
      <button
        type="button"
        className="dropdown-item w-full text-left"
        disabled={isPast}
        onClick={() => onSelect(preset.value)}
      >
        {preset.description}
      </button>
    </li>
  )
}

export function SnoozeSubmenu({ presets, onSelect }: SnoozeSubmenuProps) {
  const [open, setOpen] = useState(false)

  return (
    <>
      <button
        type="button"
        className="dropdown-item flex items-center justify-between w-full"
        onClick={() => setOpen(o => !o)}
      >
        <span className="flex items-center gap-2">
          <span className="material-symbols-outlined text-lg">snooze</span>
          Send and snooze
        </span>
        <span className={`material-symbols-outlined text-base ${open ? "rotate-180" : ""}`}>expand_more</span>
      </button>
      {open && (
        <ul className="pl-2">
          {presets.map(preset => (
            <SnoozePresetButton key={preset.value} preset={preset} onSelect={onSelect} />
          ))}
        </ul>
      )}
    </>
  )
}
