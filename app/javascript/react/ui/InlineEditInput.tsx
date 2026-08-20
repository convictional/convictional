import { type KeyboardEvent, forwardRef } from "react"

interface InlineEditInputProps {
  value: string
  maxLength?: number
  onChange: (value: string) => void
  onBlur?: () => void
  onKeyDown?: (e: KeyboardEvent<HTMLInputElement>) => void
  className?: string
}

export const InlineEditInput = forwardRef<HTMLInputElement, InlineEditInputProps>(function InlineEditInput(
  { value, maxLength, onChange, onBlur, onKeyDown, className = "" },
  ref
) {
  return (
    <span className="relative inline-block min-w-[2ch] w-full">
      {/* Mirror span sizes the wrapper to natural text width */}
      <span className={`invisible whitespace-pre ${className}`} aria-hidden="true">
        {value || " "}
      </span>
      <input
        ref={ref}
        value={value}
        maxLength={maxLength}
        onChange={e => onChange(e.target.value)}
        onBlur={onBlur}
        onKeyDown={onKeyDown}
        className={`absolute inset-0 w-full bg-transparent outline-none border-0 p-0 ${className}`}
      />
    </span>
  )
})
