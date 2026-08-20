import { readFileSync } from "node:fs"
import { join } from "node:path"

import { cleanup, render } from "@testing-library/react"
import { afterEach, describe, expect, test } from "vitest"

import { Markdown } from "../../../../../app/javascript/react/composites/markdown/Markdown"
import cases from "../../../../fixtures/markdown_whitespace/cases.json"

// Asserts the React renderer's RAW innerHTML against each case's per-surface
// `in_app_target` — NOT the cross-surface normalized `target_html`, which the
// centrally-owned normalizer compares separately. Byte-for-byte here, so a
// regression that reintroduces a cosmetic `\n`, unwraps an empty paragraph, or
// collapses a whitespace run fails loudly.
interface Case {
  name: string
  wire: string
  in_app_target: string | null
}

const conformanceCases = (cases.cases as Case[]).filter(c => c.in_app_target !== null)

describe("Markdown whitespace conformance (raw in_app_target)", () => {
  afterEach(cleanup)

  test.each(conformanceCases)("$name renders exactly its in_app_target", ({ wire, in_app_target }) => {
    const { container } = render(<Markdown source={wire} />)
    const wrapper = container.firstElementChild as HTMLElement
    expect(wrapper.innerHTML).toBe(in_app_target)
  })

  test("every case declares an in_app_target (null is an explicit opt-out)", () => {
    for (const c of cases.cases as Case[]) {
      expect(c, `${c.name}: missing in_app_target field`).toHaveProperty("in_app_target")
    }
  })
})

// The whitespace contract's `pre-wrap` rule lives in markdown-content.css, which
// is shared with the live ProseMirror editor wrapper. The editor is unaffected
// at runtime because prosemirror-view sets `white-space: pre-wrap` on
// `.ProseMirror` and it inherits to p/li/h*, so its computed value never changes
// — only the read-only display surface flips from the `@apply prose` `normal`
// default to pre-wrap. jsdom applies no stylesheets, so we assert this
// structurally against the CSS source: the new pre-wrap selector targets only
// read-only text-bearing blocks and never newly constrains `.ProseMirror`.
describe("markdown-content.css pre-wrap policy", () => {
  const css = readFileSync(join(__dirname, "../../../../../app/styles/markdown-content.css"), "utf8")

  test("pre-wrap is applied to read-only text-bearing blocks, not to .ProseMirror or <pre>", () => {
    // Assert against the code, not the comments (which legitimately discuss
    // .ProseMirror). Match any *innermost* rule block that contains white-space:
    // pre-wrap (not only as its sole declaration, so the check survives a second
    // property being added later). The block body excludes braces so it can't
    // span the nested `.markdown-content { … }` wrapper; the selector capture
    // stays word/comma/space-only so it can't run past a rule boundary.
    const code = css.replace(/\/\*[\s\S]*?\*\//g, "")
    const preWrapRule = /(?<selector>[\w, ]+)\{[^{}]*white-space:\s*pre-wrap[^{}]*\}/g
    const selectorLists = [...code.matchAll(preWrapRule)].map(m =>
      (m.groups?.selector ?? "").trim().split(",").map(s => s.trim())
    )

    const blockRule = selectorLists.find(tags => tags.includes("p") && tags.includes("li") && tags.includes("td"))
    expect(blockRule, "expected a rule listing the text-bearing blocks").toBeDefined()
    for (const tag of ["p", "li", "h1", "h2", "h3", "h4", "h5", "h6", "td", "th"]) {
      expect(blockRule).toContain(tag)
    }

    // The editor never gets a new white-space constraint from this file, and code
    // blocks stay exempt (they rely on prose-pre:whitespace-pre-wrap / the browser
    // default `pre`).
    expect(code).not.toContain(".ProseMirror")
    for (const tags of selectorLists) {
      expect(tags).not.toContain("pre")
    }
  })
})
