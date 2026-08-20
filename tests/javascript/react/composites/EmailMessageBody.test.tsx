import { readFileSync } from "node:fs"
import { join } from "node:path"

import { render } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { buildSrcdoc, EmailMessageBody } from "~/react/composites/EmailMessageBody"
import { isRealSrcdocReady } from "~/react/shared/iframeSrcdocSizing"

describe("isRealSrcdocReady", () => {
  it("is false for null/undefined documents", () => {
    expect(isRealSrcdocReady(null)).toBe(false)
    expect(isRealSrcdocReady(undefined)).toBe(false)
  })

  it("is false for a document that is not the navigated srcdoc (about:blank placeholder)", () => {
    // A freshly-created iframe exposes an about:blank document with an empty body
    // and readyState "complete" before the srcdoc navigation completes. jsdom's
    // createHTMLDocument stands in for that placeholder: its URL is not about:srcdoc.
    const placeholder = document.implementation.createHTMLDocument()
    expect(placeholder.URL).not.toBe("about:srcdoc")
    expect(isRealSrcdocReady(placeholder)).toBe(false)
  })

  it("is false for the real srcdoc document before parse produces content", () => {
    const doc = document.implementation.createHTMLDocument()
    Object.defineProperty(doc, "URL", { value: "about:srcdoc", configurable: true })
    expect(doc.body.childNodes.length).toBe(0)
    expect(isRealSrcdocReady(doc)).toBe(false)
  })

  it("is true only for the real srcdoc document with parsed body content", () => {
    const doc = document.implementation.createHTMLDocument()
    Object.defineProperty(doc, "URL", { value: "about:srcdoc", configurable: true })
    doc.body.appendChild(doc.createElement("p"))
    expect(isRealSrcdocReady(doc)).toBe(true)
  })
})

describe("EmailMessageBody", () => {
  let addSpy: ReturnType<typeof vi.spyOn>
  let removeSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    addSpy = vi.spyOn(HTMLIFrameElement.prototype, "addEventListener")
    removeSpy = vi.spyOn(HTMLIFrameElement.prototype, "removeEventListener")
  })

  afterEach(() => {
    addSpy.mockRestore()
    removeSpy.mockRestore()
  })

  // Regression for #8744: the iframe load listener's closure captures the iframe
  // and sizing state, so it must be removed on unmount to release the detached
  // iframe subtree deterministically rather than relying on GC breaking the cycle.
  it("removes the iframe load listener on unmount", () => {
    const { unmount } = render(<EmailMessageBody contentHtml="<p>hello</p>" isMobile={false} isAuthored />)

    const loadHandler = addSpy.mock.calls.find(([type]) => type === "load")?.[1]
    expect(loadHandler).toBeDefined()

    unmount()

    expect(removeSpy).toHaveBeenCalledWith("load", loadHandler)
  })

  it("pins the iframe width so wide email content can't overflow the layout (#8913)", () => {
    const { container } = render(<EmailMessageBody contentHtml="<p>hello</p>" isMobile isAuthored />)

    const iframe = container.querySelector("iframe") as HTMLIFrameElement
    expect(iframe).not.toBeNull()

    // The iOS-safe width pin (see EmailMessageBody for why all three are needed).
    expect(iframe.style.width).toBe("1px")
    expect(iframe.style.minWidth).toBe("100%")
    expect(iframe.style.maxWidth).toBe("100%")
    expect(iframe.classList.contains("w-full")).toBe(false)
  })
})

// The pre-wrap whitespace contract in email.css is scoped to `.authored` so it only
// applies to Convictional-composed mail. Inbound RECEIVED third-party HTML is pretty-printed
// with inter-tag newlines that pre-wrap would render as visible breaks, so it must
// render under the default `white-space: normal`. buildSrcdoc gates the class, mirroring
// the server's `preserve_whitespace = message_type != RECEIVED`.
describe("buildSrcdoc authored scoping", () => {
  const cssUrl = "/static/email.css"

  it("adds the authored class only for authored content and keeps theme/viewport classes", () => {
    const authored = buildSrcdoc("<p>hi</p>", "light", false, cssUrl, true)
    expect(authored).toContain('class="light desktop authored"')

    const received = buildSrcdoc("<p>hi</p>", "light", false, cssUrl, false)
    expect(received).toContain('class="light desktop"')
    expect(received).not.toContain("authored")

    // The mobile/theme classes remain independent of the authored flag.
    expect(buildSrcdoc("<p>hi</p>", "dark", true, cssUrl, true)).toContain('class="dark mobile authored"')
  })
})

// jsdom applies no stylesheets, so we assert the authored scoping structurally against
// the CSS source: the pre-wrap rule must target `.authored td` etc., never a bare `td`,
// so inbound RECEIVED mail is unaffected. pre/code stay exempt.
describe("email.css pre-wrap authored scoping", () => {
  const css = readFileSync(join(__dirname, "../../../../app/styles/email.css"), "utf8")

  it("scopes pre-wrap to authored text-bearing blocks, not bare selectors or pre/code", () => {
    const code = css.replace(/\/\*[\s\S]*?\*\//g, "")
    const preWrapRule = /(?<selector>[.\w,\s]+)\{[^{}]*white-space:\s*pre-wrap[^{}]*\}/g
    const selectorLists = [...code.matchAll(preWrapRule)].map(m =>
      (m.groups?.selector ?? "")
        .trim()
        .split(",")
        .map(s => s.trim())
    )

    const blockRule = selectorLists.find(tags => tags.includes(".authored p") && tags.includes(".authored td"))
    expect(blockRule, "expected an authored-scoped rule listing the text-bearing blocks").toBeDefined()
    for (const tag of ["p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "td", "th"]) {
      expect(blockRule).toContain(`.authored ${tag}`)
    }

    // Every pre-wrap selector must be authored-scoped — no bare element selector may
    // leak the rule onto inbound RECEIVED mail — and code blocks stay exempt.
    for (const tags of selectorLists) {
      for (const tag of tags) {
        expect(tag.startsWith(".authored ")).toBe(true)
      }
      expect(tags).not.toContain(".authored pre")
      expect(tags).not.toContain(".authored code")
    }
  })
})
