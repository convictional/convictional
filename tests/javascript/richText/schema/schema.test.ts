import { afterEach, expect, test, describe, vi } from "vitest"
import { builders } from "prosemirror-test-builder"
import { schema, serialize, parse, plugins } from "../../../../app/javascript/richText/schema"

const {
  doc,
  paragraph,
  heading,
  link,
  mention,
  hard_break,
  image,
  code,
  ordered_list,
  bullet_list,
  regular_list_item: list_item,
  blockquote,
  code_block,
  quoted_html,
  table,
  table_row,
  table_cell,
  table_header,
  strong,
  em,
  strikethrough,
  task_list_item,
} = builders(schema)

function assert_equal(doc: any, markdown: string) {
  const doc_in_markdown = serialize(doc)
  const markdown_as_doc = parse(markdown)

  expect(doc).toEqual(markdown_as_doc)
  expect(doc_in_markdown).toBe(markdown)
}

afterEach(() => {
  vi.restoreAllMocks()
})

test("Basic markdown", () => {
  assert_equal(doc(paragraph("hello world")), "hello world\n")

  assert_equal(
    doc(
      heading({ level: 1 }, "Test"),
      paragraph("This is a test document. It has a ", link({ href: "https://example.com" }, "link"), ".")
    ),
    `# Test

This is a test document. It has a [link](https://example.com).
`
  )
})

test("Lists", () => {
  // Some bulleted and ordered lists with nesting
  assert_equal(
    doc(
      bullet_list(
        list_item(
          paragraph("This is a bullet list item."),
          ordered_list(
            list_item(paragraph("This is a nested ordered list item ", code("with some code"))),
            list_item(paragraph("This is another nested ordered list item."))
          )
        ),
        list_item(
          paragraph("This is another bullet list item."),
          bullet_list(
            list_item(paragraph("This is a nested bullet list item.")),
            list_item(paragraph("This is another nested bullet list item."))
          )
        )
      )
    ),
    `* This is a bullet list item.
  1. This is a nested ordered list item \`with some code\`
  2. This is another nested ordered list item.
* This is another bullet list item.
  * This is a nested bullet list item.
  * This is another nested bullet list item.
`
  )
})

test("Mentions and hard breaks", () => {
  assert_equal(
    doc(
      paragraph(
        "Hey ",
        mention({ id: "", name: "John Doe", email: "" }),
        " look at this.",
        hard_break(),
        "This is a test document."
      )
    ),
    `Hey @[John Doe] look at this.\\
This is a test document.
`
  )
})

test("Blockquotes, nesting", () => {
  assert_equal(
    doc(
      blockquote(
        paragraph("This is a blockquote."),
        ordered_list(
          { spread: true },
          list_item(
            paragraph("This is a nested ordered list item in a blockquote."),
            bullet_list(
              list_item(paragraph("This is a nested bullet list item in a blockquote.")),
              list_item(paragraph("This is another nested bullet list item in a blockquote."))
            )
          ),
          list_item(paragraph("This is another nested ordered list item in a blockquote."))
        ),
        blockquote(paragraph("This is a nested blockquote."))
      )
    ),
    `> This is a blockquote.
>
> 1. This is a nested ordered list item in a blockquote.
>
>    * This is a nested bullet list item in a blockquote.
>    * This is another nested bullet list item in a blockquote.
>
> 2. This is another nested ordered list item in a blockquote.
>
> > This is a nested blockquote.
`
  )
})

test("Tab characters in paragraph text", () => {
  // Mid-line literal tab is serialized verbatim
  assert_equal(doc(paragraph("hello\tworld")), "hello\tworld\n")
  // Leading tab is serialized as &#x9; to avoid CommonMark indented-code-block rule
  assert_equal(doc(paragraph("\thello")), "&#x9;hello\n")
  // Leading tab inside blockquote — same escape strategy with blockquote prefix
  assert_equal(doc(blockquote(paragraph("\thello"))), "> &#x9;hello\n")
})

test("Images", () => {
  assert_equal(
    doc(paragraph(image({ src: "https://example.com/image.jpg", alt: "An example image" }), " This is an image.")),
    `![An example image](https://example.com/image.jpg) This is an image.
`
  )
})

