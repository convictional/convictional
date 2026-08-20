import { useState } from "react"

import { attachmentKey, useCollapsedImage } from "./hooks/useCollapsedImage"
import { CollapseButton, CollapsedImageChip } from "./imageCollapse"
import { Lightbox } from "./Lightbox"

interface ChatImageProps {
  src: string
  alt: string
}

export function ChatImage({ src, alt }: ChatImageProps) {
  const [isLightboxOpen, setIsLightboxOpen] = useState(false)
  const [isLoaded, setIsLoaded] = useState(false)
  const [collapsed, toggleCollapsed] = useCollapsedImage(attachmentKey(src))

  if (collapsed) {
    return <CollapsedImageChip label="Image" onExpand={toggleCollapsed} />
  }

  return (
    <>
      <span className="group relative block w-fit my-2 not-prose">
        <button type="button" onClick={() => setIsLightboxOpen(true)} className="block cursor-zoom-in">
          <img
            src={src}
            alt={alt}
            loading="lazy"
            onLoad={() => setIsLoaded(true)}
            className={`block max-h-[min(50vh,160px)] w-auto h-auto object-contain rounded ${
              isLoaded ? "" : "min-h-[min(50vh,160px)]"
            }`}
          />
        </button>
        <CollapseButton onCollapse={toggleCollapsed} className="top-1.5 left-1.5" />
      </span>
      <Lightbox images={[{ src, alt }]} isOpen={isLightboxOpen} onClose={() => setIsLightboxOpen(false)} />
    </>
  )
}
