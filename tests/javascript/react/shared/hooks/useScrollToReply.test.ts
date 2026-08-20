import { act, renderHook } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("~/shared/flash", () => ({ showFlash: vi.fn() }))

import { showFlash } from "~/shared/flash"
import { useScrollToReply } from "~/react/shared/hooks/useScrollToReply"
import type { MessageWindowResponse } from "~/react/shared/types"

const NOT_FOUND_MESSAGE = "Couldn't find the original message."
const mockedShowFlash = vi.mocked(showFlash)

beforeEach(() => {
  vi.useFakeTimers()
  // The hook awaits two nested requestAnimationFrame calls (waitForRender); run
  // them synchronously so the await resolves without a real frame, and a 250ms
  // setTimeout (waitForSettle) which fake timers drive.
  vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => {
    cb(0)
    return 0
  })
  document.body.innerHTML = ""
})

afterEach(() => {
  vi.restoreAllMocks()
  vi.useRealTimers()
})

function mountMessage(id: string): HTMLElement {
  const el = document.createElement("div")
  el.id = `chat-message-${id}`
  vi.spyOn(el, "scrollIntoView").mockImplementation(() => {})
  document.body.appendChild(el)
  return el
}

function windowResponse(overrides: Partial<MessageWindowResponse> = {}): MessageWindowResponse {
  return { messages: [], next_cursor: null, has_more: false, at_tail: true, ...overrides }
}

// After a jump, scrollToReply resolves only past a 250ms waitForSettle.
// Advancing fake timers releases that await; repeat until the promise settles.
async function runToCompletion(promise: Promise<unknown>) {
  let settled = false
  promise.finally(() => {
    settled = true
  })
  for (let i = 0; i < 200 && !settled; i++) {
    await act(async () => {
      await vi.advanceTimersByTimeAsync(300)
    })
  }
}

describe("useScrollToReply", () => {
  // Positive control: a target already in the DOM is smooth-scrolled to and
  // highlighted directly, without invoking jumpToMessage.
  it("scrolls to and highlights a target already in the DOM without jumping", async () => {
    const el = mountMessage("target")
    const jumpToMessage = vi.fn(async () => windowResponse())
    const { result } = renderHook(() => useScrollToReply(jumpToMessage))

    await act(async () => {
      await runToCompletion(result.current.scrollToReply("target"))
    })

    expect(jumpToMessage).not.toHaveBeenCalled()
    expect(el.scrollIntoView).toHaveBeenCalled()
    expect(el.classList.contains("chat-message-highlight")).toBe(true)
    expect(mockedShowFlash).not.toHaveBeenCalledWith(NOT_FOUND_MESSAGE)
  })

  // Regression test for issue #7744 — "Chat: Quote replies". A quoted original
  // that is not loaded (any depth) is reached via jumpToMessage, which fetches a
  // window AROUND the anchor and replaces the list; the element appears, gets
  // scrolled to and highlighted, with no not-found flash. The old loop capped at
  // MAX_PAGES (50) and bailed with the flash; the window jump is depth-independent.
  it("jumps to and highlights a target that is not loaded (issue #7744)", async () => {
    const jumpToMessage = vi.fn(async (messageId: string) => {
      // Simulate the window replacing the list: the target's node now exists.
      mountMessage(messageId)
      return windowResponse({ at_tail: false, has_more: true })
    })
    const { result } = renderHook(() => useScrollToReply(jumpToMessage))

    await act(async () => {
      await runToCompletion(result.current.scrollToReply("ancient"))
    })

    const el = document.getElementById("chat-message-ancient")
    expect(jumpToMessage).toHaveBeenCalledWith("ancient")
    expect(el).not.toBeNull()
    expect(el!.scrollIntoView).toHaveBeenCalled()
    expect(el!.classList.contains("chat-message-highlight")).toBe(true)
    expect(mockedShowFlash).not.toHaveBeenCalledWith(NOT_FOUND_MESSAGE)
  })

  // When the anchor can't be loaded (404/error → null), the hook shows the
  // not-found flash and highlights nothing.
  it("shows the not-found flash when jumpToMessage can't find the anchor", async () => {
    const jumpToMessage = vi.fn(async () => null)
    const { result } = renderHook(() => useScrollToReply(jumpToMessage))

    await act(async () => {
      await runToCompletion(result.current.scrollToReply("gone"))
    })

    expect(jumpToMessage).toHaveBeenCalledWith("gone")
    expect(document.getElementById("chat-message-gone")).toBeNull()
    expect(mockedShowFlash).toHaveBeenCalledWith(NOT_FOUND_MESSAGE)
  })
})
