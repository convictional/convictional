import { act, cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

import { UserHoverCard } from "~/react/composites/UserHoverCard"

const apiFetchMock = vi.hoisted(() => vi.fn())
vi.mock("~/react/shared/apiFetch", () => ({ apiFetch: apiFetchMock }))

interface PeopleResponse {
  user: {
    id: string
    display_name: string
    picture: string | null
    email: string
    bio: string | null
    is_admin: boolean
  }
  groups: { id: string; name: string }[]
}

interface TopGoalResponse {
  top_goal: { id: string; title: string | null; description: string; parent: { description: string } | null } | null
}

function peopleFor(userId: string): PeopleResponse {
  return {
    user: {
      id: userId,
      display_name: "Alice",
      picture: null,
      email: "alice@example.com",
      bio: null,
      is_admin: false,
    },
    groups: [],
  }
}

function emptyTopGoal(): TopGoalResponse {
  return { top_goal: null }
}

// Stubs both /api/people/{id} and /api/users/{id}/top_goal in the order they're called.
function mockBothFetches(people: PeopleResponse, topGoal: TopGoalResponse = emptyTopGoal()) {
  apiFetchMock.mockResolvedValueOnce(people).mockResolvedValueOnce(topGoal)
}

beforeEach(() => {
  vi.useFakeTimers()
  apiFetchMock.mockReset()
})

afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

describe("UserHoverCard", () => {
  test("does not fetch or render the card until hovered", () => {
    mockBothFetches(peopleFor("user-1"))

    render(
      <UserHoverCard userId="user-1">
        <button>Alice</button>
      </UserHoverCard>
    )

    expect(apiFetchMock).not.toHaveBeenCalled()
    expect(screen.queryByText("alice@example.com")).toBeNull()
  })

  test("shows skeleton then card after hovering past the open delay", async () => {
    let resolvePeople!: (data: PeopleResponse) => void
    let resolveTopGoal!: (data: TopGoalResponse) => void
    apiFetchMock
      .mockReturnValueOnce(new Promise<PeopleResponse>(resolve => (resolvePeople = resolve)))
      .mockReturnValueOnce(new Promise<TopGoalResponse>(resolve => (resolveTopGoal = resolve)))

    render(
      <UserHoverCard userId="user-1">
        <button>Alice</button>
      </UserHoverCard>
    )

    fireEvent.mouseEnter(screen.getByText("Alice").parentElement!)
    await act(async () => {
      vi.advanceTimersByTime(200)
    })

    expect(apiFetchMock).toHaveBeenNthCalledWith(1, "/api/people/user-1")
    expect(apiFetchMock).toHaveBeenNthCalledWith(2, "/api/users/user-1/top_goal?expand=parent")
    expect(screen.queryByText("alice@example.com")).toBeNull()

    await act(async () => {
      resolvePeople(peopleFor("user-1"))
      resolveTopGoal(emptyTopGoal())
    })

    expect(screen.getByText("alice@example.com")).toBeTruthy()
    expect(screen.getAllByText("Alice").length).toBeGreaterThanOrEqual(2)
  })

  test("does not refetch when hovered a second time", async () => {
    mockBothFetches(peopleFor("user-1"))

    render(
      <UserHoverCard userId="user-1">
        <button>Alice</button>
      </UserHoverCard>
    )

    const trigger = screen.getByText("Alice").parentElement!
    fireEvent.mouseEnter(trigger)
    await act(async () => {
      vi.advanceTimersByTime(200)
    })
    expect(apiFetchMock).toHaveBeenCalledTimes(2)

    fireEvent.mouseLeave(trigger)
    await act(async () => {
      vi.advanceTimersByTime(200)
    })

    fireEvent.mouseEnter(trigger)
    await act(async () => {
      vi.advanceTimersByTime(200)
    })

    expect(apiFetchMock).toHaveBeenCalledTimes(2)
  })

  test("retries the fetch on the next hover after a failure", async () => {
    apiFetchMock
      .mockRejectedValueOnce(new Error("boom"))
      .mockRejectedValueOnce(new Error("boom"))
      .mockResolvedValueOnce(peopleFor("user-1"))
      .mockResolvedValueOnce(emptyTopGoal())

    render(
      <UserHoverCard userId="user-1">
        <button>Alice</button>
      </UserHoverCard>
    )

    const trigger = screen.getByText("Alice").parentElement!
    fireEvent.mouseEnter(trigger)
    await act(async () => {
      vi.advanceTimersByTime(200)
    })
    expect(apiFetchMock).toHaveBeenCalledTimes(2)

    fireEvent.mouseLeave(trigger)
    await act(async () => {
      vi.advanceTimersByTime(200)
    })

    fireEvent.mouseEnter(trigger)
    await act(async () => {
      vi.advanceTimersByTime(200)
    })

    expect(apiFetchMock).toHaveBeenCalledTimes(4)
  })

  test("requests data for the given userId", async () => {
    mockBothFetches(peopleFor("user-42"))

    render(
      <UserHoverCard userId="user-42">
        <button>Bob</button>
      </UserHoverCard>
    )

    fireEvent.mouseEnter(screen.getByText("Bob").parentElement!)
    await act(async () => {
      vi.advanceTimersByTime(200)
    })

    expect(apiFetchMock).toHaveBeenNthCalledWith(1, "/api/people/user-42")
    expect(apiFetchMock).toHaveBeenNthCalledWith(2, "/api/users/user-42/top_goal?expand=parent")
  })
})