test("Standalone image stays in position between paragraphs", () => {
  // CommonMark wraps a bare image on its own line in a paragraph, so prosemirror-unified
  // never has to fit an inline image node at the block-level document root. This guards
  // against a dependency bump regressing that: a hoisted image would land at the end.
  const parsed = parse("paragraph one\n\n![](https://example.com/x.jpg)\n\nparagraph two\n")

  expect(parsed).toEqual(
    doc(
      paragraph("paragraph one"),
      paragraph(image({ src: "https://example.com/x.jpg", alt: "" })),
      paragraph("paragraph two")
    )
  )
})

test("Code blocks", () => {
  assert_equal(
    doc(code_block("This is a code block.\nIt has multiple lines.\n")),
    `\`\`\`
This is a code block.
It has multiple lines.

\`\`\`
`
  )
})

test("Empty code blocks", () => {
  // Test that empty code blocks can be parsed and serialized correctly
  // This is a regression test for an issue where ProseMirror failed to
  // initialize when the input contained an empty code block
  const emptyCodeBlockMarkdown = "```\n```\n"

  // Should parse without throwing
  expect(() => parse(emptyCodeBlockMarkdown)).not.toThrow()

  const parsed = parse(emptyCodeBlockMarkdown)

  // Should create a valid document with a code_block node
  expect(parsed.content.childCount).toBe(1)
  expect(parsed.content.firstChild?.type.name).toBe("code_block")

  // Should serialize back to the same markdown format
  const serialized = serialize(parsed)
  expect(serialized).toBe(emptyCodeBlockMarkdown)
})

test("Empty code blocks with surrounding content", () => {
  // Test empty code blocks within larger documents
  const markdownWithEmptyCodeBlock = `Some text before

\`\`\`
\`\`\`

Some text after
`

  // Should parse without throwing
  expect(() => parse(markdownWithEmptyCodeBlock)).not.toThrow()

  const parsed = parse(markdownWithEmptyCodeBlock)

  // Should create paragraphs and code block
  expect(parsed.content.childCount).toBe(3)
  expect(parsed.content.child(0).type.name).toBe("paragraph")
  expect(parsed.content.child(1).type.name).toBe("code_block")
  expect(parsed.content.child(2).type.name).toBe("paragraph")
})

test("Empty inline code is removed from documents", () => {
  const markdownWithNormalInlineCode = "Some `code` here\n"

  expect(() => parse(markdownWithNormalInlineCode)).not.toThrow()

  const parsed = parse(markdownWithNormalInlineCode)
  expect(parsed.content.firstChild?.type.name).toBe("paragraph")
})

test("Multiple empty code blocks in sequence", () => {
  const multipleEmptyCodeBlocks = "```\n```\n\n```\n```\n"

  expect(() => parse(multipleEmptyCodeBlocks)).not.toThrow()

  const parsed = parse(multipleEmptyCodeBlocks)
  expect(parsed.content.childCount).toBe(2)
  expect(parsed.content.child(0).type.name).toBe("code_block")
  expect(parsed.content.child(1).type.name).toBe("code_block")
})

test("Empty code block with language specifier", () => {
  const emptyCodeBlockWithLang = "```javascript\n```\n"

  expect(() => parse(emptyCodeBlockWithLang)).not.toThrow()

  const parsed = parse(emptyCodeBlockWithLang)
  expect(parsed.content.childCount).toBe(1)
  expect(parsed.content.firstChild?.type.name).toBe("code_block")
  expect(parsed.content.firstChild?.attrs.params).toBe("javascript")
})

test("Complex document with empty code blocks", () => {
  const complexDoc = `# Title

Some intro text.

\`\`\`
\`\`\`

More text here.

\`\`\`python
print("hello")
\`\`\`

\`\`\`
\`\`\`

Final paragraph.
`

  expect(() => parse(complexDoc)).not.toThrow()

  const parsed = parse(complexDoc)
  // Should have: heading, para, empty code, para, code with content, empty code, para
  expect(parsed.content.childCount).toBe(7)
})

test("Empty paragraphs", () => {
  assert_equal(
    doc(
      paragraph("This is a test document."),
      paragraph(""),
      paragraph("This is another paragraph."),
      paragraph("This is a third paragraph.")
    ),
    `This is a test document.

<br />

This is another paragraph.

This is a third paragraph.
`
  )

  // A lone empty paragraph (a blank document) serializes to <br />, not "" — the
  // fix for a one-blank-line doc rendering as nothing. Blank-composer emptiness is
  // handled by isBlankMarkdown, not by this collapsing to "".
  assert_equal(doc(paragraph("")), "<br />\n")
})

