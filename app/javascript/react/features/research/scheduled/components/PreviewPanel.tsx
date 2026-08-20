import DOMPurify from "isomorphic-dompurify"
import { marked } from "marked"
import { useEffect, useMemo, useRef, useState } from "react"

import type { PreviewStatus } from "../hooks/usePreviewStream"

interface Props {
  status: PreviewStatus
  text: string
  errorMessage: string | null
}

// "Within this many pixels of the bottom" — treat the scroll position as pinned to the bottom so a
// user mid-read who briefly drifts doesn't lose their place, but fresh deltas auto-scroll into view.
const STUCK_TO_BOTTOM_THRESHOLD = 20

// Renders the streaming preview inline in a bounded, scrolling container so the submit row above
// doesn't get pushed around as tokens arrive. While streaming, the scroll follows new tokens
// unless the user has scrolled up to read earlier content.
export function PreviewPanel({ status, text, errorMessage }: Props) {
  const html = useMemo(() => {
    if (!text) return ""
    // Preview content is LLM output that pulls from shared workspace sources — prompt injection
    // in those sources could coax the model into emitting executable HTML, so sanitize.
    const rendered = marked.parse(text, { async: false, gfm: true, breaks: true }) as string
    return DOMPurify.sanitize(rendered)
  }, [text])

  const scrollRef = useRef<HTMLDivElement>(null)
  const [stuckToBottom, setStuckToBottom] = useState(true)

  useEffect(() => {
    const el = scrollRef.current
    if (!el || !stuckToBottom) return
    el.scrollTop = el.scrollHeight
  }, [text, stuckToBottom])

  const handleScroll = () => {
    const el = scrollRef.current
    if (!el) return
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight
    setStuckToBottom(distanceFromBottom < STUCK_TO_BOTTOM_THRESHOLD)
  }

  if (status === "idle" && !text) return null

  const showSpinner = status === "initiating" || (status === "streaming" && !text)

  return (
    <div data-testid="scheduled-research-preview">
      <div className="text-[10px] uppercase tracking-wider text-base-content/40 mb-2">Preview</div>
      <div ref={scrollRef} onScroll={handleScroll} className="max-h-[27vh] overflow-y-auto">
        {showSpinner && (
          <div className="flex items-center gap-2 text-xs text-base-content/60">
            <span className="loading loading-spinner loading-xs"></span>
            Generating…
          </div>
        )}
        {text && (
          <div
            className="prose prose-sm max-w-none text-base-content/70 prose-headings:text-sm prose-headings:font-medium prose-headings:text-base-content/80"
            dangerouslySetInnerHTML={{ __html: html }}
          />
        )}
        {status === "error" && errorMessage && (
          <p className="text-xs text-error" data-testid="scheduled-research-preview-error">
            {errorMessage}
          </p>
        )}
      </div>
    </div>
  )
}
