import { useEffect, useRef } from "react"

import { useTheme } from "~/react/shared/hooks/useTheme"
import { bridgeIframeKeydown } from "~/react/shared/iframeKeydownBridge"
import { isRealSrcdocReady } from "~/react/shared/iframeSrcdocSizing"
import { processEmailQuotesInHtml, wrapEmojiInHtml } from "~/shared/emailQuotes"

interface EmailMessageBodyProps {
  contentHtml: string
  isMobile: boolean
  // Convictional-composed mail (SENT/SENDING/DRAFT). Gates the `authored` class that
  // scopes email.css's pre-wrap whitespace rules; inbound RECEIVED mail renders
  // under `white-space: normal` so its pretty-printed inter-tag newlines collapse.
  isAuthored: boolean
}

export function buildSrcdoc(
  content: string,
  theme: "light" | "dark",
  isMobile: boolean,
  cssUrl: string,
  isAuthored: boolean
): string {
  const htmlClass = `${theme} ${isMobile ? "mobile" : "desktop"}${isAuthored ? " authored" : ""}`
  return `<!DOCTYPE html>
<html lang="en" class="${htmlClass}">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="color-scheme" content="${theme}">
    <link rel="stylesheet" href="${cssUrl}">
  </head>
  <body>${content}</body>
</html>`
}

// Sandboxed iframe wrapper for email body HTML. Isolates email-specific CSS
// (email.css) from the app shell, auto-sizes via ResizeObserver, and processes
// quoted blocks + emoji glyphs so dark-mode invert doesn't muddy them.
export function EmailMessageBody({ contentHtml, isMobile, isAuthored }: EmailMessageBodyProps) {
  const { current: theme } = useTheme()
  const containerRef = useRef<HTMLDivElement>(null)
  const iframeRef = useRef<HTMLIFrameElement | null>(null)

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const processed = wrapEmojiInHtml(processEmailQuotesInHtml(contentHtml))
    const cssUrl = window.EMAIL_CSS_URL || ""

    const iframe = document.createElement("iframe")
    iframe.className = "border-0 rounded-md bg-transparent transition-all"
    iframe.style.height = "60px"
    // Mobile Safari / WebView sizes an iframe to its content's intrinsic width and
    // ignores width:100%. width:1px + min-width:100% floors the used width to the
    // container on every platform while keeping the iframe's min-content contribution
    // ~1px, so it can't widen the grid column; wider content scrolls inside the iframe.
    iframe.style.width = "1px"
    iframe.style.minWidth = "100%"
    iframe.style.maxWidth = "100%"
    // allow-same-origin is required so the parent can read iframe.contentDocument
    // for the ResizeObserver-based auto-sizing; without it the iframe stays at
    // its initial height.
    iframe.setAttribute("sandbox", "allow-popups allow-popups-to-escape-sandbox allow-same-origin")
    iframe.srcdoc = buildSrcdoc(processed, theme, isMobile, cssUrl, isAuthored)

    const resizeObservers: ResizeObserver[] = []
    let initialized = false
    let removeKeydownBridge: (() => void) | null = null

    // Size the iframe once the body is parsed and keep it in sync as later layout
    // changes land (images loading, quotes expanding). Idempotent: the rAF poll
    // and the load fallback may both reach it, but only the first run takes effect.
    const initSizing = (body: HTMLElement) => {
      if (initialized) return
      initialized = true
      iframe.style.setProperty("height", `${body.scrollHeight}px`, "important")
      const ro = new ResizeObserver(() => {
        const target = iframe.contentDocument?.body
        if (target) iframe.style.setProperty("height", `${target.scrollHeight}px`, "important")
      })
      ro.observe(body)
      resizeObservers.push(ro)
      removeKeydownBridge = bridgeIframeKeydown(body.ownerDocument, document)
    }

    // Primary trigger: size on parse, not on load. The load event fires only after
    // every subresource resolves (or the browser abandons it), so a slow/hanging
    // tracking pixel could pin the iframe at 60px for ~30s. Poll each frame for the
    // parsed srcdoc body instead. Bounded so a never-parsing document can't spin
    // forever; the load listener below is the ultimate backstop.
    let cancelled = false
    let rafId = 0
    let attempts = 0
    const pollForParsedBody = () => {
      if (cancelled) return
      const doc = iframe.contentDocument
      if (isRealSrcdocReady(doc)) {
        initSizing(doc.body)
        return
      }
      if (++attempts < 60) rafId = requestAnimationFrame(pollForParsedBody)
    }

    // Fallback: load fires against the real document, so it covers the fast path
    // and any parse the poll missed before exhausting its attempts.
    const handleLoad = () => {
      if (cancelled) return
      const doc = iframe.contentDocument
      if (isRealSrcdocReady(doc)) initSizing(doc.body)
    }
    iframe.addEventListener("load", handleLoad)

    container.replaceChildren(iframe)
    iframeRef.current = iframe
    rafId = requestAnimationFrame(pollForParsedBody)

    return () => {
      cancelled = true
      if (rafId) cancelAnimationFrame(rafId)
      resizeObservers.forEach(ro => ro.disconnect())
      removeKeydownBridge?.()
      // Remove the load listener explicitly: its closure captures the iframe and
      // sizing state, so without this the detached iframe subtree is only reclaimed
      // once the browser breaks the collectable cycle, not deterministically on unmount.
      iframe.removeEventListener("load", handleLoad)
      iframe.remove()
      iframeRef.current = null
    }
  }, [contentHtml, isMobile, theme, isAuthored])

  return <div ref={containerRef} data-testid="email-message-body" className="bg-base-50 rounded-r-md" />
}
