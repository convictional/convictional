// pointer-events-none so the overlay doesn't swallow the drop event itself —
// the underlying container's drop handler still fires.
//
// The backdrop is absolute (scoped to the wrapper) so the dim/blur visually
// anchors to the drop region, and by default the "Drop to upload" chip is
// centered within that same wrapper, keeping the whole treatment localized to
// the input.
//
// `centerOnScreen` centers the chip in the viewport instead. The tall chat
// surfaces use it: centering inside a wrapper sized to the full chat height
// would push the chip off-screen on long chats.
//
// `compact` shrinks the chip for short, single-line inputs (a reply bar, an
// email comment) where the default chip nearly fills the input's height.
export function DropzoneOverlay({
  centerOnScreen = false,
  compact = false,
}: {
  centerOnScreen?: boolean
  compact?: boolean
}) {
  return (
    <>
      <div className="pointer-events-none absolute inset-0 z-30 rounded-xl bg-base-100/30 backdrop-blur-[2px]" />
      <div
        className={`pointer-events-none ${centerOnScreen ? "fixed" : "absolute"} inset-0 z-30 flex items-center justify-center`}
      >
        <div
          className={`flex items-center rounded-full bg-primary text-primary-content font-medium shadow-lg shadow-primary/20 ${
            compact ? "gap-1 px-2.5 py-0.5 text-xs" : "gap-2 px-3.5 py-1.5 text-sm"
          }`}
        >
          <span className={`material-symbols-outlined leading-none ${compact ? "text-sm" : "text-base"}`}>
            cloud_upload
          </span>
          Drop to upload
        </div>
      </div>
    </>
  )
}
