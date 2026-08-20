interface JumpToLatestPillProps {
  onClick: () => void
  label: string
  // "down" for the live/scrolled-up "New messages" case; "latest" for the
  // historical-window "Jump to latest" case, which leaves the window entirely.
  variant?: "down" | "latest"
}

// Shared, presentational "jump to bottom" pill for both chat MessageLists. The
// consumer owns visibility, label, click target, and positioning — this renders
// only the button, so wrap it where it should sit.
export function JumpToLatestPill({ onClick, label, variant = "down" }: JumpToLatestPillProps) {
  return (
    <button onClick={onClick} className="btn btn-primary btn-sm rounded-full shadow-lg flex items-center gap-2">
      <span className="material-symbols-outlined text-sm">
        {variant === "latest" ? "vertical_align_bottom" : "keyboard_arrow_down"}
      </span>
      <span>{label}</span>
    </button>
  )
}
