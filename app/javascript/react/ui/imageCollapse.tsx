import { Tooltip } from "./Tooltip"

// Shared collapse affordances for inline chat images: a hover overlay button to
// hide the image, and the compact chip shown in place of a collapsed image/gallery.

interface CollapseButtonProps {
  onCollapse: () => void
  className?: string
}

export function CollapseButton({ onCollapse, className = "" }: CollapseButtonProps) {
  return (
    <Tooltip
      content="Hide image"
      className={`absolute z-10 opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity ${className}`}
    >
      <button
        type="button"
        aria-label="Hide image"
        onClick={e => {
          e.stopPropagation()
          onCollapse()
        }}
        className="flex items-center justify-center rounded bg-black/55 hover:bg-black/70 text-white p-0.5"
      >
        <span className="material-symbols-outlined text-base">visibility_off</span>
      </button>
    </Tooltip>
  )
}

interface CollapsedImageChipProps {
  label: string
  onExpand: () => void
}

export function CollapsedImageChip({ label, onExpand }: CollapsedImageChipProps) {
  return (
    <button
      type="button"
      onClick={onExpand}
      className="inline-flex items-center gap-1.5 my-2 px-2 py-1 rounded border border-base-300 text-sm text-base-content/70 hover:bg-base-200 not-prose"
    >
      <span className="material-symbols-outlined text-base">image</span>
      {label}
      <span className="text-base-content/50">· Show</span>
    </button>
  )
}
