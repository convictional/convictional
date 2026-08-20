import { useEffect, useRef } from "react"

import { iconForCommandType } from "../icons"
import type { Command } from "../types"

interface CommandsModeProps {
  commands: Command[] | null
  filterInput: string
  selectedIndex: number
  onSelect: (index: number) => void
  onActivate: (command: Command) => void
  onEditQuickLink: (command: Command) => void
}

export function filterCommands(commands: Command[], input: string): Command[] {
  const trimmed = input.toLowerCase().trim()
  if (!trimmed) return commands
  return commands.filter(c => c.label.toLowerCase().startsWith(trimmed))
}

interface CommandRowProps {
  command: Command
  isSelected: boolean
  onHover: () => void
  onActivate: () => void
  onEdit?: () => void
}

function CommandRow({ command, isSelected, onHover, onActivate, onEdit }: CommandRowProps) {
  const ref = useRef<HTMLLIElement>(null)

  useEffect(() => {
    if (isSelected) ref.current?.scrollIntoView({ block: "nearest" })
  }, [isSelected])

  const isQuickLink = command.type === "quick_link"
  const description = isQuickLink
    ? command.options?.open_in_new_tab
      ? "Opens your custom link in a new tab"
      : "Opens your custom link in the current window"
    : command.description

  return (
    <li
      ref={ref}
      onMouseOver={onHover}
      className={`p-2 cursor-pointer transition bg-base-50 hover:bg-base-200 ${isSelected ? "bg-base-200" : ""}`}
    >
      <div className="grid grid-cols-[1fr_auto] items-center">
        <button
          type="button"
          onClick={onActivate}
          {...(isSelected ? { "data-palette-active": "true" } : {})}
          className="grid grid-cols-[auto_1fr] gap-2 items-start text-left"
        >
          <div className={`btn btn-square ${isSelected ? "btn-primary" : ""}`}>
            <span className="material-symbols-outlined text-lg">{iconForCommandType(command.type)}</span>
          </div>
          <div className="-mt-0.5">
            <div className={`font-semibold text-sm ${isSelected ? "text-base-800" : "text-base-600"}`}>
              {command.label}
            </div>
            {description && (
              <div className={`text-xs line-clamp-1 ${isSelected ? "text-base-600" : "text-base-500"}`}>
                {description}
              </div>
            )}
          </div>
        </button>
        {isQuickLink && onEdit && (
          <button
            type="button"
            onClick={e => {
              e.stopPropagation()
              onEdit()
            }}
            className={`flex items-center self-end transition-opacity text-base-500 hover:text-base-600 ${
              isSelected ? "opacity-80 text-base-600" : "opacity-0 hover:opacity-100"
            }`}
            aria-label="Edit quick link"
          >
            <span className="material-symbols-outlined text-lg">settings</span>
          </button>
        )}
      </div>
    </li>
  )
}

export function CommandsMode({
  commands,
  filterInput,
  selectedIndex,
  onSelect,
  onActivate,
  onEditQuickLink,
}: CommandsModeProps) {
  if (commands === null) {
    return (
      <div className="p-2 grid gap-3">
        <p className="text-center text-sm text-base-500 py-8">Loading commands…</p>
      </div>
    )
  }

  const filtered = filterCommands(commands, filterInput)

  return (
    <div className="p-2 grid gap-3">
      <p className="text-xs text-base-500 px-4">Commands</p>
      <ul className="divide-y divide-base-300 border border-base-300 rounded-2xl overflow-hidden shadow-xs mx-2">
        {filtered.map((command, index) => (
          <CommandRow
            key={command.key}
            command={command}
            isSelected={selectedIndex === index}
            onHover={() => onSelect(index)}
            onActivate={() => onActivate(command)}
            onEdit={command.type === "quick_link" ? () => onEditQuickLink(command) : undefined}
          />
        ))}
        {filtered.length === 0 && filterInput.trim() !== "" && (
          <li className="p-4 text-center text-base-500">No commands found</li>
        )}
      </ul>
    </div>
  )
}
