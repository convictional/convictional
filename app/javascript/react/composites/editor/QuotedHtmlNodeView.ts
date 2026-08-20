import type { Node as ProseMirrorNode } from "prosemirror-model"
import type { NodeView } from "prosemirror-view"

import { isRealSrcdocReady } from "~/react/shared/iframeSrcdocSizing"
import { processEmailQuotesInHtml, wrapEmojiInHtml } from "~/shared/emailQuotes"
import { getCurrentTheme, subscribeToTheme } from "~/shared/themeApplicator"

// NodeView for the `quoted_html` atom. The shared schema's `toDOM` returns a
// DOM node, which @handlewithcare/react-prosemirror rejects — it only accepts
// strings/arrays. Registering this NodeView via the nodeViews prop bypasses
// toDOM entirely.
//
// Same UX as the legacy email-content rendering: outer collapsed chip, iframe
// sandbox flags, single-level <details> wrapping for the first .quote_container.
export class QuotedHtmlNodeView implements NodeView {
  dom: HTMLElement
  private resizeObserver: ResizeObserver | null = null
  private iframe: HTMLIFrameElement | null = null
  private htmlContent: string = ""
  private isMobile: boolean = false
  private unsubscribeTheme: (() => void) | null = null
  private sizingInitialized: boolean = false
  // Bumped on every srcdoc (re-)navigation and in destroy() so an in-flight
  // rAF poll from a superseded navigation bails instead of sizing a stale doc.
  private sizingGeneration: number = 0
  private rafId: number = 0

  constructor(node: ProseMirrorNode) {
    const startsCollapsed = Boolean(node.attrs.collapsed)
    this.htmlContent = (node.attrs.htmlContent as string) ?? ""
    this.isMobile = document.documentElement.dataset.isMobile === "true"

    this.dom = document.createElement("div")
    this.dom.setAttribute("data-quoted-html", "true")
    this.dom.contentEditable = "false"

    const toggle = document.createElement("button")
    toggle.type = "button"
    toggle.className =
      "inline-flex items-center px-2 py-1 text-xs bg-base-100 text-base-600 rounded-full cursor-pointer mb-2"
    toggle.setAttribute("aria-label", "Toggle previous message")
    toggle.textContent = "..."

    const body = document.createElement("div")
    body.className = "border-l-4 border-base-300 pl-4 py-2 bg-base-50 rounded-r-md"
    this.iframe = this.buildIframe()
    body.appendChild(this.iframe)

    // Prevent the iframe (or anything under it) from stealing native focus
    // out of the surrounding contenteditable editor. Capture phase fires
    // before the browser commits the focus shift on click.
    this.dom.addEventListener(
      "mousedown",
      event => {
        if (event.target === toggle) return
        event.preventDefault()
      },
      true
    )

    toggle.setAttribute("aria-expanded", startsCollapsed ? "false" : "true")
    body.hidden = startsCollapsed

    toggle.addEventListener("mousedown", event => event.preventDefault())
    toggle.addEventListener("click", event => {
      event.preventDefault()
      event.stopPropagation()
      const expanded = body.hidden
      body.hidden = !expanded
      toggle.setAttribute("aria-expanded", expanded ? "true" : "false")
    })

    this.dom.appendChild(toggle)
    this.dom.appendChild(body)

    this.unsubscribeTheme = subscribeToTheme(() => this.updateTheme())
  }

  private buildIframe(): HTMLIFrameElement {
    const iframe = document.createElement("iframe")
    iframe.className = "border-0 rounded-md bg-transparent"
    iframe.style.height = "60px"
    // Mirror of EmailMessageBody's width pin (see there for why).
    iframe.style.width = "1px"
    iframe.style.minWidth = "100%"
    iframe.style.maxWidth = "100%"
    // allow-same-origin is required so the parent can read iframe.contentDocument
    // to drive the ResizeObserver-based auto-sizing. Without it the iframe stays
    // stuck at the initial 60px and only the first line is visible.
    iframe.setAttribute("sandbox", "allow-popups allow-popups-to-escape-sandbox allow-same-origin")

    // Fallback: load fires against the real document after every subresource
    // settles, covering the fast path and any navigation the parse poll missed.
    // The guard is reset per srcdoc reassignment (see startSizingForCurrentSrcdoc)
    // so a theme toggle re-attaches the observer.
    iframe.addEventListener("load", () => {
      const doc = iframe.contentDocument
      if (isRealSrcdocReady(doc)) this.initSizing(doc.body)
    })

    const previousDoc = iframe.contentDocument
    iframe.srcdoc = this.srcdocFor()
    this.startSizingForCurrentSrcdoc(previousDoc)

    return iframe
  }

