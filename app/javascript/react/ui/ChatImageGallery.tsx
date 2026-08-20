import { useState } from "react"

import { ChatImage } from "./ChatImage"
import { attachmentKey, useCollapsedImage } from "./hooks/useCollapsedImage"
import { CollapseButton, CollapsedImageChip } from "./imageCollapse"
import { Lightbox } from "./Lightbox"

interface ChatImageGalleryProps {
  images: { src: string; alt: string }[]
}

export function ChatImageGallery({ images }: ChatImageGalleryProps) {
  const [openIndex, setOpenIndex] = useState<number | null>(null)
  const [collapsed, toggleCollapsed] = useCollapsedImage(images.map(image => attachmentKey(image.src)).join(","))

  if (images.length === 0) return null
  if (images.length === 1) return <ChatImage src={images[0].src} alt={images[0].alt} />

  if (collapsed) {
    return <CollapsedImageChip label={`${images.length} images`} onExpand={toggleCollapsed} />
  }

  // Show the first three normally; the 4th tile carries a +N overlay when
  // there are more than 4 images and opens the lightbox starting at index 3.
  const visible = images.slice(0, 4)
  const overflow = images.length - 4
  const showOverlay = overflow > 0

  // Two images sit side-by-side as portrait tiles; three use a tall left tile
  // with two stacked tiles on the right; four+ keep the 2x2 grid.
  const rowsClass = images.length === 2 ? "grid-rows-1" : "grid-rows-2"

  return (
    <>
      <div
        className={`group relative grid grid-cols-2 ${rowsClass} gap-1 w-[min(50vh,160px)] h-[min(50vh,160px)] my-2 not-prose`}
      >
        {visible.map((image, i) => {
          const isOverlay = showOverlay && i === 3
          const spanLeftTile = images.length === 3 && i === 0
          return (
            <button
              key={i}
              type="button"
              onClick={() => setOpenIndex(i)}
              aria-label={isOverlay ? `View all ${images.length} images` : `View image ${i + 1} of ${images.length}`}
              className={`group relative block cursor-zoom-in overflow-hidden rounded ${spanLeftTile ? "row-span-2" : ""}`}
            >
              <img
                src={image.src}
                alt={image.alt}
                loading="lazy"
                className="w-full h-full object-cover block transition-transform duration-200 group-hover:scale-105"
              />
              {isOverlay && (
                <div className="absolute inset-0 bg-black/55 group-hover:bg-black/65 transition-colors flex items-center justify-center text-white text-lg font-semibold">
                  +{overflow}
                </div>
              )}
            </button>
          )
        })}
        <div className="absolute top-1.5 right-1.5 px-1.5 py-0.5 rounded-md bg-black/65 text-white text-[10px] font-medium leading-none flex items-center gap-1 pointer-events-none">
          <PhotoStackIcon />
          {images.length}
        </div>
        <CollapseButton onCollapse={toggleCollapsed} className="top-1.5 left-1.5" />
      </div>
      {/* key remounts Lightbox each open so initialIndex takes effect — see Lightbox.tsx */}
      <Lightbox
        key={openIndex ?? "closed"}
        images={images}
        initialIndex={openIndex ?? 0}
        isOpen={openIndex !== null}
        onClose={() => setOpenIndex(null)}
      />
    </>
  )
}

function PhotoStackIcon() {
  return (
    <svg
      width="10"
      height="10"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <rect x="4" y="4" width="9" height="9" rx="1.5" />
      <path d="M2.5 6v6.5A1.5 1.5 0 0 0 4 14h6.5" />
    </svg>
  )
}
