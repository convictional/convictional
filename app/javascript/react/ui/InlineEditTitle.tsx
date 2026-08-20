import { type KeyboardEvent, forwardRef } from "react"

import { InlineEditInput } from "./InlineEditInput"

interface InlineEditTitleProps {
  displayText: string
  editValue: string
  editing: boolean
  maxLength?: number
  onEditStart: () => void
  onChange: (value: string) => void
  onBlur: () => void
  onKeyDown: (e: KeyboardEvent<HTMLInputElement>) => void
  className?: string
}

export const InlineEditTitle = forwardRef<HTMLInputElement, InlineEditTitleProps>(function InlineEditTitle(
  {
    displayText,
    editValue,
    editing,
    maxLength,
    onEditStart,
    onChange,
    onBlur,
    onKeyDown,
    className = "text-xs font-normal text-base-content/60",
  },
  ref
) {
  return (
    <div className="group/ptitle min-w-0">
      {/* Ring wraps both name and pencil so the hover outline encloses the full editable region */}
      <div
        className={`flex items-center gap-2 -ml-3 px-3 py-1.5 rounded-md ring-1 transition-shadow ${
          editing ? "ring-base-300" : "ring-transparent group-hover/ptitle:ring-base-300"
        }`}
      >
        <div className="flex-1 min-w-0">
          {editing ? (
            <InlineEditInput
              ref={ref}
              value={editValue}
              maxLength={maxLength}
              onChange={onChange}
              onBlur={onBlur}
              onKeyDown={onKeyDown}
              className={className}
            />
          ) : (
            <span className={`truncate block cursor-pointer ${className}`} title={displayText} onClick={onEditStart}>
              {displayText}
            </span>
          )}
        </div>
        {/* Always in layout (opacity-0 not display:none) so the pencil's space is always reserved.
            A pure pointer affordance that duplicates clicking the text — kept out of the tab order
            and the accessibility tree (aria-hidden) so AT users aren't offered a redundant control. */}
        <button
          type="button"
          onClick={editing ? undefined : onEditStart}
          tabIndex={-1}
          aria-hidden="true"
          className={`shrink-0 transition-opacity text-base-content/30 hover:text-base-content/60 ${
            editing ? "invisible" : "opacity-0 group-hover/ptitle:opacity-100 hover:opacity-100"
          }`}
        >
          <span className="material-symbols-outlined" style={{ fontSize: "14px" }}>
            edit
          </span>
        </button>
      </div>
    </div>
  )
})