  // Size the iframe as soon as the srcdoc body is parsed and keep it in sync as
  // later layout changes land (images loading, quotes expanding). Idempotent per
  // navigation: the rAF poll and the load fallback may both reach it, but only
  // the first run per srcdoc takes effect.
  private initSizing(body: HTMLElement): void {
    if (this.sizingInitialized || !this.iframe) return
    this.sizingInitialized = true
    this.iframe.style.setProperty("height", `${body.scrollHeight}px`, "important")

    this.resizeObserver?.disconnect()
    this.resizeObserver = new ResizeObserver(() => {
      const target = this.iframe?.contentDocument?.body
      if (target) this.iframe?.style.setProperty("height", `${target.scrollHeight}px`, "important")
    })
    this.resizeObserver.observe(body)
  }

  // Size on parse, not on load: the load event fires only after every subresource
  // resolves (or the browser abandons it), so a slow/hanging tracking pixel could
  // pin the iframe at 60px for ~30s. Poll each frame for the parsed srcdoc body
  // instead, bounded so a never-parsing document can't spin forever.
  //
  // Reassigning srcdoc (updateTheme) does not swap contentDocument synchronously,
  // so an early tick can still see the *previous* (about:srcdoc, populated)
  // document. Sizing that one would trip the guard and leave the ResizeObserver
  // attached to a body about to be discarded — silently breaking resize after a
  // theme toggle. Require a different document object than the pre-navigation one.
  private startSizingForCurrentSrcdoc(previousDoc: Document | null): void {
    if (this.rafId) cancelAnimationFrame(this.rafId)
    this.resizeObserver?.disconnect()
    this.resizeObserver = null
    this.sizingInitialized = false

    const generation = ++this.sizingGeneration
    let attempts = 0
    const poll = () => {
      if (generation !== this.sizingGeneration || !this.iframe) return
      const doc = this.iframe.contentDocument
      if (doc !== previousDoc && isRealSrcdocReady(doc)) {
        this.initSizing(doc.body)
        return
      }
      if (++attempts < 60) this.rafId = requestAnimationFrame(poll)
    }
    this.rafId = requestAnimationFrame(poll)
  }

  private srcdocFor(): string {
    const theme = getCurrentTheme()
    const cssUrl = window.EMAIL_CSS_URL || ""
    const processed = wrapEmojiInHtml(processEmailQuotesInHtml(this.htmlContent))
    // No `authored` class: quoted HTML is arbitrary (a forwarded/replied third-party
    // message), so it renders under email.css's default `white-space: normal` rather
    // than the authored-only pre-wrap rules, matching pre-whitespace-fidelity behavior.
    const htmlClass = `${theme} ${this.isMobile ? "mobile" : "desktop"}`
    return `<!DOCTYPE html>
<html lang="en" class="${htmlClass}">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="color-scheme" content="${theme}">
    <link rel="stylesheet" href="${cssUrl}">
  </head>
  <body>${processed}</body>
</html>`
  }

  private updateTheme(): void {
    if (!this.iframe) return
    const previousDoc = this.iframe.contentDocument
    this.iframe.srcdoc = this.srcdocFor()
    this.startSizingForCurrentSrcdoc(previousDoc)
  }

  stopEvent(): boolean {
    return true
  }

  ignoreMutation(): boolean {
    return true
  }

  destroy(): void {
    this.unsubscribeTheme?.()
    this.unsubscribeTheme = null
    if (this.rafId) cancelAnimationFrame(this.rafId)
    this.rafId = 0
    // Invalidate any in-flight poll so it stops re-scheduling after teardown.
    this.sizingGeneration++
    this.resizeObserver?.disconnect()
    this.resizeObserver = null
    this.iframe = null
  }
}
