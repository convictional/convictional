import { Tooltip } from "~/react/ui/Tooltip"

interface ToolButtonProps {
  icon: string
  title: string
  active?: boolean
  disabled?: boolean
  size?: "sm"
  className?: string
  onMouseDown: () => void
}

export function ToolButton({ icon, title, active, disabled, size, className, onMouseDown }: ToolButtonProps) {
  const sizeClass = size === "sm" ? "btn-sm" : ""
  return (
    <Tooltip content={title}>
      <button
        type="button"
        aria-label={title}
        className={`btn btn-square ${sizeClass} ${active ? "text-info-content" : ""} ${disabled ? "text-neutral/40" : ""} ${className || ""}`}
        tabIndex={-1}
        disabled={disabled}
        onMouseDown={e => {
          e.preventDefault()
          onMouseDown()
        }}
      >
        <span className="material-symbols-outlined !text-lg">{icon}</span>
      </button>
    </Tooltip>
  )
}