test("Quoted HTML directive", () => {
  // prosemirror-unified warns for raw HTML nodes it can't map to ProseMirror;
  // quoted_html stores them as an attribute, so the warning is expected here.
  vi.spyOn(console, "warn").mockImplementation(() => {})

  // Test basic quoted HTML directive
  assert_equal(
    doc(
      paragraph("This is before the directive."),
      quoted_html({ htmlContent: "<p>This is HTML content</p>" }),
      paragraph("This is after the directive.")
    ),
    `This is before the directive.

:::quoted_html
<p>This is HTML content</p>
:::

This is after the directive.
`
  )

  // Test quoted HTML directive with more complex HTML
  assert_equal(
    doc(
      quoted_html({
        htmlContent: "<div><p>Complex HTML</p><ul><li>Item 1</li><li>Item 2</li></ul></div>"
      })
    ),
    `:::quoted_html
<div><p>Complex HTML</p><ul><li>Item 1</li><li>Item 2</li></ul></div>
:::
`
  )

  // Test empty quoted HTML directive
  assert_equal(
    doc(quoted_html({ htmlContent: "" })),
    `:::quoted_html

:::
`
  )
})

test("Quoted HTML directive with real email content", () => {
  // prosemirror-unified warns for raw HTML nodes it can't map to ProseMirror;
  // quoted_html stores them as an attribute, so the warning is expected here.
  vi.spyOn(console, "warn").mockImplementation(() => {})

  // Input: realistic email HTML with <br><br> tags
  const emailHtml = `<div style="padding:1em;">
    <div style="padding:1em;background-color:white;border-bottom:1px solid #D1D2D4;">Hi,

<p>You have a new message from <i>Jack O'Lantern, jackolantern@example.com</i>:</p>


Hello! Please ensure you're familiar with where Den 1880's available parking spaces are located to avoid being ticketed or towed.  Only unmarked spots are available to members on a first-come, first-served basis. Any spaces marked with a number or company logo are reserved.<br><br>Please also ensure your licence plate has been registered with our team. If you haven't done so, you can email your car model and licence plate to hello@den1880.co<br><br>If you're unsure where to park, a parking guide is available in your member portal and at the front desk.  <br><br>Thank you!
    </div>
    <div style="text-align:center;padding:1em;">2025 Den 1880
    </div>
</div>
<br>
<p><a href="http://example.example">unsubscribe</a></p>
 <img width="1" height="1" alt="" src="http://example.example">`

  // Expected output: HTML normalized during parsing (<br><br> becomes <p></p><p></p>, whitespace collapsed)
  const expectedOutputHtml = `<div style="padding:1em;">
    <div style="padding:1em;background-color:white;border-bottom:1px solid #D1D2D4;">Hi,<p>You have a new message from <i>Jack O'Lantern, jackolantern@example.com</i>:</p><p>Hello! Please ensure you're familiar with where Den 1880's available parking spaces are located to avoid being ticketed or towed.  Only unmarked spots are available to members on a first-come, first-served basis. Any spaces marked with a number or company logo are reserved.<p></p><p></p>Please also ensure your licence plate has been registered with our team. If you haven't done so, you can email your car model and licence plate to hello@den1880.co<p></p><p></p>If you're unsure where to park, a parking guide is available in your member portal and at the front desk.  <p></p><p></p>Thank you!
</div>
<div style="text-align:center;padding:1em;">2025 Den 1880
</div></p></div>
<br>
<p><a href="http://example.example">unsubscribe</a></p>
 <img width="1" height="1" alt="" src="http://example.example">`

  // Test that input emailHtml gets normalized to expectedOutputHtml
  const inputMarkdown = `:::quoted_html
${emailHtml}
:::
`
  const expectedDoc = doc(quoted_html({ htmlContent: expectedOutputHtml }))
  const parsedDoc = parse(inputMarkdown)

  expect(parsedDoc).toEqual(expectedDoc)
  expect(serialize(parsedDoc)).toBe(`:::quoted_html
${expectedOutputHtml}
:::
`)

  // Test normalized form round-trips correctly
  assert_equal(expectedDoc, `:::quoted_html
${expectedOutputHtml}
:::
`)

  // Test with collapsed attribute
  const collapsedInputMarkdown = `:::quoted_html{collapsed=true}
${emailHtml}
:::
`
  const expectedCollapsedDoc = doc(quoted_html({ htmlContent: expectedOutputHtml, collapsed: true }))
  const parsedCollapsedDoc = parse(collapsedInputMarkdown)

  expect(parsedCollapsedDoc).toEqual(expectedCollapsedDoc)
  expect(serialize(parsedCollapsedDoc)).toBe(`:::quoted_html{collapsed="true"}
${expectedOutputHtml}
:::
`)
})

