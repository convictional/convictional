import { CONTENT_TYPE_ICONS, CONTENT_TYPE_ICON_STYLES } from "~/react/shared/contentTypes"

export type ResourceBadgeSize = "small" | "medium" | "large"

// small carries the mt-0.5 that aligns the badge with adjacent text in list rows;
// medium/large are for standalone/centered contexts (e.g. empty states) and skip it.
const SIZE_CLASSES: Record<ResourceBadgeSize, { container: string; icon: string }> = {
  small: { container: "mt-0.5 size-9", icon: "!text-base" },
  medium: { container: "size-12", icon: "!text-2xl" },
  large: { container: "size-16", icon: "!text-4xl" },
}

interface ResourceBadgeProps {
  contentType: string
  // Search result rows tint the badge while the row is keyboard-selected.
  selected?: boolean
  size?: ResourceBadgeSize
}

// The embellished resource icon shared by search results, the command palette,
// and link preview cards: a rounded tile carrying the per-content-type tint +
// texture from CONTENT_TYPE_ICON_STYLES.
export function ResourceBadge({ contentType, selected, size = "small" }: ResourceBadgeProps) {
  const style = CONTENT_TYPE_ICON_STYLES[contentType]
  const icon = CONTENT_TYPE_ICONS[contentType] ?? "description"
  const sizeClass = SIZE_CLASSES[size]
  return (
    <span
      className={`shrink-0 ${sizeClass.container} ${style?.badgeClass ?? "rounded-xl"} flex items-center justify-center ${selected ? (style?.bg ?? "") : ""}`}
      style={{
        backgroundColor: style?.bgColor,
        backgroundImage: style?.texture,
        backgroundSize: style?.textureSize,
        ...style?.badgeStyle,
      }}
    >
      <span className={`material-symbols-outlined ${sizeClass.icon} ${style?.text ?? "text-base-500"}`}>{icon}</span>
    </span>
  )
}
