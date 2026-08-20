import { expect, test, describe, beforeEach, afterEach } from "vitest"
import { builders } from "prosemirror-test-builder"
import { schema, plugins } from "../../../../app/javascript/richText/schema"
import { EditorState, TextSelection } from "prosemirror-state"
import { EditorView } from "prosemirror-view"

const { doc, paragraph, em, strong } = builders(schema)

// Import the actual extensions to get their regex patterns
import { TrailingSpaceItalicExtension, TrailingSpaceBoldExtension } from "../../../../app/javascript/richText/schema"

// Get the actual patterns from the extensions
const italicExtension = new TrailingSpaceItalicExtension()
const boldExtension = new TrailingSpaceBoldExtension()
const italicRules = italicExtension.proseMirrorInputRules(schema)
const boldRules = boldExtension.proseMirrorInputRules(schema)

// Extract patterns from the input rules
const asteriskPattern = italicRules[0].match
const underscorePattern = italicRules[1].match
const doubleAsteriskPattern = boldRules[0].match
const doubleUnderscorePattern = boldRules[1].match

// Test the actual regex patterns used in our extensions
describe("Input Rule Regexes", () => {
  describe("Italic patterns", () => {

    test("asterisk italic - single word", () => {
      const text = "*word* "
      const match = text.match(asteriskPattern)
      expect(match).not.toBeNull()
      expect(match![1]).toBe("word")
      expect(match![2]).toBe(" ")
    })

    test("asterisk italic - multiple words", () => {
      const text = "*hello world* "
      const match = text.match(asteriskPattern)
      expect(match).not.toBeNull()
      expect(match![1]).toBe("hello world")
      expect(match![2]).toBe(" ")
    })

    test("asterisk italic - should NOT match across multiple patterns", () => {
      const text = "*first *second* "
      const match = text.match(asteriskPattern)
      expect(match).not.toBeNull()
      expect(match![1]).toBe("second") // Should only match the last valid pattern

      // Test the specific case mentioned by user
      const userCase = "_asdasdasd _asdasdasd_ "
      const userMatch = userCase.match(underscorePattern)
      expect(userMatch).not.toBeNull()
      expect(userMatch![1]).toBe("asdasdasd") // Should only match the second word
    })

    test("asterisk italic - should NOT match with leading/trailing spaces", () => {
      const text = "* word * "
      const match = text.match(asteriskPattern)
      expect(match).toBeNull()
    })

    test("underscore italic - single word", () => {
      const text = "_word_ "
      const match = text.match(underscorePattern)
      expect(match).not.toBeNull()
      expect(match![1]).toBe("word")
      expect(match![2]).toBe(" ")
    })

    test("underscore italic - should NOT match across multiple patterns", () => {
      const text = "_first _second_ "
      const match = text.match(underscorePattern)
      expect(match).not.toBeNull()
      expect(match![1]).toBe("second") // Should only match the last valid pattern
    })
  })

  describe("Bold patterns", () => {

    test("double asterisk bold - single word", () => {
      const text = "**word** "
      const match = text.match(doubleAsteriskPattern)
      expect(match).not.toBeNull()
      expect(match![1]).toBe("word")
      expect(match![2]).toBe(" ")
    })

    test("double asterisk bold - multiple words", () => {
      const text = "**hello world** "
      const match = text.match(doubleAsteriskPattern)
      expect(match).not.toBeNull()
      expect(match![1]).toBe("hello world")
      expect(match![2]).toBe(" ")
    })

    test("double asterisk bold - should NOT match across multiple patterns", () => {
      const text = "**first **second** "
      const match = text.match(doubleAsteriskPattern)
      expect(match).not.toBeNull()
      expect(match![1]).toBe("second") // Should only match the last valid pattern
    })

    test("double underscore bold - should NOT match across multiple patterns", () => {
      const text = "__first __second__ "
      const match = text.match(doubleUnderscorePattern)
      expect(match).not.toBeNull()
      expect(match![1]).toBe("second") // Should only match the last valid pattern
    })
  })

  describe("Edge cases", () => {
    test("single character content", () => {
      const text = "*a* "
      const match = text.match(asteriskPattern)
      expect(match).not.toBeNull()
      expect(match![1]).toBe("a")
    })

    test("no trailing space - should not match", () => {
      const text = "*word*"
      const match = text.match(asteriskPattern)
      expect(match).toBeNull()
    })

    test("nested delimiters of different types should work", () => {
      const text = "*word_with_underscores* "
      const match = text.match(asteriskPattern)
      expect(match).not.toBeNull()
      expect(match![1]).toBe("word_with_underscores")
    })

    test("content starting or ending with space should not match", () => {
      const textStartSpace = "* word* "
      const matchStartSpace = textStartSpace.match(asteriskPattern)
      expect(matchStartSpace).toBeNull()

      const textEndSpace = "*word * "
      const matchEndSpace = textEndSpace.match(asteriskPattern)
      expect(matchEndSpace).toBeNull()
    })
  })
})

