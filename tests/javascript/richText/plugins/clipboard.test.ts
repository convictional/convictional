import { expect, test, describe } from "vitest"
import { clipboardPlugin, linkify, handleLinkPaste } from "../../../../app/javascript/richText/plugins/clipboard"
import { builders, eq } from "prosemirror-test-builder"
import { schema, parse, serialize } from "../../../../app/javascript/richText/schema"
import { EditorState, TextSelection } from "prosemirror-state"
import { Slice, Fragment, DOMParser as ProseMirrorDOMParser } from "prosemirror-model"
import { googleDocsPaste, googleDocsNestedListPaste } from "../fixtures/googleDocs"

// Round-trip a paste payload through transformPastedHTML -> ProseMirror schema parse ->
// markdown serializer. This is the fidelity signal the spec asks for: a realistic Google Docs
// payload should produce the expected markdown after the full pipeline.
function pasteToMarkdown(html: string): string {
  const cleaned = clipboardPlugin.props?.transformPastedHTML?.(html, null as any) ?? html
  const container = document.createElement("div")
  container.innerHTML = cleaned
  const parsed = ProseMirrorDOMParser.fromSchema(schema).parse(container)
  return serialize(parsed)
}

const { doc, paragraph, blockquote } = builders(schema)

// Test core markdown parsing functionality
test("Parse markdown content", () => {
  const markdownText = "# Header\n\n**Bold** and *italic* text\n\n* List item\n* Another item"
  const parsed = parse(markdownText)

  expect(parsed.content.childCount).toBe(3) // header, paragraph, list
  expect(parsed.content.firstChild?.type.name).toBe("heading")
  expect(parsed.content.firstChild?.attrs.level).toBe(1)
})

test("Parse code blocks without internal formatting", () => {
  const codeContent = "const x = **bold text**\n# This should not be a header"
  const parsed = parse("```\n" + codeContent + "\n```")

  expect(parsed.content.childCount).toBe(1)
  expect(parsed.content.firstChild?.type.name).toBe("code_block")
  expect(parsed.content.firstChild?.textContent).toBe(codeContent)
})

// Collect the link-marked text runs from a linkified fragment as [text, href] pairs.
function linkedRuns(fragment: ReturnType<typeof linkify>): Array<[string, string]> {
  const runs: Array<[string, string]> = []
  fragment.forEach(node => {
    if (node.type.name === "paragraph") {
      node.content.forEach(child => {
        const linkMark = child.marks?.find(mark => mark.type.name === "link")
        if (linkMark) {
          runs.push([child.text ?? "", linkMark.attrs.href as string])
        }
      })
    }
  })
  return runs
}

// Test linkification functionality
test("Linkify bare domains and scheme URLs in text", () => {
  // Bare domain alongside a scheme URL: both get linked, bare domain gets https:// prefix.
  let runs = linkedRuns(linkify(parse("Visit github.com and https://test.org for info").content))
  expect(runs).toHaveLength(2)
  expect(runs.find(([text]) => text === "github.com")?.[1]).toBe("https://github.com")
  expect(runs.find(([text]) => text === "https://test.org")?.[1]).toBe("https://test.org")

  // Bare domain with a path.
  runs = linkedRuns(linkify(parse("see github.com/Hypercontext/linkifyjs here").content))
  expect(runs).toHaveLength(1)
  expect(runs[0][1]).toBe("https://github.com/Hypercontext/linkifyjs")

  // www-prefixed bare domain.
  runs = linkedRuns(linkify(parse("go to www.google.com now").content))
  expect(runs).toHaveLength(1)
  expect(runs[0][1]).toBe("https://www.google.com")

  // Trailing period is excluded from the href and left as unlinked text.
  runs = linkedRuns(linkify(parse("Visit github.com.").content))
  expect(runs).toHaveLength(1)
  expect(runs[0][0]).toBe("github.com")
  expect(runs[0][1]).toBe("https://github.com")

  // Negative: filenames / module identifiers are not domains.
  expect(linkedRuns(linkify(parse("run main.go and index.js and Node.js, e.g. etc.").content))).toHaveLength(0)

  // Negative: email addresses are excluded (email type is not linkified).
  expect(linkedRuns(linkify(parse("email me at nick@example.com").content))).toHaveLength(0)

  // Negative: non-http(s) schemes (file:, ftp:) are not linkified — preserves the http(s)-only invariant.
  expect(linkedRuns(linkify(parse("open file:///etc/passwd or ftp://example.com/x").content))).toHaveLength(0)
})

test("Leave ordinary text alone", () => {
  const originalDoc = doc(paragraph("hello world"))
  const linkified = linkify(originalDoc.content)
  expect(eq(linkified, originalDoc.content)).toBe(true)
})

// Test paste behavior
test("clipboardTextParser linkifies URLs in text", () => {
  const mockContext = {
    parent: { type: { name: "paragraph" } },
  } as any

  // Test the clipboardTextParser functionality for linkification
  const parsed = clipboardPlugin.props?.clipboardTextParser?.("Visit https://example.com for info", mockContext, false)

  expect(parsed).not.toBeNull()

  // Verify links were created in the parsed content
  let foundLink = false
  parsed?.content.forEach(node => {
    if (node.isText && node.marks?.some(mark => mark.type.name === "link")) {
      foundLink = true
    } else if (node.type.name === "paragraph") {
      node.content.forEach(child => {
        if (child.marks?.some(mark => mark.type.name === "link")) {
          foundLink = true
        }
      })
    }
  })
  expect(foundLink).toBe(true)

  // handlePaste should return false for regular cases
  const mockView = {
    state: {
      selection: {
        empty: true,
        $from: { parent: { type: { name: "paragraph" } }, depth: 1 },
      },
    },
  } as any
  const pasteEvent = {
    clipboardData: {
      getData: (format: string) => (format === "text/plain" ? "Visit https://example.com for info" : ""),
    },
  } as ClipboardEvent
  const result = clipboardPlugin.props?.handlePaste?.(mockView, pasteEvent, parsed!)
  expect(result).toBe(false)
})
test("clipboardTextParser processes bare URLs with linkification", () => {
  const mockContext = {
    parent: { type: { name: "paragraph" } },
    depth: 1,
  } as any

  // Test that bare URLs are now processed and linkified
  const parsed = clipboardPlugin.props?.clipboardTextParser?.("https://example.com", mockContext, false, null as any)

  expect(parsed).not.toBeNull()
  expect(parsed?.content.childCount).toBe(1)

  // Should be linkified text
  let hasLinkMark = false
  let hasBlockContent = false

  parsed?.content.forEach(node => {
    if (node.isBlock) {
      hasBlockContent = true
    }
    if (node.marks?.some(mark => mark.type.name === "link")) {
      hasLinkMark = true
    }
  })

  expect(hasLinkMark).toBe(true) // Should have link marks
  expect(hasBlockContent).toBe(false) // Should be inline content

  // handlePaste should return false for regular cases
  const mockView = {
    state: {
      selection: {
        empty: true,
        $from: { parent: { type: { name: "paragraph" } }, depth: 1 },
      },
    },
  } as any
  const pasteEvent = {
    clipboardData: {
      getData: (format: string) => (format === "text/plain" ? "https://example.com" : ""),
    },
  } as ClipboardEvent
  const handlePasteResult = clipboardPlugin.props?.handlePaste?.(mockView, pasteEvent, parsed!)
  expect(handlePasteResult).toBe(false) // Falls back to default behavior
})

