import { useCallback, useEffect, useMemo, useRef, useState } from "react"

import { findPreviewUrl } from "~/richText/linkPreview"

import { apiFetch } from "../apiFetch"
import type { LinkPreview } from "../types"

const PREVIEW_DEBOUNCE_MS = 500

interface UnfurlResponse {
  link_preview: LinkPreview | null
}

/**
 * Watches draft content for URLs and debounces link preview unfurl requests.
 * Returns the current preview, a dismiss callback, and whether the preview
 * was dismissed (for skip_link_preview on send).
 */
export function useLinkPreviewUnfurl(draftContent: string) {
  const [fetchedPreview, setFetchedPreview] = useState<LinkPreview | null>(null)
  const [dismissedUrl, setDismissedUrl] = useState<string | null>(null)
  const previewAbortRef = useRef<AbortController | null>(null)
  const previewTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const lastFetchedUrlRef = useRef<string | null>(null)

  // Memoized: the consumer re-renders on unrelated state (e.g. each title
  // keystroke), and the extraction regex-scans the whole draft.
  const currentUrl = useMemo(() => findPreviewUrl(draftContent), [draftContent])
  const dismissed = currentUrl !== null && dismissedUrl === currentUrl
  // Gate on URL identity: fetchedPreview lingers across URL edits, so without
  // the check, typing URL B after URL A flashes A's card while B unfurls.
  // Same-URL re-typing still re-shows the cached preview instantly.
  const composePreview = currentUrl && !dismissed && fetchedPreview?.url === currentUrl ? fetchedPreview : null

  useEffect(() => {
    if (!currentUrl) {
      lastFetchedUrlRef.current = null
      return
    }

    if (currentUrl === lastFetchedUrlRef.current) return

    previewAbortRef.current?.abort()
    if (previewTimerRef.current) clearTimeout(previewTimerRef.current)
    lastFetchedUrlRef.current = currentUrl

    previewTimerRef.current = setTimeout(() => {
      const controller = new AbortController()
      previewAbortRef.current = controller

      apiFetch<UnfurlResponse>("/api/link_previews/unfurl", {
        method: "POST",
        body: JSON.stringify({ url: currentUrl }),
        signal: controller.signal,
      })
        .then(resp => setFetchedPreview(resp.link_preview))
        .catch(e => {
          if (e instanceof DOMException && e.name === "AbortError") return
          setFetchedPreview(null)
        })
    }, PREVIEW_DEBOUNCE_MS)

    return () => {
      if (previewTimerRef.current) clearTimeout(previewTimerRef.current)
      previewAbortRef.current?.abort()
    }
  }, [currentUrl])

  const dismissComposePreview = useCallback(() => {
    setDismissedUrl(currentUrl)
    setFetchedPreview(null)
  }, [currentUrl])

  // Clear dismissal + cached preview so a composer that persists across submits
  // can start its next draft clean (a dismissal shouldn't outlive the send).
  const reset = useCallback(() => {
    setDismissedUrl(null)
    setFetchedPreview(null)
  }, [])

  // Exact submit-time check: `dismissed` derives from the debounced draft
  // content, which can lag the editor by an onChange debounce. Callers that
  // serialize fresh content at submit should map their unfurl flag through
  // this instead, so a submit landing inside that window can't mis-flag.
  const isUrlDismissed = useCallback(
    (content: string) => {
      const url = findPreviewUrl(content)
      return url !== null && url === dismissedUrl
    },
    [dismissedUrl]
  )

  return { composePreview, dismissComposePreview, dismissed, isUrlDismissed, reset }
}
