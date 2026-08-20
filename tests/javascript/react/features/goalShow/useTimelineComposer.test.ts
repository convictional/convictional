import { act, renderHook, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

vi.mock("~/react/shared/apiFetch", () => ({
  apiFetch: vi.fn(),
}))

vi.mock("~/shared/flash", () => ({ showFlash: vi.fn() }))

import { apiFetch } from "~/react/shared/apiFetch"
import { useTimelineComposer } from "~/react/features/goalShow/hooks/useTimelineComposer"
import type { Goal } from "~/react/shared/types"
import type { GoalUpdateSubmitData } from "~/react/features/goalShow/types"

const mockApiFetch = vi.mocked(apiFetch)

function makeGoal(id: string): Goal {
  return { id } as unknown as Goal
}

const draftData: GoalUpdateSubmitData = {
  status: "on_track",
  question_text: "How's it going?",
  answer_text: "My latest edit",
  progress: 0.5,
}

// A draft POST carries is_draft: true; the completing submit POSTs the same URL without it.
function draftPosts() {
  return mockApiFetch.mock.calls.filter(([url, options]) => {
    if (typeof url !== "string" || !url.endsWith("/updates") || options?.method !== "POST") return false
    return JSON.parse(options.body as string).is_draft === true
  })
}

beforeEach(() => {
  mockApiFetch.mockReset()
  // Every goal reports a pending update whose id is derived from the goal id, so the composer
  // captures a concrete update_id for its draft saves.
  mockApiFetch.mockImplementation((url: string) => {
    const pendingMatch = url.match(/goals\/([^/]+)\/updates\/pending$/)
    if (pendingMatch) {
      return Promise.resolve({
        id: `u-${pendingMatch[1]}`,
        question_text: "How's it going?",
        status: "on_track",
        progress: 0.5,
        answer_text: null,
      } as never)
    }
    return Promise.resolve(null as never)
  })
})

afterEach(() => {
  vi.clearAllMocks()
})

describe("useTimelineComposer draft flush", () => {
  test("navigating to another goal flushes the draft against the goal being left", async () => {
    const { result, rerender } = renderHook(({ goal }) => useTimelineComposer(goal), {
      initialProps: { goal: makeGoal("A") },
    })

    // Wait for A's pending update to load so the draft captures its update_id.
    await waitFor(() => expect(result.current.pendingUpdate?.id).toBe("u-A"))

    act(() => result.current.saveDraft(draftData))
    expect(draftPosts()).toHaveLength(0)

    // Stepper swap to goal B before the 2s debounce fires.
    act(() => rerender({ goal: makeGoal("B") }))

    const posts = draftPosts()
    expect(posts).toHaveLength(1)
    const [url, options] = posts[0]
    // The flush targets the goal being LEFT (A), not the newly-selected goal (B).
    expect(url).toBe("/api/goals/A/updates")
    const body = JSON.parse(options!.body as string)
    expect(body.update_id).toBe("u-A")
    expect(body.answer_text).toBe("My latest edit")
  })

  test("a submit-triggered navigation does not flush a draft", async () => {
    const { result, rerender } = renderHook(({ goal }) => useTimelineComposer(goal), {
      initialProps: { goal: makeGoal("A") },
    })

    await waitFor(() => expect(result.current.pendingUpdate?.id).toBe("u-A"))

    act(() => result.current.saveDraft(draftData))
    // submitUpdate cancels the armed draft before POSTing the completing update.
    await act(async () => {
      await result.current.submitUpdate(draftData)
    })

    act(() => rerender({ goal: makeGoal("B") }))

    expect(draftPosts()).toHaveLength(0)
  })
})