test("Plain paste bypasses formatting", () => {
  const mockContext = {
    parent: { type: { name: "paragraph" } },
  } as any

  // Test with plain=true (equivalent to shift+paste)
  const parsed = clipboardPlugin.props?.clipboardTextParser?.(
    "# Header https://example.com",
    mockContext,
    true,
    null as any
  )

  expect(parsed).not.toBeNull()

  // Should return unformatted text (no markdown parsing)
  let hasPlainText = false
  let hasMarkdown = false

  parsed?.content.forEach(node => {
    if (node.isText && node.text === "# Header https://example.com") {
      hasPlainText = true
    }
    if (node.type.name === "heading") {
      hasMarkdown = true
    }
  })

  expect(hasPlainText).toBe(true)
  expect(hasMarkdown).toBe(false) // Should not parse markdown when plain=true
})

test("Code block prevents formatting", () => {
  const mockContext = {
    parent: { type: { name: "code_block" } },
  } as any

  // Test with code block context
  const parsed = clipboardPlugin.props?.clipboardTextParser?.("# Header", mockContext, false, null as any)

  expect(parsed).not.toBeNull()

  // Should return unformatted text (no markdown parsing in code blocks)
  let hasPlainText = false
  let hasMarkdown = false

  parsed?.content.forEach(node => {
    if (node.isText && node.text === "# Header") {
      hasPlainText = true
    }
    if (node.type.name === "heading") {
      hasMarkdown = true
    }
  })

  expect(hasPlainText).toBe(true)
  expect(hasMarkdown).toBe(false) // Should not parse markdown in code blocks
})

// Test special link paste behavior
test("Paste URL over selection applies link to selection", () => {
  // Test with pre-linked content
  const pastedLink = doc(
    paragraph(schema.text("https://example.com", [schema.marks.link.create({ href: "https://example.com" })]))
  )

  let state = EditorState.create({ doc: doc(paragraph("hello world")), plugins: [clipboardPlugin] })
  const dispatch = tr => {
    state = state.apply(tr)
  }

  // Select "world"
  dispatch(state.tr.setSelection(TextSelection.create(state.doc, 7, 12)))

  const result = handleLinkPaste(state, dispatch, pastedLink.slice(0))
  expect(result).toBeTruthy()
  expect(
    eq(
      state.doc,
      doc(
        paragraph(
          schema.text("hello "),
          schema.text("world", [schema.marks.link.create({ href: "https://example.com" })])
        )
      )
    )
  ).toBe(true)
})

test("Paste plain URL over selection applies link to selection", () => {
  // Test with plain text URL
  const plainUrl = doc(paragraph("https://example.com"))

  let state = EditorState.create({ doc: doc(paragraph("hello world")), plugins: [clipboardPlugin] })
  const dispatch = tr => {
    state = state.apply(tr)
  }

  // Select "world"
  dispatch(state.tr.setSelection(TextSelection.create(state.doc, 7, 12)))

  const result = handleLinkPaste(state, dispatch, plainUrl.slice(0))
  expect(result).toBeTruthy()
  expect(
    eq(
      state.doc,
      doc(
        paragraph(
          schema.text("hello "),
          schema.text("world", [schema.marks.link.create({ href: "https://example.com" })])
        )
      )
    )
  ).toBe(true)
})

test("Paste bare domain over selection applies link to selection", () => {
  // A bare domain pasted over a selection links the selection with an https:// href.
  const plain = doc(paragraph("github.com"))

  let state = EditorState.create({ doc: doc(paragraph("hello world")), plugins: [clipboardPlugin] })
  const dispatch = tr => {
    state = state.apply(tr)
  }

  // Select "world"
  dispatch(state.tr.setSelection(TextSelection.create(state.doc, 7, 12)))

  const result = handleLinkPaste(state, dispatch, plain.slice(0))
  expect(result).toBeTruthy()
  expect(
    eq(
      state.doc,
      doc(
        paragraph(
          schema.text("hello "),
          schema.text("world", [schema.marks.link.create({ href: "https://github.com" })])
        )
      )
    )
  ).toBe(true)
})

// This test is now covered by "clipboardTextParser converts single URL to inline content"
// The clipboardTextParser approach handles this automatically, so no special handlePaste logic needed

test("clipboardTextParser handles markdown content appropriately", () => {
  const markdownText =
    "## New Heading\n\n**Bold text** with [link](https://example.com)\n\n```js\nconsole.log('code');\n```"

  const mockContext = {
    parent: { type: { name: "paragraph" } },
  } as any

  // Test the clipboardTextParser functionality for markdown parsing
  const parsed = clipboardPlugin.props?.clipboardTextParser?.(markdownText, mockContext, false)

  expect(parsed).not.toBeNull()
  expect(parsed?.content.childCount).toBeGreaterThan(0)

  // Verify it parsed the markdown (should have different block types)
  const blockTypes = new Set()
  parsed?.content.forEach(node => {
    blockTypes.add(node.type.name)
  })

  // Should have parsed the markdown into different block types
  expect(blockTypes.size).toBeGreaterThan(1) // Should have multiple types (heading, paragraph, code_block, etc.)

  // handlePaste should return false (let ProseMirror handle insertion)
  const mockView = {
    state: {
      selection: {
        empty: true,
        $from: { parent: { type: { name: "paragraph" } }, depth: 1 },
      },
    },
  } as any
  const pasteEvent = {
    clipboardData: {
      getData: (format: string) => (format === "text/plain" ? markdownText : ""),
    },
  } as ClipboardEvent
  const result = clipboardPlugin.props?.handlePaste?.(mockView, pasteEvent, parsed!)
  expect(result).toBe(false)
})

test("clipboardTextParser parses a GFM table with delimiter row", () => {
  const markdownText = "| Name | Role |\n|------|------|\n| Alice | Dev |\n| Bob | PM |"

  const mockContext = {
    parent: { type: { name: "paragraph" } },
    depth: 1,
  } as any

  const parsed = clipboardPlugin.props?.clipboardTextParser?.(markdownText, mockContext, false)

  expect(parsed).not.toBeNull()
  expect(parsed?.content.firstChild?.type.name).toBe("table")
})

