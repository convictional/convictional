import { describe, expect, test } from "vitest"
import { builders } from "prosemirror-test-builder"

import { schema, serialize, withoutTrailingEmptyBlocks } from "../../../../app/javascript/richText/schema"

const { doc, paragraph, heading, image } = builders(schema)

// The attachments plugin leaves an empty paragraph after an upload batch as a caret target (see
// attachments.ts). Every editor's send/save path runs the doc through this before serializing so
// that caret paragraph doesn't persist as a stray "<br />" blank line.
describe("withoutTrailingEmptyBlocks", () => {
  test("drops a trailing empty paragraph left after an image upload", () => {
    const result = withoutTrailingEmptyBlocks(doc(paragraph(image({ src: "/a" }), image({ src: "/b" })), paragraph()))
    expect(serialize(result)).toBe("![](/a)![](/b)\n")
  })

  test("drops multiple consecutive trailing empty paragraphs", () => {
    const result = withoutTrailingEmptyBlocks(doc(paragraph("hello"), paragraph(), paragraph(), paragraph()))
    expect(serialize(result)).toBe("hello\n")
  })

  test("keeps a real block that follows the images (a typed caption survives)", () => {
    const result = withoutTrailingEmptyBlocks(doc(paragraph(image({ src: "/a" })), paragraph("nice pic")))
    expect(serialize(result)).toBe("![](/a)\n\nnice pic\n")
  })

  test("leaves a blank document as a single empty paragraph (never empties the doc)", () => {
    const result = withoutTrailingEmptyBlocks(doc(paragraph()))
    expect(result.childCount).toBe(1)
    expect(serialize(result)).toBe("<br />\n")
  })

  test("only strips paragraphs — a trailing empty heading is preserved", () => {
    const result = withoutTrailingEmptyBlocks(doc(paragraph("hi"), heading({ level: 1 })))
    expect(result.lastChild?.type).toBe(schema.nodes.heading)
  })
})
