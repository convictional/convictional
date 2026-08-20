import { describe, expect, test } from "vitest"

import { stripPreviewedAttachmentLink } from "~/react/composites/stripAttachmentLink"

function filePreview(url: string) {
  return { url, resource_kind: "file" }
}

describe("stripPreviewedAttachmentLink", () => {
  test("attachment-only content becomes empty", () => {
    expect(
      stripPreviewedAttachmentLink("[report.pdf](https://x/report.pdf) ", filePreview("https://x/report.pdf"))
    ).toBe("")
  })

  test("prose plus attachment leaves no double space", () => {
    expect(
      stripPreviewedAttachmentLink(
        "see [report.pdf](https://x/report.pdf) please",
        filePreview("https://x/report.pdf")
      )
    ).toBe("see please")
  })

  test("punctuation-adjacent link leaves no orphaned space before the comma", () => {
    expect(
      stripPreviewedAttachmentLink(
        "see [report.pdf](https://x/report.pdf), thanks",
        filePreview("https://x/report.pdf")
      )
    ).toBe("see, thanks")
  })

  test("escaped-paren destination matches the unescaped preview url", () => {
    expect(
      stripPreviewedAttachmentLink("[file(1).pdf](https://x/file\\(1\\).pdf)", filePreview("https://x/file(1).pdf"))
    ).toBe("")
  })

  test("a non-matching url is preserved", () => {
    const content = "[report.pdf](https://x/report.pdf)"
    expect(stripPreviewedAttachmentLink(content, filePreview("https://x/other.pdf"))).toBe(content)
  })

  test("only the previewed link is stripped; a second link survives", () => {
    expect(
      stripPreviewedAttachmentLink(
        "[a.pdf](https://x/a.pdf) and [b.pdf](https://x/b.pdf)",
        filePreview("https://x/a.pdf")
      )
    ).toBe("and [b.pdf](https://x/b.pdf)")
  })

  test("image markdown is never matched", () => {
    const content = "![alt](https://x/report.pdf)"
    expect(stripPreviewedAttachmentLink(content, filePreview("https://x/report.pdf"))).toBe(content)
  })

  test("only file previews are stripped", () => {
    const content = "[the doc](https://x/report.pdf)"
    expect(stripPreviewedAttachmentLink(content, { url: "https://x/report.pdf", resource_kind: "document" })).toBe(
      content
    )
    expect(stripPreviewedAttachmentLink(content, { url: "https://x/report.pdf" })).toBe(content)
  })

  test("a null/undefined preview returns content unchanged", () => {
    const content = "[report.pdf](https://x/report.pdf)"
    expect(stripPreviewedAttachmentLink(content, null)).toBe(content)
    expect(stripPreviewedAttachmentLink(content, undefined)).toBe(content)
  })

  test("whitespace away from the removed link is left intact", () => {
    // A hard line break (two trailing spaces) and prose spacing elsewhere in the body
    // must survive: the tidy only touches the removal site, not the whole message.
    expect(
      stripPreviewedAttachmentLink(
        "[report.pdf](https://x/report.pdf)\nRoses  \nViolets",
        filePreview("https://x/report.pdf")
      )
    ).toBe("\nRoses  \nViolets")
    expect(
      stripPreviewedAttachmentLink(
        "[report.pdf](https://x/report.pdf) score 10 : 3",
        filePreview("https://x/report.pdf")
      )
    ).toBe("score 10 : 3")
  })
})