test("clipboardTextParser does NOT parse a single pipe-wrapped sentence as a table", () => {
  // Without a delimiter row, a line like "| pipe demo |" is not a table —
  // it should fall through to plain-text / link extraction.
  const markdownText = "| pipe demo |"

  const mockContext = {
    parent: { type: { name: "paragraph" } },
    depth: 1,
  } as any

  const parsed = clipboardPlugin.props?.clipboardTextParser?.(markdownText, mockContext, false)

  expect(parsed).not.toBeNull()
  let containsTable = false
  parsed?.content.forEach(node => {
    if (node.type.name === "table") containsTable = true
  })
  expect(containsTable).toBe(false)
})

test("clipboardTextParser returns proper slice with depth", () => {
  const markdownText = "## Heading\n\n**Bold text** with [link](https://example.com)"

  const mockContext = {
    parent: { type: { name: "paragraph" } },
    depth: 2,
  } as any

  const parsed = clipboardPlugin.props?.clipboardTextParser?.(markdownText, mockContext, false, null as any)

  expect(parsed).not.toBeNull()
  expect(parsed?.openStart).toBe(2) // Should use context depth
  expect(parsed?.openEnd).toBe(2) // Should use context depth

  // Should parse markdown and linkify
  let hasBlockContent = false
  let hasLinkMark = false

  parsed?.content.forEach(node => {
    if (node.isBlock) {
      hasBlockContent = true
    }
    if (node.isText && node.marks?.some(mark => mark.type.name === "link")) {
      hasLinkMark = true
    } else if (node.type.name === "paragraph") {
      node.content.forEach(child => {
        if (child.marks?.some(mark => mark.type.name === "link")) {
          hasLinkMark = true
        }
      })
    }
  })

  expect(hasBlockContent).toBe(true) // Should have block content
  expect(hasLinkMark).toBe(true) // Should preserve link marks
})

test("handlePaste handles blockquote insertion", () => {
  const mockView = {
    state: {
      selection: {
        empty: true,
        $from: {
          depth: 2,
          pos: 5,
          node: (depth: number) => {
            if (depth === 1) return { type: schema.nodes.blockquote }
            return { type: { name: "paragraph" } }
          },
        },
        $to: {
          depth: 2,
          pos: 10,
          node: (depth: number) => {
            if (depth === 1) return { type: schema.nodes.blockquote }
            return { type: { name: "paragraph" } }
          },
        },
      },
      tr: {
        replaceSelection: (slice: any) => ({
          scrollIntoView: () => ({ slice }),
        }),
      },
    },
    dispatch: (tr: any) => {
      return tr
    },
  } as any

  const mockSlice = new Slice(Fragment.empty, 0, 0)
  const pasteEvent = {} as ClipboardEvent

  // Should return true when handling blockquote insertion to prevent double paste
  const result = clipboardPlugin.props?.handlePaste?.(mockView, pasteEvent, mockSlice)
  expect(result).toBe(true) // Returns true to prevent default ProseMirror handling
})

test("clipboardTextParser extracts single paragraph content", () => {
  const simpleText = "Just some **bold** text with https://example.com"

  const mockContext = {
    parent: { type: { name: "paragraph" } },
    depth: 1,
  } as any

  const parsed = clipboardPlugin.props?.clipboardTextParser?.(simpleText, mockContext, false, null as any)

  expect(parsed).not.toBeNull()
  expect(parsed?.openStart).toBe(1) // Should use context depth
  expect(parsed?.openEnd).toBe(1) // Should use context depth

  // Should extract inline content for single paragraphs
  let hasBlockContent = false
  let hasInlineContent = false
  let hasLinkMark = false

  parsed?.content.forEach(node => {
    if (node.isBlock) {
      hasBlockContent = true
    }
    if (node.isText) {
      hasInlineContent = true
      if (node.marks?.some(mark => mark.type.name === "link")) {
        hasLinkMark = true
      }
    }
  })

  expect(hasBlockContent).toBe(false) // Should extract inline content from single paragraph
  expect(hasInlineContent).toBe(true) // Should have inline text
  expect(hasLinkMark).toBe(true) // Should linkify URLs
})

