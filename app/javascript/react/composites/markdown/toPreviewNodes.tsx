import type { ReactNode } from "react"

import type { Segment } from "./segments"
import { markdownToSegments } from "./segments"

// Collapse whitespace to a single line and trim the outer edges, leaving single
// spaces around inline mentions intact.
function collapse(segments: Segment[]): Segment[] {
  const collapsed = segments.map(segment =>
    segment.isMention ? segment : { ...segment, value: segment.value.replace(/\s+/g, " ") }
  )
  const first = collapsed[0]
  if (first && !first.isMention) first.value = first.value.replace(/^ /, "")
  const last = collapsed[collapsed.length - 1]
  if (last && !last.isMention) last.value = last.value.replace(/ $/, "")
  return collapsed.filter(segment => segment.isMention || segment.value !== "")
}

interface PreviewOptions {
  // Class applied to mention spans. Callers mute it to a greyscale tone for read
  // entries so the mention stops popping. Defaults to the active info color.
  mentionClassName?: string
}

export function markdownToPreviewNodes(source: string, options?: PreviewOptions): ReactNode[] {
  if (!source) return []
  const mentionClassName = options?.mentionClassName ?? "text-info-content"
  return collapse(markdownToSegments(source)).map((segment, index) =>
    // Mention spans match the markup rendered by Markdown.tsx. `value` is already `@Name`.
    segment.isMention ? (
      <span key={index} className={mentionClassName}>
        {segment.value}
      </span>
    ) : (
      segment.value
    )
  )
}
