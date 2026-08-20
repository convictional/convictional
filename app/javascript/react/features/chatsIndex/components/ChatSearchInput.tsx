import type { RefObject } from "react"

import { Avatar } from "~/react/ui/Avatar"
import type { SelectedRecipient } from "../types"

interface ChatSearchInputProps {
  searchQuery: string
  onSearchChange: (query: string) => void
  onKeyDown: (e: React.KeyboardEvent) => void
  composing: boolean
  selectedRecipients: SelectedRecipient[]
  onRemoveRecipient: (id: string) => void
  onFocusChange: (focused: boolean) => void
  inputFocused: boolean
  inputRef: RefObject<HTMLInputElement | null>
  autoFocus: boolean
}

export function ChatSearchInput({
  searchQuery,
  onSearchChange,
  onKeyDown,
  composing,
  selectedRecipients,
  onRemoveRecipient,
  onFocusChange,
  inputFocused,
  inputRef,
  autoFocus,
}: ChatSearchInputProps) {
  return (
    <div className="flex-1 min-w-0">
      <div
        className="relative flex items-center min-h-9 bg-base-50 rounded-full border border-base-300 shadow-xs px-3 py-1 cursor-text"
        onClick={() => inputRef.current?.focus()}
      >
        <div className="flex items-center gap-2 w-full">
          <div className="flex flex-wrap items-center gap-1 flex-1 min-w-0">
            {selectedRecipients.map(recipient => (
              <span
                key={recipient.id}
                className="inline-flex items-center gap-1 bg-base-200 rounded-full pl-1 pr-2 py-0.5 text-sm shrink-0"
              >
                <Avatar displayName={recipient.name} picture={recipient.picture} size="xs" />
                <span className="truncate max-w-[120px]">{recipient.name}</span>
                <button
                  type="button"
                  onClick={e => {
                    e.stopPropagation()
                    onRemoveRecipient(recipient.id)
                  }}
                  className="text-base-400 hover:text-base-600 ml-0.5 leading-none"
                >
                  <span className="material-symbols-outlined text-[14px]">close</span>
                </button>
              </span>
            ))}
            <input
              ref={inputRef}
              value={searchQuery}
              onChange={e => onSearchChange(e.target.value)}
              onKeyDown={onKeyDown}
              onFocus={() => onFocusChange(true)}
              onBlur={() => onFocusChange(false)}
              type="text"
              autoFocus={autoFocus}
              autoComplete="off"
              placeholder={composing ? "Add people..." : "Search..."}
              className="input h-7 flex-1 min-w-[80px] bg-transparent border-0 !rounded-none focus:outline-none px-0 !placeholder:text-base-400"
            />
          </div>
          {/* Hints ride the input row, fading on focus rather than expanding/collapsing the box
              height — a height change here would shift the list down/up and mis-target clicks. */}
          <div
            className={`@mobile:hidden shrink-0 flex items-center gap-3 text-sm text-base-500 transition-opacity duration-200 ${inputFocused ? "opacity-100" : "opacity-0"}`}
          >
            <span>
              <kbd className="kbd kbd-sm">↑↓</kbd> navigate
            </span>
            <span>
              <kbd className="kbd kbd-sm">↵</kbd> {composing ? "add" : "open"}
            </span>
            <span>
              <kbd className="kbd kbd-sm">esc</kbd> {composing ? "exit" : "clear"}
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}
