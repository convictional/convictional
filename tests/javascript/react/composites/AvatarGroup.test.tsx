import { act, cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

import { AvatarGroup } from "~/react/composites/AvatarGroup"
import type { User } from "~/react/shared/types"

const apiFetchMock = vi.hoisted(() => vi.fn())
vi.mock("~/react/shared/apiFetch", () => ({ apiFetch: apiFetchMock }))

function makeUser(overrides: Partial<User> = {}): User {
  return { id: "user-1", display_name: "Alice", picture: null, ...overrides }
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

describe("AvatarGroup", () => {
  test("renders up to two avatars and an overflow badge", () => {
    const users = [
      makeUser({ id: "u1", display_name: "Alice" }),
      makeUser({ id: "u2", display_name: "Bob" }),
      makeUser({ id: "u3", display_name: "Carol" }),
      makeUser({ id: "u4", display_name: "Dave" }),
    ]

    render(<AvatarGroup users={users} />)

    expect(screen.getByText("+2")).toBeTruthy()
  })

  test("lifts a present avatar above its neighbors in the stack layout", () => {
    const users = [makeUser({ id: "u1", display_name: "Alice" }), makeUser({ id: "u2", display_name: "Bob" })]

    const { container } = render(<AvatarGroup layout="stack" users={users} presentUserIds={["u2"]} sortPresentFirst />)

    // The present user's avatar is lifted via a z-indexed span so its ring isn't clipped by a neighbor.
    const lifted = container.querySelectorAll("span.z-10")
    expect(lifted.length).toBe(1)
    expect(lifted[0]!.querySelector(".border-info-content")).toBeTruthy()
  })

  test("hovering a stacked avatar triggers a profile card fetch for that user", async () => {
    const users = [makeUser({ id: "u1", display_name: "Alice" }), makeUser({ id: "u2", display_name: "Bob" })]

    const { container } = render(<AvatarGroup users={users} />)

    // Each shown avatar sits in an absolute-positioned wrapper; the UserHoverCard
    // is the immediate span child of that wrapper. Hover the second one.
    const triggers = container.querySelectorAll("div.absolute > span")
    expect(triggers.length).toBe(2)

    fireEvent.mouseEnter(triggers[1]!)
    await act(async () => {
      vi.advanceTimersByTime(200)
    })

    expect(apiFetchMock).toHaveBeenCalledWith("/api/people/u2")
    expect(apiFetchMock).toHaveBeenCalledWith("/api/users/u2/top_goal?expand=parent")
  })
})