// HTML paste tests - these capture the bug where markdown pasted from VS Code/editors
// appears as raw text because the clipboard contains text/html which bypasses clipboardTextParser
describe("HTML paste handling (VS Code / text editor paste)", () => {
  test("transformPastedHTML should be defined to handle HTML paste", () => {
    // When pasting from VS Code/editors, clipboard has text/html
    // This test verifies that the plugin handles HTML paste
    expect(clipboardPlugin.props?.transformPastedHTML).toBeDefined()
  })

  test("HTML containing markdown text should be parsed as markdown", () => {
    // This simulates what VS Code puts in the clipboard when copying markdown
    // The HTML is just the text wrapped in basic tags
    const htmlFromVSCode = "<div>**Strong**</div>"

    const transformed = clipboardPlugin.props?.transformPastedHTML?.(htmlFromVSCode, null as any)

    // The HTML should be transformed to contain actual strong formatting
    // not raw asterisks
    expect(transformed).not.toContain("**Strong**")
    expect(transformed).toMatch(/<strong>|<b>/)
  })

  test("VS Code editor paste with cosmetic inline styles still parses as markdown", () => {
    // Real VS Code HTML clipboard output wraps code in a <div> with font-weight:normal
    // and other cosmetic styles. The rich-HTML guard must not misread these as rich
    // formatting and skip the markdown re-parse path.
    const htmlFromVSCode = `<div style="color: #d4d4d4;background-color: #1e1e1e;font-family: Menlo, Monaco, 'Courier New', monospace;font-weight: normal;font-size: 12px;line-height: 18px;white-space: pre;"><div><span style="color: #d4d4d4;"># Heading</span></div><div><span style="color: #d4d4d4;">**Bold text**</span></div></div>`

    const transformed = clipboardPlugin.props?.transformPastedHTML?.(htmlFromVSCode, null as any)

    expect(transformed).not.toContain("**Bold text**")
    expect(transformed).not.toContain("# Heading")
    expect(transformed).toMatch(/<h1>/)
    expect(transformed).toMatch(/<strong>/)
  })

  test("HTML paste with multi-line markdown should parse all formatting", () => {
    // This is the exact content from MARKDOWN_TEST_FILE.md wrapped in HTML
    // as VS Code would do when copying
    const markdownContent = `# Header one

## Header Two

*Italic*

**Strong**

\`inline-code\`

\`\`\`
code block
\`\`\``

    // VS Code typically wraps in pre or div tags
    const htmlFromVSCode = `<div>${markdownContent}</div>`

    const transformed = clipboardPlugin.props?.transformPastedHTML?.(htmlFromVSCode, null as any)

    // Should not contain raw markdown syntax
    expect(transformed).not.toContain("# Header one")
    expect(transformed).not.toContain("**Strong**")
    expect(transformed).not.toContain("*Italic*")

    // Should contain actual HTML formatting
    expect(transformed).toMatch(/<h1>|<h2>|<strong>|<em>|<code>/)
  })

  test("HTML paste should not create extra empty paragraphs", () => {
    // When markdown with \n\n separators is parsed as HTML,
    // it shouldn't create double spacing
    const markdownContent = `First paragraph

Second paragraph

Third paragraph`

    const htmlFromVSCode = `<div>${markdownContent}</div>`

    const transformed = clipboardPlugin.props?.transformPastedHTML?.(htmlFromVSCode, null as any)

    // Count paragraph elements - should have exactly 3, not 5 (with empties)
    const paragraphMatches = transformed?.match(/<p>/g) || []
    expect(paragraphMatches.length).toBeLessThanOrEqual(3)

    // Should not have empty paragraphs
    expect(transformed).not.toMatch(/<p>\s*<\/p>/)
  })

  test("HTML paste preserves actual HTML formatting from rich sources", () => {
    // When pasting from a rich HTML source (like a website),
    // the existing formatting should be preserved
    const richHtml = "<p>This is <strong>bold</strong> and <em>italic</em></p>"

    const transformed = clipboardPlugin.props?.transformPastedHTML?.(richHtml, null as any)

    // Rich HTML should pass through with formatting intact
    expect(transformed).toContain("<strong>bold</strong>")
    expect(transformed).toContain("<em>italic</em>")
  })

  test("transformPastedHTML preserves comment-highlight spans (dedup happens later in transformPasted)", () => {
    const htmlWithComment = `<p>Some <span class="inline-comment-highlight" data-comment-id="abc-123">highlighted text</span> here</p>`

    const transformed = clipboardPlugin.props?.transformPastedHTML?.(htmlWithComment, null as any)

    expect(transformed).toContain("inline-comment-highlight")
    expect(transformed).toContain('data-comment-id="abc-123"')
    expect(transformed).toContain("highlighted text")
    expect(transformed).toContain("Some")
    expect(transformed).toContain("here")
  })

  test("transformPastedHTML preserves multiple comment highlights (dedup happens later in transformPasted)", () => {
    const html = `<p><span class="inline-comment-highlight" data-comment-id="id-1">first</span> and <span class="inline-comment-highlight" data-comment-id="id-2">second</span></p>`

    const transformed = clipboardPlugin.props?.transformPastedHTML?.(html, null as any)

    expect(transformed).toContain('data-comment-id="id-1"')
    expect(transformed).toContain('data-comment-id="id-2"')
    expect(transformed).toContain("first")
    expect(transformed).toContain("second")
  })

  test("HTML without comment highlights passes through unchanged", () => {
    const richHtml = `<p>This is <strong>bold</strong> text</p>`

    const transformed = clipboardPlugin.props?.transformPastedHTML?.(richHtml, null as any)

    expect(transformed).toContain("<strong>bold</strong>")
  })

  test("Google Docs paste unwraps the non-bold wrapper <b> tag", () => {
    // Google Docs wraps all pasted content in <b id="docs-internal-guid-...">
    // with font-weight: normal. Without unwrapping, ProseMirror treats everything as bold.
    const googleDocsHtml = `<b id="docs-internal-guid-12a1fe6a-7fff-8d99-6435-67131a745278" style="font-weight: normal;"><p dir="ltr"><span style="font-weight: 700;">Nick</span></p><p dir="ltr"><span style="font-weight: 400;">Main focus: </span></p><p dir="ltr"><span style="font-weight: 400;">Asks/Blockers:</span></p></b>`

    const transformed = clipboardPlugin.props?.transformPastedHTML?.(googleDocsHtml, null as any)

    // The wrapper <b> should be removed so non-bold text isn't incorrectly bolded
    expect(transformed).not.toMatch(/<b[^r]/)
    // The inner content should still be present
    expect(transformed).toContain("Nick")
    expect(transformed).toContain("Main focus:")
    expect(transformed).toContain("Asks/Blockers:")
  })
})