test("Trailing spaces after URLs are trimmed", () => {
  const docWithTrailingSpace = doc(paragraph("URL: https://example.com "))
  const serialized = serialize(docWithTrailingSpace)

  // Should not contain &#x20;
  expect(serialized).not.toContain("&#x20")
  // Should end with URL directly (no space)
  expect(serialized.trim()).toBe("URL: https://example.com")
})

test("Trailing spaces after regular text are trimmed", () => {
  const docWithTrailingSpace = doc(paragraph("Some text "))
  const serialized = serialize(docWithTrailingSpace)

  // Should not contain &#x20;
  expect(serialized).not.toContain("&#x20")
  // Should end without trailing space
  expect(serialized.trim()).toBe("Some text")
})

test("Hard breaks (two spaces + newline) are preserved", () => {
  // Inline hard break (followed by more content in the same paragraph) — preserved
  // as the markdown backslash-newline form.
  const docWithInlineHardBreak = doc(
    paragraph("Line one", hard_break(), "Line two")
  )
  expect(serialize(docWithInlineHardBreak)).toBe("Line one\\\nLine two\n")

  // Block-trailing hard break (last child of a paragraph) — must be DROPPED.
  // Otherwise the first save serializes as "X\\\n" and on re-edit the literal
  // backslash gets re-escaped to "X\\\\\n" (double-backslash), which mistune
  // renders as a literal backslash in the output.
  const docWithTrailingHardBreak = doc(paragraph("X", hard_break()))
  expect(serialize(docWithTrailingHardBreak)).toBe("X\n")

  // Round-trip idempotence: serialize(parse(serialize(doc))) === serialize(doc).
  // Before the fix, a block-trailing hard_break round-trips to a double-backslash;
  // after the fix it's dropped on the first serialize, so the round-trip is stable.
  const multiBlockDoc = doc(paragraph("X", hard_break()), paragraph("Y"))
  const once = serialize(multiBlockDoc)
  const twice = serialize(parse(once))
  expect(once).toBe("X\n\nY\n")
  expect(twice).toBe(once)
  expect(once).not.toContain("\\\\")
  expect(twice).not.toContain("\\\\")
})

test("user-typed trailing backslash is preserved through serialize/parse", () => {
  // The block-trailing hard_break drop must NOT destroy a legitimate user-typed
  // trailing backslash, whether or not the paragraph has a trailing break.
  const d = doc(paragraph("path\\"))
  const md = serialize(d)
  // Backslash must be present in the serialized markdown.
  expect(md).toContain("\\")
  // Round-trip is stable.
  expect(serialize(parse(md))).toBe(md)

  // With a trailing hard_break: the hard_break is dropped but the user's `\` stays.
  const dWithBreak = doc(paragraph("path\\", hard_break()))
  const mdWithBreak = serialize(dWithBreak)
  expect(mdWithBreak).toContain("\\")
  expect(serialize(parse(mdWithBreak))).toBe(mdWithBreak)
})

test("Mid-paragraph spaces are preserved", () => {
  const docWithMidSpace = doc(paragraph("Some text with spaces between words"))
  const serialized = serialize(docWithMidSpace)

  expect(serialized).toBe("Some text with spaces between words\n")
})

test("Multiple paragraphs with trailing spaces", () => {
  const docWithMultipleParagraphs = doc(
    paragraph("First paragraph "),
    paragraph("Second paragraph "),
    paragraph("Third paragraph")
  )
  const serialized = serialize(docWithMultipleParagraphs)

  // No &#x20; entities
  expect(serialized).not.toContain("&#x20")
  // Should have clean paragraphs
  expect(serialized).toBe("First paragraph\n\nSecond paragraph\n\nThird paragraph\n")
})

test("Empty paragraphs still work with trimming", () => {
  const docWithEmptyParagraph = doc(
    paragraph("Text"),
    paragraph(""),
    paragraph("More text")
  )
  const serialized = serialize(docWithEmptyParagraph)

  expect(serialized).toContain("<br />")
})

