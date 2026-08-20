import { cleanup, render } from "@testing-library/react"
import { afterEach, describe, expect, test } from "vitest"

import { Markdown } from "../../../../../app/javascript/react/composites/markdown/Markdown"

// Compact fixture covering the surface area where the React renderer must match
// the server-side TailwindRenderer's structural output: a paragraph, a heading,
// a regular bulleted list, a task list (checked + unchecked), and a table with
// a centered column.
//
// Hardcoded inline because tests can't shell out to Python. The corresponding
// server-side parity check lives in `tests/unit/helpers/test_markdown.py`.
const FIXTURE = [
  "# Heading",
  "",
  "Some paragraph text.",
  "",
  "- regular one",
  "- regular two",
  "",
  "- [ ] todo",
  "- [x] done",
  "",
  "| a | b | c |",
  "|---|:-:|---|",
  "| 1 | 2 | 3 |",
].join("\n")

describe("React <Markdown> structural parity with TailwindRenderer", () => {
  afterEach(cleanup)

  test("rendered DOM matches the server's structural contract", () => {
    const { container } = render(<Markdown source={FIXTURE} />)
    const wrapper = container.firstElementChild as HTMLElement

    // Outer wrapper is a div with the canonical class.
    expect(wrapper.tagName).toBe("DIV")
    expect(wrapper.getAttribute("class")).toBe("markdown-content")

    // Heading and paragraph render as native semantic elements.
    expect(wrapper.querySelector("h1")?.textContent).toBe("Heading")
    expect(wrapper.querySelector("p")?.textContent).toContain("Some paragraph text.")

    // Task-list <li>s carry list-none and relative classes — same as the
    // TailwindRenderer.task_list_item output: `<li class="!my-1 list-none relative">`.
    const allItems = Array.from(wrapper.querySelectorAll("li"))
    const taskItems = allItems.filter(li => li.querySelector("input[type='checkbox']"))
    expect(taskItems.length).toBe(2)
    for (const item of taskItems) {
      expect(item.className).toContain("list-none")
      expect(item.className).toContain("relative")
    }

    // Regular <li>s should NOT carry list-none — the parent <ul> bullet markers
    // need to show through for non-task siblings.
    const regularItems = allItems.filter(li => !li.querySelector("input[type='checkbox']"))
    expect(regularItems.length).toBeGreaterThanOrEqual(2)
    for (const item of regularItems) {
      expect(item.className).not.toContain("list-none")
    }

    // Disabled checkbox inputs with task-checkbox class — same as the server
    // emits: `<input class="task-checkbox absolute -left-5 top-1" type="checkbox" disabled>`.
    const checkboxes = Array.from(wrapper.querySelectorAll<HTMLInputElement>("input[type='checkbox']"))
    expect(checkboxes.length).toBe(2)
    for (const cb of checkboxes) {
      expect(cb.className).toContain("task-checkbox")
      expect(cb.disabled).toBe(true)
    }
    expect(checkboxes.find(cb => !cb.checked)).toBeDefined()
    expect(checkboxes.find(cb => cb.checked)).toBeDefined()

    // Aligned table cells expose the alignment via the `data-align` attribute
    // that rehypeRestoreAlign copies from remark-gfm's `align` (since
    // hast-util-to-jsx-runtime would otherwise mangle it into style.textAlign).
    const table = wrapper.querySelector("table")
    expect(table).not.toBeNull()
    const headerCells = Array.from(wrapper.querySelectorAll("th"))
    expect(headerCells).toHaveLength(3)
    expect(headerCells[1].getAttribute("data-align")).toBe("center")

    const bodyCells = Array.from(wrapper.querySelectorAll("tbody td"))
    expect(bodyCells).toHaveLength(3)
    expect(bodyCells[1].getAttribute("data-align")).toBe("center")
  })
})