describe("Emoji shortcode pattern", () => {
  const emojiPattern = /:([a-z0-9_+-]+):$/

  test("matches common shortcodes", () => {
    expect(":smile:".match(emojiPattern)![1]).toBe("smile")
    expect(":heart:".match(emojiPattern)![1]).toBe("heart")
    expect(":+1:".match(emojiPattern)![1]).toBe("+1")
    expect(":thumbsup:".match(emojiPattern)![1]).toBe("thumbsup")
  })

  test("matches shortcodes with underscores and special characters", () => {
    expect(":heart_eyes:".match(emojiPattern)![1]).toBe("heart_eyes")
    expect(":heavy_minus_sign:".match(emojiPattern)![1]).toBe("heavy_minus_sign")
  })

  test("does not match without closing colon", () => {
    expect(":smile".match(emojiPattern)).toBeNull()
  })

  test("does not match empty shortcode", () => {
    expect("::".match(emojiPattern)).toBeNull()
  })

  test("does not match uppercase", () => {
    expect(":SMILE:".match(emojiPattern)).toBeNull()
  })

  test("matches at end of text with preceding content", () => {
    const match = "hello :smile:".match(emojiPattern)
    expect(match).not.toBeNull()
    expect(match![1]).toBe("smile")
  })
})

describe("Input rules integration (live editor)", () => {
  let view: EditorView
  let container: HTMLElement

  beforeEach(() => {
    container = document.createElement("div")
    document.body.appendChild(container)
  })

  afterEach(() => {
    view?.destroy()
    container.remove()
  })

  function createViewWithText(content: string): EditorView {
    const doc = schema.node("doc", null, [
      schema.node("paragraph", null, [schema.text(content)]),
    ])
    const state = EditorState.create({ doc, schema, plugins })
    view = new EditorView(container, { state })
    return view
  }

  function typeSpace(): boolean {
    const end = view.state.doc.content.size - 1
    view.dispatch(view.state.tr.setSelection(TextSelection.create(view.state.doc, end)))
    const { from, to } = view.state.selection
    const handled = view.someProp("handleTextInput", (f) => f(view, from, to, " "))
    if (!handled) {
      view.dispatch(view.state.tr.insertText(" "))
    }
    return !!handled
  }

  test("**bold** followed by space produces bold text", () => {
    createViewWithText("**bold**")
    typeSpace()

    const paragraph = view.state.doc.firstChild!
    expect(paragraph.textContent).toContain("bold")
    const textNode = paragraph.firstChild!
    expect(textNode.marks.some((m) => m.type.name === "strong")).toBe(true)
  })

  test("*italic* followed by space produces italic text", () => {
    createViewWithText("*italic*")
    typeSpace()

    const paragraph = view.state.doc.firstChild!
    expect(paragraph.textContent).toContain("italic")
    const textNode = paragraph.firstChild!
    expect(textNode.marks.some((m) => m.type.name === "em")).toBe(true)
  })

  test("__bold__ followed by space produces bold text", () => {
    createViewWithText("__bold__")
    typeSpace()

    const paragraph = view.state.doc.firstChild!
    expect(paragraph.textContent).toContain("bold")
    const textNode = paragraph.firstChild!
    expect(textNode.marks.some((m) => m.type.name === "strong")).toBe(true)
  })

  test("_italic_ followed by space produces italic text", () => {
    createViewWithText("_italic_")
    typeSpace()

    const paragraph = view.state.doc.firstChild!
    expect(paragraph.textContent).toContain("italic")
    const textNode = paragraph.firstChild!
    expect(textNode.marks.some((m) => m.type.name === "em")).toBe(true)
  })
})
