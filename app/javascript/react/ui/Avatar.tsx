import { useState } from "react"

export type AvatarSize = "xs" | "small" | "medium" | "large"

// Border variant for grouped avatars. All non-"none" variants reserve the same
// 3px box as the active (info-content) presence ring, so avatars stay the same
// size whether or not they're active. "ring" draws a visible base-200 ring that
// overlapping stacked avatars rely on to read as distinct; "spacer" keeps the box
// but makes the border transparent — for compact groups that draw their own
// wrapper ring and want a visible ring only on present (active) users.
export type AvatarBorder = "none" | "ring" | "spacer"

interface AvatarProps {
  displayName: string
  picture: string | null
  size?: AvatarSize
  isActive?: boolean
  border?: AvatarBorder
}

const SIZE_CLASSES: Record<AvatarSize, string> = {
  xs: "w-4 h-4 text-xs",
  small: "w-5 h-5 text-sm",
  medium: "w-6 h-6 text-base",
  large: "w-8 h-8 text-xl",
}

// Always render the <img> and hide it on error rather than removing from the
// DOM. This allows browser-cached images to display on re-mount after navigation,
// even if the initial load was blocked (e.g., ORB on Google profile picture CDN).
export function Avatar({ displayName, picture, size = "small", isActive = false, border = "none" }: AvatarProps) {
  const sizeClass = SIZE_CLASSES[size]
  const [imgFailed, setImgFailed] = useState(false)
  const [renderedPicture, setRenderedPicture] = useState(picture)
  if (picture !== renderedPicture) {
    setRenderedPicture(picture)
    setImgFailed(false)
  }
  const showImage = picture && !imgFailed
  const borderClass = isActive
    ? "border-3 border-info-content"
    : border === "spacer"
      ? "border-3 border-transparent"
      : border === "ring"
        ? "border-3 border-base-200"
        : ""

  return (
    <div className={`avatar block rounded-full static ${showImage ? "" : "avatar-placeholder"} ${borderClass}`}>
      <div className={`${sizeClass} rounded-full bg-neutral-300 text-neutral-600`}>
        {picture && (
          <img
            key={picture}
            src={picture}
            alt={displayName}
            style={showImage ? undefined : { display: "none" }}
            onError={() => setImgFailed(true)}
          />
        )}
        {!showImage && (
          <span className="uppercase" title={displayName}>
            {displayName.charAt(0)}
          </span>
        )}
      </div>
    </div>
  )
}
