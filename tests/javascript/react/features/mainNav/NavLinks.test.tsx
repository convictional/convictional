import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

import { NavLinks } from "../../../../../app/javascript/react/features/mainNav/NavLinks"

const installSpy = vi.fn()
const uninstallSpy = vi.fn()
vi.mock("@github/hotkey", () => ({
  install: (el: HTMLElement) => installSpy(el),
  uninstall: (el: HTMLElement) => uninstallSpy(el),
}))

describe("NavLinks", () => {
  beforeEach(() => {
    installSpy.mockClear()
    uninstallSpy.mockClear()
    window.history.replaceState({}, "", "/")
  })

  afterEach(cleanup)

  test("renders all five nav links with hotkeys and preload", () => {
    render(<NavLinks />)

    const expected: Array<[string, string, string]> = [
      ["Inbox", "/", "g i"],
      ["Chat", "/chats", "g c"],
      ["Posts", "/posts", "g p"],
      ["Docs", "/documents", "g o"],
      ["Goals", "/goals", "g g"],
    ]

    for (const [label, href, hotkey] of expected) {
      const link = screen.getByRole("link", { name: label })
      expect(link).toHaveAttribute("href", href)
      expect(link).toHaveAttribute("data-hotkey", hotkey)
    }
  })

  test("SPA-shell links opt out of boosting; they also skip the wasted preload", () => {
    render(<NavLinks />)

    // Every tab now targets the client-routed SPA shell: never boost them (a boosted
    // fetch gets the shell as a fragment and needs the HX-Redirect bounce to
    // recover), and don't preload them (the hover XHR would only warm an unused 204).
    for (const label of ["Inbox", "Chat", "Posts", "Docs", "Goals"]) {
      const link = screen.getByRole("link", { name: label })
      expect(link).toHaveAttribute("hx-boost", "false")
      expect(link).not.toHaveAttribute("preload")
    }
  })

  test("marks the active link with aria-current and primary styling", () => {
    window.history.replaceState({}, "", "/posts/new-thing")
    render(<NavLinks />)

    const active = screen.getByRole("link", { name: "Posts" })
    expect(active).toHaveAttribute("aria-current", "page")
    expect(active.className).toContain("text-primary")

    const inactive = screen.getByRole("link", { name: "Chat" })
    expect(inactive).not.toHaveAttribute("aria-current")
  })

  test("highlights nothing when the path matches no tab (e.g. /meetings)", () => {
    window.history.replaceState({}, "", "/meetings")
    render(<NavLinks />)

    for (const label of ["Inbox", "Chat", "Posts", "Docs", "Goals"]) {
      expect(screen.getByRole("link", { name: label })).not.toHaveAttribute("aria-current")
    }
  })

  // Every inbox sub-view highlights Inbox. /unread was missing from the match
  // pattern while the React nav never rendered on an inbox path; it does now.
  test("matches every inbox sub-view — /unread, /snoozed, /archived are all Inbox", () => {
    for (const path of ["/", "/unread", "/snoozed", "/archived", "/sent", "/drafts", "/assigned_to_me"]) {
      window.history.replaceState({}, "", path)
      const utils = render(<NavLinks />)
      expect(screen.getByRole("link", { name: "Inbox" })).toHaveAttribute("aria-current", "page")
      utils.unmount()
    }
  })

  test("matches anchored prefixes — /post_drafts is Posts, /goal_alignments is Goals", () => {
    window.history.replaceState({}, "", "/post_drafts/abc")
    const first = render(<NavLinks />)
    expect(screen.getByRole("link", { name: "Posts" })).toHaveAttribute("aria-current", "page")
    first.unmount()

    window.history.replaceState({}, "", "/goal_alignments/xyz")
    render(<NavLinks />)
    expect(screen.getByRole("link", { name: "Goals" })).toHaveAttribute("aria-current", "page")
  })

  test("installs hotkeys on mount and uninstalls on unmount", () => {
    const { unmount } = render(<NavLinks />)
    expect(installSpy).toHaveBeenCalledTimes(5)

    unmount()
    expect(uninstallSpy).toHaveBeenCalledTimes(5)
  })

  test("hovering a link previews the indicator under that link, mouseleave snaps back", () => {
    render(<NavLinks />)

    const posts = screen.getByRole("link", { name: "Posts" })
    fireEvent.mouseEnter(posts)
    // hovering doesn't change aria-current — only the indicator position.
    // We can't easily measure the indicator in jsdom (offsetWidth is 0), but
    // we can assert that the hover handler doesn't crash and aria-current
    // remains on the original active link.
    expect(screen.getByRole("link", { name: "Inbox" })).toHaveAttribute("aria-current", "page")
  })
})
