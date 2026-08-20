import { describe, expect, test } from "vitest"

import { chatBackNavigation } from "../../../../../app/javascript/react/features/chatShow/chatBackNavigation"

describe("chatBackNavigation", () => {
  test("defaults to the chats index when return_to is absent", () => {
    expect(chatBackNavigation(undefined)).toEqual({ url: "/chats", label: "Back to chats" })
  })

  test("labels a chats-index return_to 'Back to chats', preserving its query", () => {
    expect(chatBackNavigation("/chats")).toEqual({ url: "/chats", label: "Back to chats" })
    expect(chatBackNavigation("/chats?group_id=g1")).toEqual({ url: "/chats?group_id=g1", label: "Back to chats" })
  })

  test("labels a mailbox (root) return_to 'Back to inbox' — the inbox lives at '/'", () => {
    expect(chatBackNavigation("/")).toEqual({ url: "/", label: "Back to inbox" })
    expect(chatBackNavigation("/?sort=oldest")).toEqual({ url: "/?sort=oldest", label: "Back to inbox" })
  })

  test("labels a saved/template mailbox view 'Back to custom view'", () => {
    expect(chatBackNavigation("/?mailbox_view_id=abc")).toEqual({
      url: "/?mailbox_view_id=abc",
      label: "Back to custom view",
    })
    expect(chatBackNavigation("/?mailbox_view_template=getting_started")).toEqual({
      url: "/?mailbox_view_template=getting_started",
      label: "Back to custom view",
    })
  })

  test("drops an off-site return_to (no open redirect) and falls back to the chats index", () => {
    expect(chatBackNavigation("//evil.com/phish")).toEqual({ url: "/chats", label: "Back to chats" })
    expect(chatBackNavigation("https://evil.com/phish")).toEqual({ url: "/chats", label: "Back to chats" })
  })
})
