import { Avatar } from "~/react/ui/Avatar"
import type { Contact } from "../types"

interface ContactItemProps {
  contact: Contact
  isSelected: boolean
  isHovered: boolean
  isNavigating: boolean
  navigatingDisabled: boolean
  isRecipient?: boolean
  composing?: boolean
  inputFocused?: boolean
  onSelect: () => void
  onHover: () => void
}

export function ContactItem({
  contact,
  isSelected,
  isHovered,
  isNavigating,
  navigatingDisabled,
  isRecipient = false,
  composing = false,
  inputFocused = false,
  onSelect,
  onHover,
}: ContactItemProps) {
  return (
    <button
      type="button"
      onClick={onSelect}
      onMouseEnter={onHover}
      className={`flex items-center gap-2 pl-2 pr-3 py-1.5 rounded-lg hover:bg-base-200 transition-colors duration-75 text-left cursor-pointer w-full ${
        isHovered ? "bg-base-200" : ""
      } ${navigatingDisabled && !isNavigating ? "opacity-50 pointer-events-none" : ""}`}
    >
      <div className="w-3 flex items-center justify-center shrink-0">
        {isSelected && inputFocused && <div className="w-1.5 h-5 bg-primary rounded-full @mobile:hidden" />}
      </div>
      <div className="shrink-0">
        {contact.type === "group" ? (
          <div className="w-5 h-5 rounded-full bg-base-300 flex items-center justify-center">
            <span className="material-symbols-outlined text-base-content/50 text-[14px]">group</span>
          </div>
        ) : contact.type === "self" ? (
          <div className="w-5 h-5 rounded-full bg-base-300 flex items-center justify-center">
            <span className="material-symbols-outlined text-base-content/50 text-[14px]">edit_note</span>
          </div>
        ) : (
          <Avatar displayName={contact.name} picture={contact.picture} size="small" />
        )}
      </div>
      <div className="flex-1 min-w-0 flex items-center justify-between gap-2">
        <span className="text-sm truncate shrink min-w-0">
          {contact.name}
          {contact.type === "group" && (
            <span className="text-base-500 bg-base-200 rounded-full px-1.5 py-0.5 inline-flex items-center gap-0.5 ml-1 text-[11px]">
              <span className="material-symbols-outlined leading-none text-[12px]">person</span>
              <span className="leading-none">{contact.collaborator_count}</span>
            </span>
          )}
        </span>
        {isRecipient && (
          <span className="material-symbols-outlined text-info-content text-[18px] shrink-0">check_circle</span>
        )}
        {!isRecipient && isNavigating && <span className="loading loading-spinner loading-xs shrink-0" />}
        {!isRecipient && !isNavigating && isSelected && inputFocused && (
          <span className="shrink-0 text-sm text-primary-themed @mobile:hidden">
            <kbd className="kbd kbd-sm kbd-primary">↵</kbd>{" "}
            {composing && contact.type !== "group" && contact.type !== "self" ? "add" : "open"}
          </span>
        )}
      </div>
    </button>
  )
}
