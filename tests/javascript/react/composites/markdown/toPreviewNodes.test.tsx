import { cleanup, render } from "@testing-library/react"
import { afterEach, describe, expect, test } from "vitest"

import { markdownToPreviewNodes } from "~/react/composites/markdown/toPreviewNodes"

afterEach(cleanup)

function renderPreview(source: string) {
  return render(<div data-testid="preview">{markdownToPreviewNodes(source)}</div>)
}

describe("markdownToPreviewNodes", () => {
  test("renders a mention as a styled span and keeps surrounding text", () => {
    const { container } = renderPreview("Hey @[Bob Clams] take a look")

    const preview = container.querySelector("[data-testid=preview]")!
    expect(preview.textContent).toBe("Hey @Bob Clams take a look")

    const mentions = container.querySelectorAll("span.text-info-content")
    expect(mentions).toHaveLength(1)
    expect(mentions[0].textContent).toBe("@Bob Clams")
  })

  test("strips other markdown to plain text", () => {
    const { container } = renderPreview("**bold** text with `code`")

    const preview = container.querySelector("[data-testid=preview]")!
    expect(preview.textContent).toBe("bold text with code")
    expect(container.querySelector("span.text-info-content")).toBeNull()
  })

  test("renders multiple mentions in one string", () => {
    const { container } = renderPreview("@[Alice] and @[Bob]")

    const preview = container.querySelector("[data-testid=preview]")!
    expect(preview.textContent).toBe("@Alice and @Bob")
    expect(container.querySelectorAll("span.text-info-content")).toHaveLength(2)
  })

  test("collapses multi-line markdown into a single line", () => {
    const { container } = renderPreview("First paragraph\n\nSecond paragraph")

    const preview = container.querySelector("[data-testid=preview]")!
    expect(preview.textContent).toBe("First paragraph Second paragraph")
  })

  test("applies a custom mention class for muted (read) previews", () => {
    const { container } = render(
      <div data-testid="preview">
        {markdownToPreviewNodes("Hey @[Bob Clams]", { mentionClassName: "text-base-500" })}
      </div>,
    )

    const mention = container.querySelector("span")!
    expect(mention).toHaveClass("text-base-500")
    expect(mention).not.toHaveClass("text-info-content")
  })

  test("renders an image node as a plain-text placeholder, not a mention", () => {
    const empty = renderPreview("![](https://example.com/cat.png)")
    const emptyPreview = empty.container.querySelector("[data-testid=preview]")!
    expect(emptyPreview.textContent).not.toBe("")
    expect(emptyPreview.textContent).toBe("[image]")
    expect(empty.container.querySelector("span.text-info-content")).toBeNull()

    const alt = renderPreview("![a cat](https://example.com/cat.png)")
    const altPreview = alt.container.querySelector("[data-testid=preview]")!
    expect(altPreview.textContent).toBe("[a cat]")
    expect(alt.container.querySelector("span.text-info-content")).toBeNull()
  })

  test("renders nothing for an empty string", () => {
    const { container } = renderPreview("")

    expect(container.querySelector("[data-testid=preview]")!.textContent).toBe("")
  })
})