describe("Google Docs paste formatting", () => {
  test("unwraps Google Docs redirect URLs to real destinations", () => {
    const html = `<meta charset='utf-8'><b id="docs-internal-guid-abc123" style="font-weight:normal;">
      <p dir="ltr" style="line-height:1.38;margin-top:0pt;margin-bottom:0pt;">
        <span style="font-size:11pt;font-family:Arial,sans-serif;">Check out </span>
        <a href="https://www.google.com/url?q=https%3A%2F%2Fexample.com&amp;sa=D&amp;source=editors&amp;ust=1700000000000000&amp;usg=AOvVaw0XYZ" style="text-decoration:none;">
          <span style="font-size:11pt;font-family:Arial,sans-serif;color:#1155cc;text-decoration:underline;">example link</span>
        </a>
      </p>
    </b>`

    const transformed = clipboardPlugin.props?.transformPastedHTML?.(html, null as any)

    expect(transformed).toMatch(/href="https:\/\/example\.com\/?"/)
    expect(transformed).not.toContain("google.com/url")
  })

  test("strips userinfo from unwrapped Google Docs redirect URLs", () => {
    // Defense against phishing payloads like https://trusted.com@evil.com/ — the
    // userinfo segment is dropped so the rewritten href can't impersonate a trusted host.
    const q = encodeURIComponent("https://user:pass@evil.example.com/path")
    const html = `<p><a href="https://www.google.com/url?q=${q}&amp;sa=D&amp;source=editors&amp;ust=1700000000000000">x</a></p>`

    const transformed = clipboardPlugin.props?.transformPastedHTML?.(html, null as any)

    expect(transformed).toContain('href="https://evil.example.com/path"')
    expect(transformed).not.toContain("user:pass@")
  })

  test("rejects javascript: protocol in Google Docs redirect URLs", () => {
    const q = encodeURIComponent("javascript:alert(1)")
    const html = `<p><a href="https://www.google.com/url?q=${q}&amp;sa=D&amp;source=editors">click</a></p>`

    const transformed = clipboardPlugin.props?.transformPastedHTML?.(html, null as any)

    // Original Google redirect is preserved (unwrap refuses non-http/https destinations)
    expect(transformed).not.toMatch(/href="javascript:/)
    expect(transformed).toContain("google.com/url")
  })

  test("unwraps Google redirect URLs with encoded special characters", () => {
    const html = `<meta charset='utf-8'><b id="docs-internal-guid-def456" style="font-weight:normal;">
      <p dir="ltr">
        <a href="https://www.google.com/url?q=https%3A%2F%2Fexample.com%2Fpath%3Ffoo%3Dbar%26baz%3Dqux%23section&amp;sa=D&amp;source=editors&amp;ust=1700000000000000&amp;usg=AOvVaw1ABC" style="text-decoration:none;">
          <span style="font-size:11pt;">complex link</span>
        </a>
      </p>
    </b>`

    const transformed = clipboardPlugin.props?.transformPastedHTML?.(html, null as any)

    expect(transformed).toMatch(/href="https:\/\/example\.com\/path\?foo=bar&amp;baz=qux#section"/)
    expect(transformed).not.toContain("google.com/url")
  })

  test("leaves original href when Google redirect URL has no q parameter", () => {
    const html = `<meta charset='utf-8'><b id="docs-internal-guid-ghi789" style="font-weight:normal;">
      <p dir="ltr">
        <a href="https://www.google.com/url?sa=D&amp;source=editors" style="text-decoration:none;">
          <span style="font-size:11pt;">link</span>
        </a>
      </p>
    </b>`

    const transformed = clipboardPlugin.props?.transformPastedHTML?.(html, null as any)

    expect(transformed).toContain("google.com/url?sa=D")
  })

  test("does not unwrap Google URLs missing sa=D or source=editors params", () => {
    const html = `<p><a href="https://www.google.com/url?q=https%3A%2F%2Fexample.com">link</a></p>`

    const transformed = clipboardPlugin.props?.transformPastedHTML?.(html, null as any)

    expect(transformed).toContain("google.com/url?q=")
  })

  test("rich Google Docs HTML with markdown-like text is not re-parsed as markdown", () => {
    // Google Docs HTML with bold formatting AND text that matches MARKDOWN_PATTERNS.
    // The paragraph "- Overview of Q1 results" starts with "- " which matches ^\s*[-*]\s
    const html = `<meta charset='utf-8'><b id="docs-internal-guid-jkl012" style="font-weight:normal;">
      <p dir="ltr" style="line-height:1.38;margin-top:0pt;margin-bottom:0pt;">
        <span style="font-size:11pt;font-family:Arial,sans-serif;color:#000000;background-color:transparent;font-weight:700;font-style:normal;">Project Update</span>
      </p>
      <p dir="ltr" style="line-height:1.38;margin-top:0pt;margin-bottom:0pt;">
        <span style="font-size:11pt;font-family:Arial,sans-serif;color:#000000;background-color:transparent;font-weight:400;font-style:italic;">- Overview of Q1 results</span>
      </p>
    </b>`

    const transformed = clipboardPlugin.props?.transformPastedHTML?.(html, null as any)

    // The rich HTML formatting should be preserved, NOT converted to markdown-parsed output
    expect(transformed).toContain("font-weight")
    expect(transformed).toContain("font-style")
    // The text content should still be there
    expect(transformed).toContain("Project Update")
    expect(transformed).toContain("Overview of Q1 results")
  })

  test("plain HTML with markdown text is still parsed as markdown", () => {
    // VS Code style: plain div wrapping markdown text, no rich formatting tags
    const html = `<div># Heading\n\n**Bold text**</div>`

    const transformed = clipboardPlugin.props?.transformPastedHTML?.(html, null as any)

    // Markdown should be parsed into proper HTML elements
    expect(transformed).toMatch(/<h1>/)
    expect(transformed).toMatch(/<strong>/)
  })

  test("rewrites Google Docs role=checkbox list items to <input type=checkbox>", () => {
    // Uses a real clipboard payload captured from Google Docs (googleDocsPaste fixture)
    // with one unchecked and one checked item. Google Docs emits each <li> with a
    // decorative <img> first child (different PNGs for each state); our rewriter drops
    // the img and inserts <input type="checkbox" [checked]>.
    const transformed = clipboardPlugin.props?.transformPastedHTML?.(googleDocsPaste, null as any)

    // Both items become <input type="checkbox"> first children of their <li>
    const inputs = transformed?.match(/<input type="checkbox"[^>]*>/g) || []
    expect(inputs).toHaveLength(2)
    // Exactly one carries the `checked` attribute (the checked item)
    expect(inputs.filter(m => /\bchecked\b/.test(m))).toHaveLength(1)
    // The decorative PNGs for both states are gone
    expect(transformed).not.toContain("data:image/png")
    // Text content from both items survives
    expect(transformed).toContain("Unchecked")
    expect(transformed).toContain("Checked")
  })

  test("preserves bold and italic formatting from Google Docs", () => {
    const html = `<meta charset='utf-8'><b id="docs-internal-guid-pqr678" style="font-weight:normal;">
      <p dir="ltr" style="line-height:1.38;margin-top:0pt;margin-bottom:0pt;">
        <span style="font-size:11pt;font-family:Arial,sans-serif;color:#000000;background-color:transparent;font-weight:700;font-style:normal;font-variant:normal;text-decoration:none;vertical-align:baseline;white-space:pre-wrap;">bold text</span>
        <span style="font-size:11pt;font-family:Arial,sans-serif;color:#000000;background-color:transparent;font-weight:400;font-style:italic;font-variant:normal;text-decoration:none;vertical-align:baseline;white-space:pre-wrap;">italic text</span>
      </p>
    </b>`

    const transformed = clipboardPlugin.props?.transformPastedHTML?.(html, null as any)

    expect(transformed).toMatch(/font-weight:\s*700/)
    expect(transformed).toMatch(/font-style:\s*italic/)
    expect(transformed).toContain("bold text")
    expect(transformed).toContain("italic text")
  })

  test("preserves heading levels from Google Docs", () => {
    const html = `<meta charset='utf-8'><b id="docs-internal-guid-stu901" style="font-weight:normal;">
      <h2 dir="ltr" style="line-height:1.38;margin-top:18pt;margin-bottom:6pt;">
        <span style="font-size:16pt;font-family:Arial,sans-serif;font-weight:400;">Section Title</span>
      </h2>
      <h3 dir="ltr" style="line-height:1.38;margin-top:16pt;margin-bottom:4pt;">
        <span style="font-size:13.999999999999998pt;font-family:Arial,sans-serif;font-weight:400;">Subsection</span>
      </h3>
    </b>`

    const transformed = clipboardPlugin.props?.transformPastedHTML?.(html, null as any)

    expect(transformed).toContain("<h2")
    expect(transformed).toContain("<h3")
    expect(transformed).toContain("Section Title")
    expect(transformed).toContain("Subsection")
  })

  test("preserves nested lists from Google Docs", () => {
    // Google Docs emits nested lists as invalid HTML where the inner <ul> is a sibling
    // of the outer <li>, not a child. The clipboard transform must rewrite this into
    // the W3C-valid nested form so ProseMirror's parser produces a nested list rather
    // than flattening the items.
    const markdown = pasteToMarkdown(googleDocsNestedListPaste)

    // Inner items must be indented (nested) — they should appear right after "Item 2"
    // with leading whitespace before the bullet character.
    expect(markdown).toMatch(/\* Item 2\n\s+[*-]\s+Indented item 1/)
    expect(markdown).toMatch(/\s+[*-]\s+Indented item 2/)

    // Inner items must NOT appear as top-level bullets (no leading whitespace).
    expect(markdown).not.toMatch(/^[*-]\s+Indented item 1/m)
    expect(markdown).not.toMatch(/^[*-]\s+Indented item 2/m)

    // Outer items should still be top-level bullets.
    expect(markdown).toMatch(/^[*-]\s+List item 1/m)
    expect(markdown).toMatch(/^[*-]\s+Item 2/m)
    expect(markdown).toMatch(/^[*-]\s+Last bullet/m)
  })

  test("orphan nested list with no preceding <li> is left intact (no crash)", () => {
    // If a list is the first child of its UL/OL parent — `<ul><ul><li>orphan</li></ul></ul>`
    // — there's no preceding <li> to reattach the inner list into. The reattach must
    // skip rather than crash. Real Google Docs doesn't emit this, but locking down
    // the skip behavior prevents silent regressions.
    const html = `<ul><ul><li>orphan</li></ul></ul>`
    expect(() => clipboardPlugin.props?.transformPastedHTML?.(html, null as any)).not.toThrow()
    const transformed = clipboardPlugin.props?.transformPastedHTML?.(html, null as any) ?? ""
    expect(transformed).toContain("orphan")
  })

  test("block-trailing hard break from paste is dropped at serialize time (idempotent)", () => {
    // Google Docs emits <br /> between block elements. ProseMirror's parser absorbs these
    // as trailing hard_breaks on the preceding paragraph. The serializer must drop them so
    // the first save's markdown round-trips cleanly (no double-backslash on re-edit).
    const htmlWithBlockBr = `<meta charset='utf-8'><b id="docs-internal-guid-br-test" style="font-weight:normal;"><p dir="ltr">X</p><br /><ul><li dir="ltr"><p dir="ltr" role="presentation"><span>item</span></p></li></ul></b>`
    const md = pasteToMarkdown(htmlWithBlockBr)

    // The trailing hard_break is dropped — no backslash at the paragraph/list boundary.
    expect(md).not.toContain("X\\")
    // Round-trip is idempotent: re-parsing and re-serializing produces the same bytes.
    expect(serialize(parse(md))).toBe(md)
  })

  test("inter-block <br /> separators become single blank lines (not extra spacing, not zero)", () => {
    // Google Docs uses `<br />` siblings between blocks as visible blank-line separators.
    // The cleanup replaces each with an empty paragraph so the gap is exactly one blank
    // line — not the multi-line gap that `paragraph(hard_break)` produced before, and
    // not zero spacing if we just stripped them.
    const html = `<meta charset='utf-8'><b id="docs-internal-guid-spacing" style="font-weight:normal;"><p dir="ltr">first</p><br /><p dir="ltr">second</p><br /><br /><p dir="ltr">third</p></b>`
    const transformed = clipboardPlugin.props?.transformPastedHTML?.(html, null as any) ?? ""

    // Each inter-block <br /> is replaced with an empty <p>; none survive as <br>.
    expect(transformed).not.toMatch(/<\/p>\s*<br/i)
    expect(transformed).not.toMatch(/<br[^>]*>\s*<p/i)
    // Two `<br />`s between second and third produce two empty paragraphs.
    expect(transformed.match(/<p[^>]*>\s*<\/p>/g)?.length ?? 0).toBeGreaterThanOrEqual(3)

    // Round-trip preserves the structure as blank lines between content paragraphs.
    const md = pasteToMarkdown(html)
    expect(md).toContain("first")
    expect(md).toContain("second")
    expect(md).toContain("third")
    expect(serialize(parse(md))).toBe(md)
  })

  test("inline <br /> inside a paragraph is preserved (Shift+Enter line breaks)", () => {
    // The inter-block <br /> cleanup must not touch <br />s used as soft line breaks
    // inside a paragraph — those siblings are inline content, not blocks.
    const html = `<meta charset='utf-8'><b id="docs-internal-guid-inline-br" style="font-weight:normal;"><p dir="ltr"><span>line one</span><br /><span>line two</span></p></b>`
    const transformed = clipboardPlugin.props?.transformPastedHTML?.(html, null as any) ?? ""

    expect(transformed).toMatch(/line one[\s\S]*<br[^>]*>[\s\S]*line two/i)
  })

  test("preserves strikethrough formatting from Google Docs", () => {
    const html = `<meta charset='utf-8'><b id="docs-internal-guid-yza567" style="font-weight:normal;">
      <p dir="ltr" style="line-height:1.38;margin-top:0pt;margin-bottom:0pt;">
        <span style="font-size:11pt;font-family:Arial,sans-serif;color:#000000;background-color:transparent;font-weight:400;font-style:normal;font-variant:normal;text-decoration:line-through;vertical-align:baseline;white-space:pre-wrap;">struck</span>
      </p>
    </b>`

    const transformed = clipboardPlugin.props?.transformPastedHTML?.(html, null as any)

    expect(transformed).toMatch(/text-decoration:\s*line-through/)
    expect(transformed).toContain("struck")
  })

  test("unwraps multiple Google redirect URLs in the same paste", () => {
    const html = `<meta charset='utf-8'><b id="docs-internal-guid-bcd890" style="font-weight:normal;">
      <p dir="ltr" style="line-height:1.38;margin-top:0pt;margin-bottom:0pt;">
        <a href="https://www.google.com/url?q=https%3A%2F%2Ffirst.example.com&amp;sa=D&amp;source=editors&amp;ust=1700000000000000&amp;usg=AOvVaw0AAA" style="text-decoration:none;">
          <span style="font-size:11pt;font-family:Arial,sans-serif;color:#1155cc;text-decoration:underline;">first link</span>
        </a>
        <span style="font-size:11pt;font-family:Arial,sans-serif;"> and </span>
        <a href="https://www.google.com/url?q=https%3A%2F%2Fsecond.example.com&amp;sa=D&amp;source=editors&amp;ust=1700000000000001&amp;usg=AOvVaw0BBB" style="text-decoration:none;">
          <span style="font-size:11pt;font-family:Arial,sans-serif;color:#1155cc;text-decoration:underline;">second link</span>
        </a>
      </p>
    </b>`

    const transformed = clipboardPlugin.props?.transformPastedHTML?.(html, null as any)

    expect(transformed).toMatch(/href="https:\/\/first\.example\.com\/?"/)
    expect(transformed).toMatch(/href="https:\/\/second\.example\.com\/?"/)
    expect(transformed).not.toContain("google.com/url")
  })

  test("empty Google Docs wrapper paste produces no output", () => {
    // Edge case: pasting an all-whitespace Google Docs wrapper must not throw
    // or emit junk nodes.
    const html = `<meta charset='utf-8'><b id="docs-internal-guid-empty" style="font-weight:normal;">   </b>`

    const transformed = clipboardPlugin.props?.transformPastedHTML?.(html, null as any)
    expect(() => clipboardPlugin.props?.transformPastedHTML?.("", null as any)).not.toThrow()
    expect(transformed).toBeDefined()
    expect(transformed).not.toContain("<b ")
  })

  test("combined inline marks on same run survive the paste", () => {
    // Bold + italic on one span, bold-linked text on another — both should land as
    // inline marks rather than element soup.
    const html = `<b id="docs-internal-guid-mixed" style="font-weight:normal;"><p dir="ltr"><span style="font-weight:700;font-style:italic;">bold italic</span><span style="font-weight:400;"> then </span><a href="https://example.com"><span style="font-weight:700;color:#1155cc;">bold link</span></a></p></b>`

    const markdown = pasteToMarkdown(html)

    // Bold+italic collapses to the triple-star form
    expect(markdown).toMatch(/\*\*\*bold italic\*\*\*/)
    // Link survives with its href; bold on link text is also preserved
    expect(markdown).toMatch(/\[\*?\*?bold link\*?\*?\]\(https:\/\/example\.com\)/)
  })

  test("bulleted list from Google Docs serializes as a tight markdown list", () => {
    // Spec Edge Case 13: tight-vs-loose list serialization. Google Docs emits
    // <li><p><span>...</span></p></li>; the round-trip must yield a tight list
    // (no blank line between items), whichever bullet character the serializer uses.
    const html = `<b id="docs-internal-guid-tight" style="font-weight:normal;"><ul style="margin-top:0;margin-bottom:0;padding-inline-start:48px;"><li dir="ltr" aria-level="1"><p dir="ltr" role="presentation"><span>alpha</span></p></li><li dir="ltr" aria-level="1"><p dir="ltr" role="presentation"><span>bravo</span></p></li></ul></b>`

    const markdown = pasteToMarkdown(html).trim()

    expect(markdown).toMatch(/^[-*]\s+alpha\n[-*]\s+bravo$/)
    expect(markdown).not.toMatch(/alpha\n\n[-*]\s+bravo/)
  })

  test("full captured Google Docs paste preserves every supported formatting type", () => {
    // Round-trip assertion over the whole fixture. Covers <h1>, paragraphs, blank-line
    // separators, checklist, bullet list, numbered list, and inline bold/italic runs.
    // (The underline run is intentionally dropped — underline is not in the schema.)
    const markdown = pasteToMarkdown(googleDocsPaste)

    expect(markdown).toMatch(/^#\s+Heading 1/m)
    expect(markdown).toMatch(/This is my main text\./)
    expect(markdown).toMatch(/This is after two lines\./)
    // Checklist items become task_list_item markdown with proper checked state
    expect(markdown).toMatch(/\[\s\]\s+Unchecked/)
    expect(markdown).toMatch(/\[x\]\s+.*Checked/)
    // Bullet list with "One" and "Two" as separate tight items
    expect(markdown).toMatch(/^[-*]\s+One\n[-*]\s+Two/m)
    // Numbered list with "One" and "Two"
    expect(markdown).toMatch(/^1\.\s+One\n2\.\s+Two/m)
    // Inline marks survive: bold and italic
    expect(markdown).toMatch(/\*\*Bold\*\*/)
    expect(markdown).toMatch(/\*italic\*/)
    // Underline is not in the schema, so the underlined run drops to plain text
    expect(markdown).toMatch(/\bunderline\b/)
  })
})

// Issue #8872: markdown pasted with a text/html sibling (which browsers and editors synthesize
// for most copies) took the transformPastedHTML branch, where detection was too narrow and
// length-capped — so blockquotes, thematic breaks, links, task lists, and large pastes landed
// as escaped raw text (\##, \*\*, \>) instead of formatting. The plain-text clipboardTextParser
// branch always formatted these, so the two paths had drifted apart. These lock the parity.
describe("markdown paste detection (issue #8872)", () => {
  // A plain (non-rich) HTML wrapper is what a raw-markdown copy carries as its text/html sibling.
  const wrap = (md: string) => `<div>${md.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/\n/g, "<br>")}</div>`

  test("blockquote-only markdown formats", () => {
    const md = pasteToMarkdown(wrap("> quoted line one\n> quoted line two"))
    expect(md).toMatch(/^>\s+quoted line one/m)
    expect(md).not.toMatch(/\\>/)
  })

  test("thematic break + link formats", () => {
    const md = pasteToMarkdown(wrap("See [the doc](https://example.com)\n\n---\n\nEnd."))
    expect(md).toMatch(/\[the doc\]\(https:\/\/example\.com\)/)
    // The --- becomes a horizontal rule, not escaped literal dashes.
    expect(md).not.toMatch(/\\-\\-\\-/)
  })

  test("task list formats as a list, not escaped text", () => {
    // Checkbox state fidelity through the paste round-trip is a separate, pre-existing
    // toDOM/parseDOM concern; here we only assert the item is detected and formatted as a
    // list rather than surviving as escaped literal "\- \[ \] todo item".
    const md = pasteToMarkdown(wrap("- [ ] todo item\n- [x] done item"))
    expect(md).toMatch(/^[-*+]\s+.*todo item/m)
    expect(md).not.toMatch(/\\-\s*\\\[/)
  })

  test("strikethrough formats", () => {
    const md = pasteToMarkdown(wrap("this is ~~struck~~ text"))
    expect(md).toMatch(/~~struck~~/)
    expect(md).not.toMatch(/\\~\\~/)
  })

  test("plus-sign bullets format", () => {
    const md = pasteToMarkdown(wrap("+ first\n+ second"))
    expect(md).toMatch(/^[-*+]\s+first/m)
    expect(md).toMatch(/^[-*+]\s+second/m)
  })

  test("large (>100KB) markdown paste still formats (no length cap)", () => {
    // Detection used to give up above 100,000 chars, so content just over the cap landed as
    // escaped raw text. Built from a few large blocks (not thousands of <br>s) so the assertion
    // exercises the no-cap path without hitting jsdom's O(n^2) node-serialization cost.
    const big = "## Big Heading\n\n" + "word ".repeat(21_000) + "\n\n**end bold text**"
    expect(big.length).toBeGreaterThan(100_000)
    const out = clipboardPlugin.props?.transformPastedHTML?.(wrap(big), null as any) ?? ""
    expect(out).toMatch(/<h2/)
    expect(out).toMatch(/<strong>end bold text<\/strong>/)
    expect(out).not.toContain("## Big Heading")
  })

  test("markdown detection stays linear on adversarial input (no ReDoS freeze)", () => {
    // A run of "[(" with no closing bracket makes an unbounded link pattern backtrack O(n^2)
    // and freeze the tab; the bounded {1,200} quantifiers keep it linear. The original guard
    // timed a multi-MB input against a 2s budget, but that input takes ~2s of HTML parsing even
    // when healthy — a 1× margin that flakes under CI load. A 40k-char input keeps the healthy
    // path well under 200ms (the regex itself is ~8ms; the rest is HTML parsing) while an
    // unbounded regression backtracks for ~2.7s on the same input. A 1s threshold sits in that
    // wide gap: it never trips on the healthy path, even under contention, but a regression
    // blows straight through it.
    const hostile = `<div>${"[(".repeat(20_000)}</div>`
    const transform = clipboardPlugin.props?.transformPastedHTML

    // Warm up so JIT/first-parse cost doesn't land on the measured call.
    transform?.(hostile, null as any)

    const start = performance.now()
    const out = transform?.(hostile, null as any)
    const elapsed = performance.now() - start

    expect(out).toBeDefined()
    expect(elapsed).toBeLessThan(1000)
  })

  test("plain prose with an HTML wrapper is not mangled", () => {
    // No markdown markers: passes through untouched, no accidental escaping or reflow.
    const md = pasteToMarkdown(wrap("Just an ordinary sentence with no formatting at all."))
    expect(md).toContain("Just an ordinary sentence with no formatting at all.")
  })

  test("structural HTML table is preserved, not flattened to text", () => {
    // A bare HTML table (no other rich tags) must parse as a table via the DOM path, not get
    // run through extractTextFromHtml -> markdown re-parse, which would destroy its structure.
    const html = `<table><thead><tr><th>Name</th><th>Role</th></tr></thead><tbody><tr><td>Alice</td><td>Dev</td></tr></tbody></table>`
    const md = pasteToMarkdown(html)
    expect(md).toMatch(/\|\s*Name\s*\|/)
    expect(md).toMatch(/\|\s*Alice\s*\|/)
  })

  test("structural HTML image is preserved, not flattened to text", () => {
    const html = `<div><img src="https://example.com/pic.png" alt="a picture"></div>`
    const md = pasteToMarkdown(html)
    expect(md).toContain("https://example.com/pic.png")
  })
})

describe("comment mark deduplication", () => {
  // Build a Slice from raw HTML (mirrors ProseMirror's clipboard parsing path).
  function sliceFromHtml(html: string): Slice {
    const container = document.createElement("div")
    container.innerHTML = html
    return ProseMirrorDOMParser.fromSchema(schema).parseSlice(container)
  }

  // Parse HTML into a full doc — used to seed the destination doc with existing comment marks.
  function docFromHtml(html: string) {
    const container = document.createElement("div")
    container.innerHTML = html
    return ProseMirrorDOMParser.fromSchema(schema).parse(container)
  }

  // Mock just enough of EditorView for transformPasted: it only reads view.state.doc.
  function mockViewWithDoc(d: ReturnType<typeof docFromHtml>): any {
    return { state: EditorState.create({ schema, doc: d }) }
  }

  // Walk a Slice and collect every commentId mark attached to text nodes.
  function commentIdsInSlice(slice: Slice): string[] {
    const ids: string[] = []
    slice.content.descendants(node => {
      for (const mark of node.marks) {
        if (mark.type.name === "comment") ids.push(mark.attrs.commentId as string)
      }
    })
    return ids
  }

  // Find the first text node in a Slice whose text matches `text` and return its comment-mark ids.
  function commentIdsOnText(slice: Slice, text: string): string[] {
    const ids: string[] = []
    slice.content.descendants(node => {
      if (node.isText && node.text === text) {
        for (const mark of node.marks) {
          if (mark.type.name === "comment") ids.push(mark.attrs.commentId as string)
        }
      }
    })
    return ids
  }

  test("preserves comment mark when commentId is absent from dest doc (cut+paste)", () => {
    const destDoc = docFromHtml("<p>plain destination text</p>")
    const view = mockViewWithDoc(destDoc)
    const slice = sliceFromHtml(
      `<p><span class="inline-comment-highlight" data-comment-id="abc-123">highlighted text</span></p>`
    )

    const result = clipboardPlugin.props?.transformPasted?.(slice, view)

    expect(result).toBeDefined()
    expect(commentIdsInSlice(result!)).toContain("abc-123")
    expect(commentIdsOnText(result!, "highlighted text")).toEqual(["abc-123"])
  })

  test("strips comment mark when commentId already exists in dest doc (copy+paste)", () => {
    const destDoc = docFromHtml(
      `<p><span class="inline-comment-highlight" data-comment-id="abc-123">existing text</span></p>`
    )
    const view = mockViewWithDoc(destDoc)
    const slice = sliceFromHtml(
      `<p><span class="inline-comment-highlight" data-comment-id="abc-123">highlighted text</span></p>`
    )

    const result = clipboardPlugin.props?.transformPasted?.(slice, view)

    expect(result).toBeDefined()
    expect(commentIdsInSlice(result!)).not.toContain("abc-123")
    expect(commentIdsOnText(result!, "highlighted text")).toEqual([])
  })

  test("handles mixed marks — strips duplicate, preserves novel", () => {
    const destDoc = docFromHtml(
      `<p><span class="inline-comment-highlight" data-comment-id="existing-id">already here</span></p>`
    )
    const view = mockViewWithDoc(destDoc)
    const slice = sliceFromHtml(
      `<p><span class="inline-comment-highlight" data-comment-id="existing-id">first</span><span class="inline-comment-highlight" data-comment-id="new-id">second</span></p>`
    )

    const result = clipboardPlugin.props?.transformPasted?.(slice, view)

    expect(result).toBeDefined()
    expect(commentIdsOnText(result!, "first")).toEqual([])
    expect(commentIdsOnText(result!, "second")).toEqual(["new-id"])
  })

  test("HTML without comment highlights passes through transformPasted unchanged", () => {
    const destDoc = docFromHtml("<p>any destination</p>")
    const view = mockViewWithDoc(destDoc)
    const slice = sliceFromHtml(`<p><strong>bold text</strong></p>`)

    const result = clipboardPlugin.props?.transformPasted?.(slice, view)

    expect(result).toBeDefined()
    // No comment marks anywhere in the slice
    expect(commentIdsInSlice(result!)).toEqual([])
    // Strong mark on "bold text" is preserved
    let foundBold = false
    result!.content.descendants(node => {
      if (
        node.isText &&
        node.text === "bold text" &&
        node.marks.some(m => m.type.name === "strong" || m.type.name === "bold")
      ) {
        foundBold = true
      }
    })
    expect(foundBold).toBe(true)
  })

  test("strips comment mark on text nested inside a list item", () => {
    const destDoc = docFromHtml(
      `<p><span class="inline-comment-highlight" data-comment-id="nested-id">already here</span></p>`
    )
    const view = mockViewWithDoc(destDoc)
    const slice = sliceFromHtml(
      `<ul><li><span class="inline-comment-highlight" data-comment-id="nested-id">list item text</span></li></ul>`
    )

    const result = clipboardPlugin.props?.transformPasted?.(slice, view)

    expect(result).toBeDefined()
    expect(commentIdsInSlice(result!)).not.toContain("nested-id")
    expect(commentIdsOnText(result!, "list item text")).toEqual([])
  })

  test("preserves comment mark on text nested inside a list item when id is absent", () => {
    const destDoc = docFromHtml("<p>plain destination text</p>")
    const view = mockViewWithDoc(destDoc)
    const slice = sliceFromHtml(
      `<ul><li><span class="inline-comment-highlight" data-comment-id="nested-id">list item text</span></li></ul>`
    )

    const result = clipboardPlugin.props?.transformPasted?.(slice, view)

    expect(result).toBeDefined()
    expect(commentIdsInSlice(result!)).toContain("nested-id")
    expect(commentIdsOnText(result!, "list item text")).toEqual(["nested-id"])
  })
})
