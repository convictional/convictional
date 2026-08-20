import { act, cleanup, fireEvent, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

const apiFetchMock = vi.hoisted(() => vi.fn())
vi.mock("~/react/shared/apiFetch", () => ({ apiFetch: apiFetchMock }))

import { DraftCard } from "~/react/features/postsIndex/components/DraftCard"
import type { PostDraft } from "~/react/features/postsIndex/types"

import { makeDraft, makeUser } from "./fixtures"
import { renderInPostsRouter } from "./harness"

// DraftCard renders a typed <Link> to the editor, so it must mount inside the
// router as the index route's component. returnTo is the index URL the card
// stamps onto the editor's back link.
function renderDraftCard(draft: PostDraft, currentUserId: string | null = "user-1") {
  return renderInPostsRouter(() => <DraftCard draft={draft} currentUserId={currentUserId} returnTo="/posts" />)
}

beforeEach(() => {
  apiFetchMock.mockReset()
  apiFetchMock.mockReturnValue(new Promise(() => {}))
})

afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

describe("DraftCard", () => {
  test("hovering a collaborator avatar opens the profile card", async () => {
    const { container } = await renderDraftCard(makeDraft({ collaborators: [makeUser({ id: "collab-1" })] }))

    vi.useFakeTimers()
    // Stack layout renders the UserHoverCard trigger <span> directly under .avatar-group.
    const trigger = container.querySelector(".avatar-group > span")!
    fireEvent.mouseEnter(trigger)
    await act(async () => {
      vi.advanceTimersByTime(200)
    })

    expect(apiFetchMock).toHaveBeenCalledWith("/api/people/collab-1")
    expect(apiFetchMock).toHaveBeenCalledWith("/api/users/collab-1/top_goal?expand=parent")
  })

  test("links to the draft editor with a return_to param", async () => {
    await renderDraftCard(makeDraft({ id: "d9", title: "My draft" }))
    expect(screen.getByText("My draft")).toBeInTheDocument()
    const link = screen.getByRole("link")
    expect(link.getAttribute("href")).toContain("/posts/d9/edit")
    expect(link.getAttribute("href")).toContain("return_to=%2Fposts")
  })

  test("shows 'Shared with me' when the creator is not the current user", async () => {
    await renderDraftCard(makeDraft({ creator: makeUser({ id: "someone-else", display_name: "Bob" }) }))
    expect(screen.getByText("Shared with me")).toBeInTheDocument()
    expect(screen.getByText("@Bob")).toBeInTheDocument()
  })

  test("omits 'Shared with me' for the current user's own draft", async () => {
    await renderDraftCard(makeDraft({ creator: makeUser({ id: "user-1" }) }))
    expect(screen.queryByText("Shared with me")).not.toBeInTheDocument()
  })

  test("renders collaborator avatars", async () => {
    const { container } = await renderDraftCard(
      makeDraft({ collaborators: [makeUser({ id: "c1", display_name: "Carol" })] })
    )
    expect(container.querySelector(".avatar")).not.toBeNull()
  })
})
