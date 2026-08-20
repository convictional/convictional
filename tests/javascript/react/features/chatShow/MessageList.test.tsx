import { act, cleanup, fireEvent, render, screen } from "@testing-library/react"
import React from "react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

import { MessageList } from "../../../../../app/javascript/react/features/chatShow/MessageList"
import type { ChatMessage } from "../../../../../app/javascript/react/shared/types"

// Heavy child — its rendering isn't under test here, and stubbing it lets us
// keep messages prop minimal and avoid Avatar/Tooltip/MessageActions dependencies.
vi.mock("../../../../../app/javascript/react/composites/chat/InteractiveMessageBubble", () => ({
  InteractiveMessageBubble: ({ message }: { message: ChatMessage }) => (
    <div data-testid={`bubble-${message.id}`}>{message.content}</div>
  ),
}))

const SCROLL_HEIGHT = 5000
const INNER_HEIGHT = 800

let scrollY: number
let scrollHeight: number
let scrollToSpy: ReturnType<typeof vi.fn>
let resizeObserverCallbacks: ResizeObserverCallback[]
let intersectionObserverCallbacks: IntersectionObserverCallback[]
let intersectionObserverInits: (IntersectionObserverInit | undefined)[]
let intersectionObserverCtor: ReturnType<typeof vi.fn>

function setScrollY(value: number) {
  scrollY = value
  Object.defineProperty(window, "scrollY", { configurable: true, get: () => scrollY })
}

function setScrollHeight(value: number) {
  scrollHeight = value
}

function fireWindowScroll() {
  window.dispatchEvent(new Event("scroll"))
}

function fireIntersection(isIntersecting: boolean) {
  act(() => {
    intersectionObserverCallbacks.forEach(cb =>
      cb([{ isIntersecting } as IntersectionObserverEntry], {} as IntersectionObserver)
    )
  })
}

function makeMessage(overrides: Partial<ChatMessage> = {}): ChatMessage {
  return {
    id: "msg-1",
    global_id: "gid://convictional/ChatMessage/msg-1",
    content: "Hello",
    created_at: "2026-04-30T12:00:00Z",
    edited_at: null,
    reactions: {},
    user: { id: "user-other", display_name: "Alice", picture: null },
    link_preview: null,
    reply_to: null,
    ...overrides,
  }
}

function defaultProps(messages: ChatMessage[]) {
  return {
    messages,
    loadingMore: false,
    hasMore: false,
    currentUserId: "user-self",
    chatTitle: "Test Chat",
    chatType: "dm" as const,
    isGroupChat: false,
    editingMessageId: null,
    lastReadAt: null,
    unreadMessageCount: 0,
    onLoadMore: vi.fn().mockResolvedValue(undefined),
    onLoadNewer: vi.fn().mockResolvedValue(undefined),
    loadingNewer: false,
    hasNewer: false,
    onScrollTo: vi.fn(),
    scrollingToReplyRef: { current: false } as React.RefObject<boolean>,
    scrollingToId: null,
    atTail: true,
    onJumpToLatest: vi.fn(),
    onEdit: vi.fn(),
    onCancelEdit: vi.fn(),
    onSaveEdit: vi.fn().mockResolvedValue(undefined),
    onDelete: vi.fn(),
    onReact: vi.fn(),
    onReply: vi.fn(),
    decisionsByGid: new Map(),
    onToggleDecision: vi.fn(),
  }
}

