import { act, renderHook, waitFor } from "@testing-library/react"
import type { Dispatch, SetStateAction } from "react"
import { afterEach, describe, expect, test, vi } from "vitest"

import { apiFetch } from "~/react/shared/apiFetch"
import { useReactionToggle } from "~/react/shared/hooks/useReactionToggle"
import type { ReactionUser } from "~/react/shared/types"

vi.mock("~/react/shared/apiFetch", () => ({ apiFetch: vi.fn() }))

const mockApiFetch = vi.mocked(apiFetch)

const me: ReactionUser = { id: "u-me", display_name: "Me" }
const other: ReactionUser = { id: "u-other", display_name: "Other" }

interface Item {
  id: string
  reactions: Record<string, ReactionUser[]>
}

function setup(initial: Item[], currentUser: ReactionUser | null = me) {
  const store = { items: initial }
  const setItems: Dispatch<SetStateAction<Item[]>> = update => {
    store.items = typeof update === "function" ? update(store.items) : update
  }
  const onError = vi.fn()
  const { result, rerender } = renderHook(() =>
    useReactionToggle<Item, Item>({
      currentUser,
      setItems,
      buildUrl: (id, reactionType) => `/api/x/${id}?reaction_type=${reactionType}`,
      parseReactions: comment => comment.reactions,
      onError,
    })
  )
  return { store, onError, result, rerender }
}

afterEach(() => {
  mockApiFetch.mockReset()
})

describe("useReactionToggle", () => {
  test("splices the reaction optimistically, then reconciles with the server reactions", async () => {
    const { store, onError, result } = setup([{ id: "c1", reactions: {} }])
    let resolve: (v: unknown) => void = () => {}
    mockApiFetch.mockReturnValueOnce(new Promise(r => (resolve = r)) as never)

    act(() => {
      void result.current("c1", "thumbs_up")
    })
    // Optimistic: the actor appears immediately, before the POST resolves.
    expect(store.items[0].reactions).toEqual({ thumbs_up: [me] })

    resolve({ id: "c1", reactions: { thumbs_up: [me, other] } })
    await waitFor(() => expect(store.items[0].reactions).toEqual({ thumbs_up: [me, other] }))
    expect(onError).not.toHaveBeenCalled()
  })

  test("reverts the optimistic change and reports the error when the POST fails", async () => {
    const { store, onError, result } = setup([{ id: "c1", reactions: { heart: [other] } }])
    mockApiFetch.mockRejectedValueOnce(new Error("boom"))

    await act(async () => {
      await result.current("c1", "thumbs_up")
    })

    // Re-applying the self-inverse toggle removes our optimistic add while
    // leaving the concurrent reactor (other) untouched.
    expect(store.items[0].reactions).toEqual({ heart: [other], thumbs_up: [] })
    expect(onError).toHaveBeenCalledOnce()
  })

  test("still POSTs and reconciles without an optimistic splice when currentUser is null", async () => {
    const { store, result } = setup([{ id: "c1", reactions: {} }], null)
    let resolve: (v: unknown) => void = () => {}
    mockApiFetch.mockReturnValueOnce(new Promise(r => (resolve = r)) as never)

    act(() => {
      void result.current("c1", "thumbs_up")
    })
    // No optimistic change (we can't attribute it), but the POST still fires.
    expect(store.items[0].reactions).toEqual({})
    expect(mockApiFetch).toHaveBeenCalledWith("/api/x/c1?reaction_type=thumbs_up", { method: "POST" })

    resolve({ id: "c1", reactions: { thumbs_up: [other] } })
    await waitFor(() => expect(store.items[0].reactions).toEqual({ thumbs_up: [other] }))
  })

  test("reports the error without touching state when the POST fails and there is no actor", async () => {
    const { store, onError, result } = setup([{ id: "c1", reactions: { heart: [other] } }], null)
    mockApiFetch.mockRejectedValueOnce(new Error("boom"))

    await act(async () => {
      await result.current("c1", "thumbs_up")
    })

    // No optimistic splice happened (no actor), so there is nothing to revert —
    // state is untouched and only the error is surfaced.
    expect(store.items[0].reactions).toEqual({ heart: [other] })
    expect(onError).toHaveBeenCalledOnce()
  })

  test("returns a stable callback across re-renders", () => {
    const { result, rerender } = setup([{ id: "c1", reactions: {} }])
    const first = result.current
    rerender()
    expect(result.current).toBe(first)
  })
})