test("Does not create empty text nodes when trimming whitespace-only text", () => {
  // Tests the fix for empty text node errors: text nodes that become empty
  // after trimming should be removed to prevent "Empty text nodes are not allowed"
  const input = `Text with trailing spaces

Another paragraph
`
  // Should parse without throwing "Empty text nodes are not allowed"
  expect(() => parse(input)).not.toThrow()

  const doc = parse(input)
  expect(doc).toBeTruthy()

  // Should be able to serialize back
  const output = serialize(doc)
  expect(output).toBeTruthy()
})

test("URLs with underscores in link text are not escaped", () => {
  // Test that underscores in URLs used as link text are NOT escaped
  // This is a regression test for a bug where http://localhost:8000/email_threads/123
  // was being serialized as http://localhost:8000/email\_threads/123

  // Test URL as both href AND link text (common pattern from auto-linking)
  assert_equal(
    doc(paragraph(link({ href: "http://localhost:8000/email_threads/123" }, "http://localhost:8000/email_threads/123"))),
    `[http://localhost:8000/email_threads/123](http://localhost:8000/email_threads/123)
`
  )

  // Test URL with multiple underscores
  assert_equal(
    doc(paragraph(link({ href: "https://example.com/some_path/with_underscores/file_name.txt" }, "https://example.com/some_path/with_underscores/file_name.txt"))),
    `[https://example.com/some_path/with_underscores/file_name.txt](https://example.com/some_path/with_underscores/file_name.txt)
`
  )
})

test("Plain text URLs with underscores are not escaped", () => {
  // Plain text URLs (not inside links) should not have underscores escaped
  assert_equal(
    doc(paragraph("Check out http://localhost:8000/email_threads/123 for details")),
    `Check out http://localhost:8000/email_threads/123 for details
`
  )
})

test("Regular text with underscores is still escaped appropriately", () => {
  // Non-URL text should still have underscores escaped if they could be interpreted as emphasis
  const docWithRegularText = doc(paragraph("Some text with under_scores in_it"))
  const serialized = serialize(docWithRegularText)

  // Underscores should be escaped to prevent emphasis interpretation
  expect(serialized).toContain("under\\_scores")
  expect(serialized).toContain("in\\_it")
})

test("URLs with query parameters are not escaped", () => {
  // URLs with query parameters should not have special characters escaped
  assert_equal(
    doc(paragraph(link({ href: "https://example.com/search?q=test_value&foo=bar_baz" }, "https://example.com/search?q=test_value&foo=bar_baz"))),
    `[https://example.com/search?q=test_value&foo=bar_baz](https://example.com/search?q=test_value&foo=bar_baz)
`
  )

  // Plain text URL with query parameters
  assert_equal(
    doc(paragraph("Visit https://example.com/api?user_id=123&session_token=abc for more")),
    `Visit https://example.com/api?user_id=123&session_token=abc for more
`
  )
})

test("URLs with parentheses are handled correctly", () => {
  // URLs containing parentheses (common in Wikipedia links)
  // Note: Parentheses in URLs need special handling in markdown
  assert_equal(
    doc(paragraph(link({ href: "https://en.wikipedia.org/wiki/Scheme_(programming_language)" }, "https://en.wikipedia.org/wiki/Scheme_(programming_language)"))),
    `[https://en.wikipedia.org/wiki/Scheme_(programming_language)](https://en.wikipedia.org/wiki/Scheme_\\(programming_language\\))
`
  )
})

test("URLs with asterisks and other special characters", () => {
  // Test that asterisks in URLs (if they appear) don't get treated as emphasis
  assert_equal(
    doc(paragraph("Check https://example.com/path_with_underscores/file.txt for info")),
    `Check https://example.com/path_with_underscores/file.txt for info
`
  )

  // URL with hash fragment
  assert_equal(
    doc(paragraph(link({ href: "https://example.com/docs#section_name" }, "https://example.com/docs#section_name"))),
    `[https://example.com/docs#section_name](https://example.com/docs#section_name)
`
  )
})

test("Basic table", () => {
  assert_equal(
    doc(
      table(
        table_row(table_header(paragraph("A")), table_header(paragraph("B"))),
        table_row(table_cell(paragraph("1")), table_cell(paragraph("2")))
      )
    ),
    `| A | B |
| - | - |
| 1 | 2 |
`
  )
})

test("Table with inline formatting in cells", () => {
  assert_equal(
    doc(
      table(
        table_row(table_header(paragraph("Name")), table_header(paragraph("Status"))),
        table_row(table_cell(paragraph(strong("Alice"))), table_cell(paragraph(em("active"))))
      )
    ),
    `| Name      | Status   |
| --------- | -------- |
| **Alice** | *active* |
`
  )
})