beforeEach(() => {
  setScrollHeight(SCROLL_HEIGHT)
  setScrollY(SCROLL_HEIGHT - INNER_HEIGHT) // start at bottom (autoScroll=true)
  Object.defineProperty(window, "innerHeight", { value: INNER_HEIGHT, configurable: true, writable: true })
  Object.defineProperty(document.documentElement, "scrollHeight", {
    configurable: true,
    get: () => scrollHeight,
  })
  scrollToSpy = vi.fn()
  window.scrollTo = scrollToSpy as unknown as typeof window.scrollTo

  resizeObserverCallbacks = []
  vi.stubGlobal(
    "ResizeObserver",
    vi.fn(function (cb: ResizeObserverCallback) {
      resizeObserverCallbacks.push(cb)
      return { observe: vi.fn(), disconnect: vi.fn(), unobserve: vi.fn() }
    })
  )
  intersectionObserverCallbacks = []
  intersectionObserverInits = []
  intersectionObserverCtor = vi.fn(function (cb: IntersectionObserverCallback, init?: IntersectionObserverInit) {
    intersectionObserverCallbacks.push(cb)
    intersectionObserverInits.push(init)
    return {
      observe: vi.fn(),
      disconnect: vi.fn(() => {
        intersectionObserverCallbacks = intersectionObserverCallbacks.filter(c => c !== cb)
      }),
      unobserve: vi.fn(),
    }
  })
  vi.stubGlobal("IntersectionObserver", intersectionObserverCtor)
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

function fireResize() {
  // Fires every registered observer's callback. The hook only checks scroll
  // state, not the entries payload, so an empty array is sufficient.
  act(() => {
    resizeObserverCallbacks.forEach(cb => cb([], {} as ResizeObserver))
  })
}

describe("MessageList sticky-bottom", () => {
  test("pins to the bottom on mount", () => {
    render(<MessageList {...defaultProps([makeMessage()])} />)

    expect(scrollToSpy).toHaveBeenCalledWith({ top: SCROLL_HEIGHT - INNER_HEIGHT, behavior: "instant" })
  })

  test("re-pins when the wrapper resizes while autoScroll is true", () => {
    render(<MessageList {...defaultProps([makeMessage()])} />)
    scrollToSpy.mockClear()

    fireResize()

    expect(scrollToSpy).toHaveBeenCalledWith({ top: SCROLL_HEIGHT - INNER_HEIGHT, behavior: "instant" })
  })

  test("does not re-pin on wrapper resize after the user scrolls up", () => {
    render(<MessageList {...defaultProps([makeMessage()])} />)
    scrollToSpy.mockClear()

    // Scroll well above the bottom-anchor threshold (50px) so handleScroll
    // flips autoScroll to false.
    act(() => {
      setScrollY(1000)
      fireWindowScroll()
    })

    fireResize()

    expect(scrollToSpy).not.toHaveBeenCalled()
  })

  test("snaps to bottom when the current user sends a new message even if scrolled up", () => {
    const initial = [makeMessage({ id: "m1" })]
    const { rerender } = render(<MessageList {...defaultProps(initial)} />)

    // User scrolls up — autoScroll becomes false
    act(() => {
      setScrollY(1000)
      fireWindowScroll()
    })
    scrollToSpy.mockClear()

    const ownMessage = makeMessage({ id: "m2", user: { id: "user-self", display_name: "Me", picture: null } })
    rerender(<MessageList {...defaultProps([...initial, ownMessage])} />)

    // The own-message effect schedules scrollTo via requestAnimationFrame.
    // Run microtasks so the rAF callback fires.
    return new Promise<void>(resolve => {
      requestAnimationFrame(() => {
        expect(scrollToSpy).toHaveBeenCalledWith({ top: SCROLL_HEIGHT - INNER_HEIGHT, behavior: "instant" })
        resolve()
      })
    })
  })

  test("does not snap to bottom on an other-user message when scrolled up", () => {
    const initial = [makeMessage({ id: "m1" })]
    const { rerender } = render(<MessageList {...defaultProps(initial)} />)

    act(() => {
      setScrollY(1000)
      fireWindowScroll()
    })
    scrollToSpy.mockClear()

    const incoming = makeMessage({ id: "m2", user: { id: "user-other-2", display_name: "Bob", picture: null } })
    rerender(<MessageList {...defaultProps([...initial, incoming])} />)

    return new Promise<void>(resolve => {
      requestAnimationFrame(() => {
        expect(scrollToSpy).not.toHaveBeenCalled()
        resolve()
      })
    })
  })

  test("adapts re-pinning to layout growth, the 50px tolerance, and re-entry to the bottom", () => {
    // One walkthrough of the autoScroll detection contract. (a) After the
    // initial pin, growing scrollHeight (cold-cache image-load case) re-pins
    // to the new bottom. (b) A scroll within 50px of the bottom is still
    // "at bottom" so resize re-pins. (c) After the user scrolls clearly up,
    // resize is a no-op. (d) When the user returns to the bottom, autoScroll
    // re-enables and resize re-pins.
    render(<MessageList {...defaultProps([makeMessage()])} />)
    expect(scrollToSpy).toHaveBeenCalledWith({ top: SCROLL_HEIGHT - INNER_HEIGHT, behavior: "instant" })

    // (a) Document grows after first paint.
    setScrollHeight(SCROLL_HEIGHT + 3000)
    scrollToSpy.mockClear()
    fireResize()
    expect(scrollToSpy).toHaveBeenLastCalledWith({ top: SCROLL_HEIGHT + 3000 - INNER_HEIGHT, behavior: "instant" })

    // (b) Within the 50px tolerance — still treated as at the bottom.
    act(() => {
      setScrollY(SCROLL_HEIGHT + 3000 - INNER_HEIGHT - 30)
      fireWindowScroll()
    })
    scrollToSpy.mockClear()
    fireResize()
    expect(scrollToSpy).toHaveBeenCalled()

    // (c) Clear scroll up — autoScroll flips false, resize is a no-op.
    act(() => {
      setScrollY(1000)
      fireWindowScroll()
    })
    scrollToSpy.mockClear()
    fireResize()
    expect(scrollToSpy).not.toHaveBeenCalled()

    // (d) Back to bottom — autoScroll re-enables.
    act(() => {
      setScrollY(SCROLL_HEIGHT + 3000 - INNER_HEIGHT)
      fireWindowScroll()
    })
    fireResize()
    expect(scrollToSpy).toHaveBeenCalled()
  })
})

describe("MessageList pagination via IntersectionObserver", () => {
  test("manages the load-more observer lifecycle and respects every gate", async () => {
    // Gates this contract covers in one walk: (a) no observer when hasMore is
    // false, (b) when hasMore flips true, exactly one observer is created
    // with a top-only rootMargin and threshold 0, (c) the IO callback calls
    // onLoadMore on intersect, (d) it does NOT call onLoadMore when not
    // intersecting or when scrollingToReplyRef is held, (e) re-entrant
    // intersects while a load is in flight are gated (no double-fire), (f)
    // loadingMore prop toggles do NOT rebuild the observer — the gate is
    // owned by the component, not derived from props, (g) once the in-flight
    // load settles the gate releases and the next intersect fires again.
    // (h) the observer is NOT created on initial mount while autoScroll is true
    // (user at bottom), even if hasMore is true; the bottom-pin still runs,
    // (i) when the user scrolls up, the observer IS created; when they return to
    // the bottom, the observer is disconnected and subsequent intersections do not
    // call onLoadMore; on a subsequent scroll-up, a new observer is created.
    let resolveLoad: () => void = () => {}
    const onLoadMore = vi.fn(
      () =>
        new Promise<void>(resolve => {
          resolveLoad = resolve
        })
    )
    const scrollingToReplyRef = { current: false } as React.RefObject<boolean>
    const props = (overrides: Partial<React.ComponentProps<typeof MessageList>> = {}) => ({
      ...defaultProps([makeMessage()]),
      onLoadMore,
      scrollingToReplyRef,
      ...overrides,
    })

    // (a) hasMore=false → no observer.
    const { rerender } = render(<MessageList {...props({ hasMore: false })} />)
    expect(intersectionObserverCtor).not.toHaveBeenCalled()

    // (b) hasMore flips true — scroll-up first so autoScroll becomes false, then rerender.
    act(() => {
      setScrollY(1000)
      fireWindowScroll()
    })
    rerender(<MessageList {...props({ hasMore: true })} />)
    expect(intersectionObserverCtor).toHaveBeenCalledTimes(1)
    expect(intersectionObserverInits[0]).toMatchObject({ threshold: 0 })
    expect(intersectionObserverInits[0]!.rootMargin).toMatch(/^\d+px 0px 0px 0px$/)

    // (c) Intersect → onLoadMore.
    fireIntersection(true)
    expect(onLoadMore).toHaveBeenCalledTimes(1)

    // (d) Non-intersect and scrolling-to-reply → no further calls.
    fireIntersection(false)
    scrollingToReplyRef.current = true
    fireIntersection(true)
    expect(onLoadMore).toHaveBeenCalledTimes(1)
    scrollingToReplyRef.current = false

    // (e) Re-entrant intersect while the load is in flight is gated.
    fireIntersection(true)
    expect(onLoadMore).toHaveBeenCalledTimes(1)

    // (f) loadingMore prop toggles do NOT rebuild the observer. The gate
    // lives in the component (a synchronous ref) so an async parent flip of
    // `loadingMore` can't open a window for double-fire by tearing the
    // observer down and back up.
    rerender(<MessageList {...props({ hasMore: true, loadingMore: true })} />)
    expect(intersectionObserverCtor).toHaveBeenCalledTimes(1)
    rerender(<MessageList {...props({ hasMore: true, loadingMore: false })} />)
    expect(intersectionObserverCtor).toHaveBeenCalledTimes(1)

    // (g) Resolve the in-flight load → gate releases → next intersect fires.
    await act(async () => {
      resolveLoad()
      // Flush the .finally microtask that releases the gate.
      await Promise.resolve()
      await Promise.resolve()
    })
    fireIntersection(true)
    expect(onLoadMore).toHaveBeenCalledTimes(2)

    // Reset state so only a fresh component is mounted for sub-cases (h)-(k).
    cleanup()
    setScrollY(SCROLL_HEIGHT - INNER_HEIGHT)
    onLoadMore.mockClear()
    scrollToSpy.mockClear()
    intersectionObserverCtor.mockClear()

    // (h) At-bottom mount with hasMore=true: no observer is created; bottom-pin fires.
    render(<MessageList {...props({ hasMore: true, lastReadAt: "2026-04-20T12:00:00Z", unreadMessageCount: 5 })} />)
    expect(scrollToSpy).toHaveBeenCalledWith({ top: SCROLL_HEIGHT - INNER_HEIGHT, behavior: "instant" })
    expect(intersectionObserverCtor).not.toHaveBeenCalled()

    // (i) Scroll up → observer is created; intersect fires onLoadMore.
    onLoadMore.mockClear()
    intersectionObserverCtor.mockClear()
    act(() => {
      setScrollY(1000)
      fireWindowScroll()
    })
    expect(intersectionObserverCtor).toHaveBeenCalledTimes(1)
    fireIntersection(true)
    expect(onLoadMore).toHaveBeenCalledTimes(1)

    // (j) Scroll back to bottom → observer is disconnected; subsequent intersects are no-ops.
    onLoadMore.mockClear()
    act(() => {
      setScrollY(SCROLL_HEIGHT - INNER_HEIGHT)
      fireWindowScroll()
    })
    expect(intersectionObserverCtor).toHaveBeenCalledTimes(1) // no new observer created on return-to-bottom
    fireIntersection(true)
    expect(onLoadMore).not.toHaveBeenCalled()

    // (k) Re-scroll up → a new observer is built; intersect fires again.
    act(() => {
      setScrollY(1000)
      fireWindowScroll()
    })
    expect(intersectionObserverCtor).toHaveBeenCalledTimes(2)
    fireIntersection(true)
    expect(onLoadMore).toHaveBeenCalledTimes(1)
  })
})

describe("MessageList rendering states", () => {
  test("renders chat-end indicator, unread divider, and unread pill across the matrix", () => {
    // (a) hasMore=false + messages → "Beginning of chat with Alice".
    const { rerender } = render(
      <MessageList {...defaultProps([makeMessage()])} hasMore={false} chatTitle="Alice" chatType="dm" />
    )
    expect(screen.getByText(/Beginning of chat with Alice/i)).toBeInTheDocument()

    // (b) hasMore=true + lastReadAt mid-list → divider above the first unread.
    const dividerMessages = [
      makeMessage({ id: "m1", created_at: "2026-04-30T12:00:00Z" }),
      makeMessage({ id: "m2", created_at: "2026-04-30T12:01:00Z" }),
      makeMessage({ id: "m3", created_at: "2026-04-30T12:02:00Z" }),
    ]
    rerender(
      <MessageList
        {...defaultProps(dividerMessages)}
        hasMore={true}
        lastReadAt="2026-04-30T12:00:30Z"
        unreadMessageCount={2}
      />
    )
    expect(screen.getByLabelText("New messages divider")).toBeInTheDocument()
    expect(screen.getByText(/2 new messages/i)).toBeInTheDocument()

    // (c) Every loaded message unread + hasMore=true → pill (no in-list divider).
    const allUnread = [
      makeMessage({ id: "m1", created_at: "2026-04-30T12:01:00Z" }),
      makeMessage({ id: "m2", created_at: "2026-04-30T12:02:00Z" }),
    ]
    rerender(
      <MessageList
        {...defaultProps(allUnread)}
        hasMore={true}
        lastReadAt="2026-04-30T12:00:00Z"
        unreadMessageCount={5}
      />
    )
    expect(screen.queryByLabelText("New messages divider")).not.toBeInTheDocument()
    expect(screen.getByRole("button", { name: /5 unread messages/i })).toBeInTheDocument()

    // (d) Same shape but hasMore=false → suppress pill (it would lead nowhere).
    rerender(
      <MessageList
        {...defaultProps(allUnread)}
        hasMore={false}
        lastReadAt="2026-04-30T12:00:00Z"
        unreadMessageCount={2}
      />
    )
    expect(screen.queryByRole("button", { name: /unread message/i })).not.toBeInTheDocument()
  })
})

describe("MessageList not-at-tail pill, forward pagination, and gating", () => {
  test("not-at-tail shows a 'Jump to latest' pill routing to onJumpToLatest", () => {
    const onJumpToLatest = vi.fn()
    render(<MessageList {...defaultProps([makeMessage()])} atTail={false} onJumpToLatest={onJumpToLatest} />)
    fireEvent.click(screen.getByRole("button", { name: /Jump to latest/i }))
    expect(onJumpToLatest).toHaveBeenCalledOnce()
  })

  test("does not pin to the bottom while not at the tail", () => {
    render(<MessageList {...defaultProps([makeMessage()])} atTail={false} />)
    // Mount pin and resize re-pin are both gated off.
    expect(scrollToSpy).not.toHaveBeenCalled()
    scrollToSpy.mockClear()
    fireResize()
    expect(scrollToSpy).not.toHaveBeenCalled()
  })

  test("forward-pagination observer fires onLoadNewer on bottom-sentinel intersect while not at the tail", () => {
    // While not at the tail, intersecting the bottom sentinel pulls the next
    // newer page (the mirror of load-more near the top), with a bottom-only
    // rootMargin. The same self-owned re-entrancy gate prevents double-fire.
    const onLoadNewer = vi.fn().mockResolvedValue(undefined)
    render(
      <MessageList {...defaultProps([makeMessage()])} atTail={false} hasNewer={true} onLoadNewer={onLoadNewer} />
    )
    // A fresh observer exists for the bottom sentinel.
    const init = intersectionObserverInits[intersectionObserverInits.length - 1]
    expect(init).toMatchObject({ threshold: 0 })
    expect(init!.rootMargin).toMatch(/^0px 0px \d+px 0px$/)

    fireIntersection(true)
    expect(onLoadNewer).toHaveBeenCalledTimes(1)
    // Re-entrant intersect while in flight is gated.
    fireIntersection(true)
    expect(onLoadNewer).toHaveBeenCalledTimes(1)
  })

  test("does not observe forward pagination once at the tail", () => {
    intersectionObserverCtor.mockClear()
    render(<MessageList {...defaultProps([makeMessage()])} atTail={true} hasNewer={false} />)
    expect(intersectionObserverCtor).not.toHaveBeenCalled()
  })

  test("snaps to the live bottom when jumpToLatest reloads the tail while scrolled up", () => {
    // After jumping to an old message the user is scrolled up (autoScroll
    // false), so the autoScroll-gated pins don't fire. jumpToLatest replaces
    // the window with the newest page and flips atTail true; it must snap to the
    // real bottom, not leave the user parked mid-history.
    const { rerender } = render(<MessageList {...defaultProps([makeMessage({ id: "old" })])} atTail={false} />)

    // Scrolled up inside the historical window — autoScroll is false.
    act(() => {
      setScrollY(1000)
      fireWindowScroll()
    })
    scrollToSpy.mockClear()

    // reload() has replaced the list with the newest page; atTail flips true and
    // the list does NOT grow from the window (window was 1, newest page is 1).
    rerender(<MessageList {...defaultProps([makeMessage({ id: "newest" })])} atTail={true} />)

    expect(scrollToSpy).toHaveBeenCalledWith({ top: SCROLL_HEIGHT - INNER_HEIGHT, behavior: "instant" })
  })

  test("does NOT snap when forward pagination reaches the tail by appending (list grew)", () => {
    // loadNewer flips atTail false->true too, but it keeps the user mid-thread.
    // Snapping there would be jarring, so the edge effect skips when the list
    // grew (append) rather than being replaced by a fresh page.
    const oldList = [makeMessage({ id: "a" }), makeMessage({ id: "b" })]
    const { rerender } = render(<MessageList {...defaultProps(oldList)} atTail={false} hasNewer={true} />)

    act(() => {
      setScrollY(1000)
      fireWindowScroll()
    })
    scrollToSpy.mockClear()

    // loadNewer appended a newer page and reached the tail: list grew, atTail true.
    rerender(<MessageList {...defaultProps([...oldList, makeMessage({ id: "c" })])} atTail={true} />)

    expect(scrollToSpy).not.toHaveBeenCalled()
  })
})

describe("MessageList programmatic scroll signaling", () => {
  test("dispatches island:programmatic-scroll before any internal scroll", () => {
    // The auto-hiding nav listens for this event to suppress its `top`
    // transition during programmatic scrolls — without it, WebKit's
    // scroll-anchor algorithm reacts to the nav's mid-pin layout shift and
    // drags scrollY backwards. Lock in that the event fires.
    const handler = vi.fn()
    window.addEventListener("island:programmatic-scroll", handler)
    try {
      render(<MessageList {...defaultProps([makeMessage()])} />)
      expect(handler).toHaveBeenCalled()
      expect(scrollToSpy).toHaveBeenCalledWith({ top: SCROLL_HEIGHT - INNER_HEIGHT, behavior: "instant" })
    } finally {
      window.removeEventListener("island:programmatic-scroll", handler)
    }
  })
})
