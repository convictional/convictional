import type { Node as ProseMirrorNode } from "prosemirror-model"
import { afterEach, beforeEach, describe, expect, test } from "vitest"

import { QuotedHtmlNodeView } from "~/react/composites/editor/QuotedHtmlNodeView"
import { setThemeSetting } from "~/shared/themeApplicator"

describe("QuotedHtmlNodeView", () => {
  const node = { attrs: { htmlContent: "<p>quoted</p>", collapsed: false } } as unknown as ProseMirrorNode
  let nodeView: QuotedHtmlNodeView | null = null

  beforeEach(() => {
    setThemeSetting("light")
    document.documentElement.dataset.isMobile = "false"
  })

  afterEach(() => {
    nodeView?.destroy()
    nodeView = null
  })

  test("renders iframe with theme/mobile signals and reacts to theme changes", () => {
    nodeView = new QuotedHtmlNodeView(node)
    const iframe = nodeView.dom.querySelector("iframe") as HTMLIFrameElement

    expect(iframe).not.toBeNull()

    // #8913: the iOS-safe width pin keeps wide quoted HTML from overflowing on mobile.
    expect(iframe.style.width).toBe("1px")
    expect(iframe.style.minWidth).toBe("100%")
    expect(iframe.style.maxWidth).toBe("100%")
    expect(iframe.classList.contains("w-full")).toBe(false)

    expect(nodeView.dom.querySelectorAll("iframe")).toHaveLength(1)
    expect(iframe.srcdoc).toContain('class="light desktop"')
    expect(iframe.srcdoc).toContain('<meta name="color-scheme" content="light">')
    expect(iframe.srcdoc).toContain("<p>quoted</p>")

    setThemeSetting("dark")
    expect(iframe.srcdoc).toContain('class="dark desktop"')
    expect(iframe.srcdoc).toContain('<meta name="color-scheme" content="dark">')

    nodeView.destroy()
    const srcdocAfterDestroy = iframe.srcdoc
    setThemeSetting("light")
    expect(iframe.srcdoc).toBe(srcdocAfterDestroy)
  })

  test("renders mobile class when dataset.isMobile is true", () => {
    document.documentElement.dataset.isMobile = "true"
    nodeView = new QuotedHtmlNodeView(node)
    const iframe = nodeView.dom.querySelector("iframe") as HTMLIFrameElement
    expect(iframe.srcdoc).toContain('class="light mobile"')
  })
})
