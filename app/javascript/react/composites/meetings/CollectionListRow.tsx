import { Tooltip } from "~/react/ui/Tooltip"
import { pluralize } from "~/shared/strings"

interface CollectionListRowProps {
  href: string
  icon: string
  title: string
  // Meeting count badge; omitted or 0 renders nothing.
  count?: number
}

// A single row inside the joined collections card. Borders and rounding come
// from the parent card (divide-y), so the row itself is just a padded flex link.
export function CollectionListRow({ href, icon, title, count }: CollectionListRowProps) {
  return (
    <a
      href={href}
      className="px-4 py-3 bg-base-50 hover:bg-base-200 flex items-center gap-3 justify-between transition-colors w-full"
    >
      <div className="flex items-center gap-3 truncate min-w-0">
        <span className="material-symbols-outlined text-xl shrink-0 text-base-content/60">{icon}</span>
        <span className="text-sm font-medium truncate">{title}</span>
      </div>
      {count !== undefined && count > 0 && (
        <Tooltip content={`${count} ${pluralize(count, "meeting", "meetings")} in this collection`} placement="left">
          <span className="shrink-0 px-2 py-0.5 rounded-full bg-base-200 text-xs text-base-content/60">{count}</span>
        </Tooltip>
      )}
    </a>
  )
}