test("Table with empty cells", () => {
  assert_equal(
    doc(
      table(
        table_row(table_header(paragraph("A")), table_header(paragraph("B"))),
        table_row(table_cell(paragraph()), table_cell(paragraph("x")))
      )
    ),
    `| A | B |
| - | - |
|   | x |
`
  )
})

test("Table with code in cells", () => {
  assert_equal(
    doc(
      table(
        table_row(table_header(paragraph("Key")), table_header(paragraph("Value"))),
        table_row(table_cell(paragraph(code("id"))), table_cell(paragraph("123")))
      )
    ),
    `| Key  | Value |
| ---- | ----- |
| \`id\` | 123   |
`
  )
})

test("Table with links in cells", () => {
  assert_equal(
    doc(
      table(
        table_row(table_header(paragraph("Site")), table_header(paragraph("URL"))),
        table_row(
          table_cell(paragraph("Example")),
          table_cell(paragraph(link({ href: "https://example.com" }, "link")))
        )
      )
    ),
    `| Site    | URL                         |
| ------- | --------------------------- |
| Example | [link](https://example.com) |
`
  )
})

test("Table within a larger document", () => {
  assert_equal(
    doc(
      paragraph("Before the table."),
      table(
        table_row(table_header(paragraph("X")), table_header(paragraph("Y"))),
        table_row(table_cell(paragraph("a")), table_cell(paragraph("b")))
      ),
      paragraph("After the table.")
    ),
    `Before the table.

| X | Y |
| - | - |
| a | b |

After the table.
`
  )
})

test("Table with three columns and multiple rows", () => {
  assert_equal(
    doc(
      table(
        table_row(table_header(paragraph("A")), table_header(paragraph("B")), table_header(paragraph("C"))),
        table_row(table_cell(paragraph("1")), table_cell(paragraph("2")), table_cell(paragraph("3"))),
        table_row(table_cell(paragraph("4")), table_cell(paragraph("5")), table_cell(paragraph("6")))
      )
    ),
    `| A | B | C |
| - | - | - |
| 1 | 2 | 3 |
| 4 | 5 | 6 |
`
  )
})

test("Strikethrough", () => {
  assert_equal(
    doc(paragraph("This has ", strikethrough("struck through"), " text")),
    "This has ~~struck through~~ text\n"
  )
})

test("Adjacent text nodes with shared bold factor out common marks", () => {
  // A bold sentence where one word is also italicized: "**particular *tastes*?**"
  // Pre-fix this regressed to "*****tastes*****" because nested marks weren't factored.
  assert_equal(
    doc(paragraph(strong("particular "), strong(em("tastes")), strong("?"))),
    "**particular *tastes*?**\n"
  )
})

test("Round-trip of corrupted bold+italic heals on re-serialize", () => {
  const parsed = parse("*****hello*****")
  const reserialized = serialize(parsed)

  // Should emit valid bold+italic, not the corrupted 5-asterisk form
  expect(reserialized.trim()).toBe("***hello***")
  // Must not contain any run of 4 or more consecutive asterisks
  expect(reserialized).not.toMatch(/\*{4,}/)
})

test("Task lists", () => {
  assert_equal(
    doc(
      bullet_list(
        task_list_item({ checked: false }, paragraph("Unchecked task")),
        task_list_item({ checked: true }, paragraph("Checked task"))
      )
    ),
    "* [ ] Unchecked task\n* [x] Checked task\n"
  )
})

test("Task list with strikethrough", () => {
  assert_equal(
    doc(
      bullet_list(
        task_list_item({ checked: true }, paragraph(strikethrough("Done task"))),
        task_list_item({ checked: false }, paragraph("Pending task"))
      )
    ),
    "* [x] ~~Done task~~\n* [ ] Pending task\n"
  )
})

describe("Schema consistency", () => {
  test("input rule mark types belong to the editor schema", () => {
    for (const plugin of plugins) {
      const rules = (plugin as any).rules
      if (!rules) continue
      for (const rule of rules) {
        if (rule.markType) {
          expect(rule.markType.schema).toBe(schema)
        }
      }
    }
  })

  test("schema includes comment mark", () => {
    expect(schema.marks.comment).toBeDefined()
  })

  test("schema includes strikethrough mark", () => {
    expect(schema.marks.strikethrough).toBeDefined()
  })

  test("schema includes task_list_item node", () => {
    expect(schema.nodes.task_list_item).toBeDefined()
  })
})
