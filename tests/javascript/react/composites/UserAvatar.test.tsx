import { act, cleanup, fireEvent, render } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

import { UserAvatar } from "~/react/composites/UserAvatar"
import type { User } from "~/react/shared/types"

const apiFetchMock = vi.hoisted(() => vi.fn())
vi.mock("~/react/shared/apiFetch", () => ({ apiFetch: apiFetchMock }))

// Use a picture so Avatar renders an <img> (not the placeholder-initial <span>) —
// that keeps the only <span> in the tree the UserHoverCard trigger.
function makeUser(overrides: Partial<User> = {}): User {
  return { id: "user-1", display_name: "Alice", picture: "https://example.com/a.jpg", ...overrides }
}

beforeEach(() => {
  vi.useFakeTimers()
  apiFetchMock.mockReset()
  // Never resolve — we only assert the request was made with the right id.
  apiFetchMock.mockReturnValue(new Promise(() => {}))
})

afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

describe("UserAvatar", () => {
  test("hovering wraps the avatar in a hover card and fetches that user's profile", async () => {
    const { container } = render(<UserAvatar user={makeUser({ id: "u9" })} />)

    // The hover card renders its trigger as a <span> wrapping the avatar.
    const trigger = container.querySelector("span")!
    fireEvent.mouseEnter(trigger)
    await act(async () => {
      vi.advanceTimersByTime(200)
    })

    expect(apiFetchMock).toHaveBeenCalledWith("/api/people/u9")
    expect(apiFetchMock).toHaveBeenCalledWith("/api/users/u9/top_goal?expand=parent")
  })

  test("withHoverCard={false} renders a bare avatar with no hover trigger and no fetch", async () => {
    const { container } = render(<UserAvatar user={makeUser({ id: "u9" })} withHoverCard={false} />)

    expect(container.querySelector("span")).toBeNull()
    fireEvent.mouseEnter(container.querySelector(".avatar")!)
    await act(async () => {
      vi.advanceTimersByTime(200)
    })

    expect(apiFetchMock).not.toHaveBeenCalled()
  })
})
