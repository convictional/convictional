import { afterEach, beforeEach, describe, expect, it } from "vitest"

import { entryTargetWithReturnTo } from "~/react/features/mailboxIndex/entryTarget"

const originalLocation = window.location

function setLocation(pathname: string, search: string) {
  Object.defineProperty(window, "location", {
    value: { origin: "https://app.test", href: `https://app.test${pathname}${search}`, pathname, search },
    writable: true,
    configurable: true,
  })
}

beforeEach(() => setLocation("/", ""))

afterEach(() => {
  Object.defineProperty(window, "location", { value: originalLocation, writable: true, configurable: true })
})

describe("entryTargetWithReturnTo", () => {
  it("splits the href and stamps the inbox root as return_to", () => {
    expect(entryTargetWithReturnTo("/posts/abc?mailbox_entry_id=1")).toEqual({
      to: "/posts/abc",
      search: { mailbox_entry_id: "1", return_to: "/" },
    })
  })

  it("adds return_to when the href has no query", () => {
    expect(entryTargetWithReturnTo("/email_threads/abc")).toEqual({
      to: "/email_threads/abc",
      search: { return_to: "/" },
    })
  })

  // The search values are handed to <Link>, which does its own encoding — so a
  // return_to carrying a query must stay decoded here or it would be double-encoded.
  it("preserves the current folder and view params", () => {
    setLocation("/", "?mailbox_view_template=urgent")
    expect(entryTargetWithReturnTo("/posts/abc?mailbox_entry_id=1")).toEqual({
      to: "/posts/abc",
      search: { mailbox_entry_id: "1", return_to: "/?mailbox_view_template=urgent" },
    })

    setLocation("/archived", "")
    expect(entryTargetWithReturnTo("/posts/abc")).toEqual({ to: "/posts/abc", search: { return_to: "/archived" } })
  })

  it("has no destination for a placeholder href", () => {
    expect(entryTargetWithReturnTo("#")).toBeNull()
  })
})
