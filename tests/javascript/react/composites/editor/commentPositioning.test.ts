import { expect, test, describe } from "vitest"

import {
  computeActiveCardTop,
  isSelectionInsideEditor,
  markAnchorElement,
  pickCardDirection,
} from "../../../../../app/javascript/react/composites/editor/features/comments/useCommentPositioning"

describe("pickCardDirection", () => {
  const viewport = 800

  test("drops down when there is enough room below the mark", () => {
    // Mark near the top, plenty of room below for a 300px card
    const direction = pickCardDirection({ top: 100, bottom: 120 }, 300, viewport)
    expect(direction).toBe("down")
  })

  test("drops up when card overflows below and there is more room above", () => {
    // Mark near the bottom — only 50px below, ~700px above, card is 400px
    const direction = pickCardDirection({ top: 700, bottom: 750 }, 400, viewport)
    expect(direction).toBe("up")
  })

  test("stays down when card overflows below but there is also no room above", () => {
    // Card taller than the viewport — neither side fits, prefer default downward
    const direction = pickCardDirection({ top: 100, bottom: 120 }, 1000, viewport)
    expect(direction).toBe("down")
  })

  test("respects topClampOffset (sticky header) when comparing space above", () => {
    // Sticky header takes 600px. Mark at top:620 / bottom:640. spaceAbove (after clamp) = 20,
    // spaceBelow = 160 — should drop down.
    const direction = pickCardDirection({ top: 620, bottom: 640 }, 300, viewport, 600)
    expect(direction).toBe("down")
  })

  test("ties go to down (default growth)", () => {
    // spaceBelow = 400, spaceAbove = 400, card 500 — spaceAbove is not strictly greater
    const direction = pickCardDirection({ top: 400, bottom: 400 }, 500, viewport)
    expect(direction).toBe("down")
  })
})

describe("isSelectionInsideEditor", () => {
  // Fake node whose `contains` matches itself and any listed descendants, like Node.contains.
  const makeNode = (descendants: object[] = []) => {
    const node: { contains: (other: Node | null) => boolean } = {
      contains: other => other === node || descendants.includes(other as object),
    }
    return node as unknown as Node
  }

  test("true when the anchor is the editor or a descendant of it", () => {
    const anchor = makeNode()
    const editor = makeNode([anchor as object])
    expect(isSelectionInsideEditor(editor, anchor)).toBe(true)
    expect(isSelectionInsideEditor(editor, editor)).toBe(true)
  })

  test("false when the anchor is outside the editor (e.g. a nested comment editor)", () => {
    const outsideAnchor = makeNode()
    const editor = makeNode()
    expect(isSelectionInsideEditor(editor, outsideAnchor)).toBe(false)
  })

  test("false when either the editor or the anchor is null", () => {
    const node = makeNode()
    expect(isSelectionInsideEditor(null, node)).toBe(false)
    expect(isSelectionInsideEditor(node, null)).toBe(false)
    expect(isSelectionInsideEditor(null, null)).toBe(false)
  })
})

describe("computeActiveCardTop", () => {
  test("down direction: anchors card top to mark top, invariant under page scroll", () => {
    expect(computeActiveCardTop({ top: 300, bottom: 320 }, 100, 250, "down")).toBe(200)
    expect(computeActiveCardTop({ top: -200, bottom: -180 }, -400, 250, "down")).toBe(200)
  })

  test("up direction: anchors card bottom to mark bottom, invariant under page scroll", () => {
    expect(computeActiveCardTop({ top: 580, bottom: 600 }, 100, 300, "up")).toBe(200)
    expect(computeActiveCardTop({ top: 80, bottom: 100 }, -400, 300, "up")).toBe(200)
  })
})

describe("markAnchorElement", () => {
  // A ProseMirror-like editor DOM: top-level blocks are direct children of the root, and a
  // collapsed section flags its following-sibling blocks with the collapse class (the
  // heading itself never carries it). The comment highlight span lives inside a block.
  const buildEditor = (html: string): Element => {
    const root = document.createElement("div")
    root.innerHTML = html.trim()
    return root
  }
  const commentMark = (root: Element): Element => root.querySelector("[data-comment-id]")!

  test("returns the mark itself when it is not inside a collapsed section", () => {
    const root = buildEditor(`
      <h1>Heading</h1>
      <p>Body <span class="inline-comment-highlight" data-comment-id="c1">text</span></p>
    `)
    const mark = commentMark(root)
    expect(markAnchorElement(mark)).toBe(mark)
  })

  test("anchors to the section heading when the mark's block is collapsed", () => {
    const root = buildEditor(`
      <h2 class="target">Heading</h2>
      <p class="heading-section-collapsed">Body <span class="inline-comment-highlight" data-comment-id="c1">text</span></p>
    `)
    expect(markAnchorElement(commentMark(root))).toBe(root.querySelector(".target"))
  })

  test("anchors to the outermost heading when nested subsections are collapsed", () => {
    // Collapsing the H1 hides its H2 subheading and the paragraph beneath it — the marker
    // must land on the still-visible H1, skipping the collapsed subheading.
    const root = buildEditor(`
      <h1 class="target">Top</h1>
      <h2 class="heading-section-collapsed">Sub</h2>
      <p class="heading-section-collapsed">Body <span class="inline-comment-highlight" data-comment-id="c1">text</span></p>
    `)
    expect(markAnchorElement(commentMark(root))).toBe(root.querySelector(".target"))
  })

  test("returns null when a collapsed mark has no heading before it", () => {
    const root = buildEditor(`
      <p class="heading-section-collapsed">Body <span class="inline-comment-highlight" data-comment-id="c1">text</span></p>
    `)
    expect(markAnchorElement(commentMark(root))).toBeNull()
  })
})
