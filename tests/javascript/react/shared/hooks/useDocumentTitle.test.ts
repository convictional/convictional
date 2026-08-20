import { renderHook } from "@testing-library/react"
import { afterEach, describe, expect, test } from "vitest"

import { formatPageTitle, useDocumentTitle } from "~/react/shared/hooks/useDocumentTitle"

function stampPrefix(value: string): void {
  const meta = document.createElement("meta")
  meta.name = "page-title-prefix"
  meta.content = value
  document.head.appendChild(meta)
}

describe("formatPageTitle", () => {
  afterEach(() => {
    document.querySelector('meta[name="page-title-prefix"]')?.remove()
  })

  test("matches format_page_title with no environment prefix", () => {
    expect(formatPageTitle("Goals")).toBe("Goals - Convictional")
  })

  test("applies the environment prefix the shell stamps", () => {
    stampPrefix("[STAGING] ")
    expect(formatPageTitle("Goals")).toBe("[STAGING] Goals - Convictional")
  })

  test("applies a dev-label prefix", () => {
    stampPrefix("convictional-blue | ")
    expect(formatPageTitle("Mailbox")).toBe("convictional-blue | Mailbox - Convictional")
  })
})

describe("useDocumentTitle", () => {
  afterEach(() => {
    document.querySelector('meta[name="page-title-prefix"]')?.remove()
  })

  test("sets document.title to the formatted title", () => {
    renderHook(() => useDocumentTitle("Mailbox"))
    expect(document.title).toBe("Mailbox - Convictional")
  })
})
