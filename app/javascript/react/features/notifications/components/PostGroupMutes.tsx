import { useState } from "react"
import { Tooltip } from "~/react/ui/Tooltip"
import type { PostGroupMute } from "../types"

interface Props {
  mutes: PostGroupMute[]
  onChange: (groupId: string, muted: boolean) => Promise<void>
}

export function PostGroupMutes({ mutes, onChange }: Props) {
  const mutedCount = mutes.filter(m => m.muted).length
  const [open, setOpen] = useState(mutedCount > 0)

  if (mutes.length === 0) return null

  return (
    <div>
      <button
        type="button"
        className="flex items-center gap-2 text-sm text-base-content/80 hover:text-base-content cursor-pointer"
        onClick={() => setOpen(o => !o)}
        aria-expanded={open}
      >
        <span className="material-symbols-outlined text-base" aria-hidden>
          {open ? "expand_more" : "chevron_right"}
        </span>
        Groups you're in
        {mutedCount > 0 && <span className="text-xs text-base-content/60">({mutedCount} muted)</span>}
        <Tooltip
          content="Stop a group's posts from reaching your inbox."
          placement="top"
          className="inline-flex items-center"
        >
          <span className="material-symbols-outlined text-sm text-base-content/40 leading-none" aria-hidden>
            info
          </span>
        </Tooltip>
      </button>

      {open && (
        <ul className="mt-2 space-y-1">
          {mutes.map(mute => (
            <li
              key={mute.group_id}
              className="grid grid-cols-[1fr_auto] items-center gap-3 py-1.5 px-2 -mx-2 rounded-lg hover:bg-base-200/50 transition-colors"
            >
              <span className="flex items-center gap-2 min-w-0">
                <span className="material-symbols-outlined text-base text-base-content/50 shrink-0" aria-hidden>
                  group
                </span>
                <span className="text-sm truncate" title={mute.group_name}>
                  {mute.group_name}
                </span>
              </span>
              <label className="label cursor-pointer flex items-center gap-2">
                {mute.muted && <span className="text-xs text-base-content/60">Muted</span>}
                <input
                  type="checkbox"
                  className="toggle toggle-sm toggle-primary"
                  checked={!mute.muted}
                  onChange={e => onChange(mute.group_id, !e.target.checked)}
                  aria-label={mute.muted ? `Unmute ${mute.group_name}` : `Mute ${mute.group_name}`}
                />
              </label>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
