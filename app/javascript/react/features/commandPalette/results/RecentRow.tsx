import { ResourceBadge } from "~/react/composites/ResourceBadge"
import { DateTime } from "~/react/ui/DateTime"

import type { RecentItem } from "../types"
import { ResultRow } from "./ResultRow"

interface RecentRowProps {
  visit: RecentItem
  isSelected: boolean
  onHover: () => void
  onActivate: () => void
}

// resource_type → content_type key (only "emailthread" differs from API form)
const CONTENT_TYPE_KEY: Record<string, string> = { emailthread: "email_thread" }

function contentTypeFor(resourceType: string): string {
  const normalized = resourceType.toLowerCase().replace(/[^a-z0-9]/g, "")
  return CONTENT_TYPE_KEY[normalized] ?? normalized
}

export function RecentRow({ visit, isSelected, onHover, onActivate }: RecentRowProps) {
  const collaboratorNames = visit.collaborators.map(c => c.display_name).join(", ")

  const rowDetails = (
    <>
      <p className="text-sm wrap-anywhere line-clamp-1">{visit.title}</p>
      {visit.preview ? (
        <p className="text-xs text-base-500 line-clamp-1 wrap-anywhere">{visit.preview}</p>
      ) : (
        collaboratorNames && <p className="text-xs text-base-500 line-clamp-1 wrap-anywhere">{collaboratorNames}</p>
      )}
      <p className="text-xs text-base-500 wrap-anywhere flex items-center gap-1 flex-wrap">
        <span className="inline-flex items-center gap-0.5">
          <span className="material-symbols-outlined !text-xs">bolt</span>
          <DateTime datetime={visit.updated_at} format="relative" />
        </span>
      </p>
    </>
  )

  return (
    <ResultRow
      href={visit.url}
      onClick={onActivate}
      onHover={onHover}
      isSelected={isSelected}
      icon={<ResourceBadge contentType={contentTypeFor(visit.resource_type)} />}
      rowDetails={rowDetails}
    />
  )
}
