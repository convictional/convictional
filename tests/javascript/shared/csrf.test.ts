import { expect, test, describe, vi, beforeEach, afterEach } from "vitest"
import {
  initSessionBroadcast,
  fetchWithCSRF,
  isCSRFFailure,
  resetSessionChangedFlag,
  SESSION_CHANGED_MESSAGE,
} from "../../../app/javascript/shared/csrf"
import { showFlash } from "../../../app/javascript/shared/flash"

vi.mock("../../../app/javascript/shared/flash", () => ({
  showFlash: vi.fn(),
}))

class MockBroadcastChannel {
  static instances: MockBroadcastChannel[] = []
  name: string
  onmessage: ((event: MessageEvent) => void) | null = null

  constructor(name: string) {
    this.name = name
    MockBroadcastChannel.instances.push(this)
  }

  postMessage(message: unknown): void {
    const event = new MessageEvent("message", { data: message })
    for (const instance of MockBroadcastChannel.instances) {
      if (instance !== this && instance.name === this.name) {
        instance.onmessage?.(event)
      }
    }
  }

  close(): void {
    const index = MockBroadcastChannel.instances.indexOf(this)
    if (index > -1) {
      MockBroadcastChannel.instances.splice(index, 1)
    }
  }

  static clear(): void {
    MockBroadcastChannel.instances = []
  }
}

function setMeta(token: string, sessionCreatedAt: string): void {
  let meta = document.querySelector<HTMLMetaElement>('meta[name="csrf-token"]')
  if (!meta) {
    meta = document.createElement("meta")
    meta.name = "csrf-token"
    document.head.appendChild(meta)
  }
  meta.content = token
  meta.dataset.sessionCreatedAt = sessionCreatedAt
}

function removeMeta(): void {
  document.querySelector('meta[name="csrf-token"]')?.remove()
}

function setAuthenticated(value: boolean): void {
  if (value) {
    document.body.dataset.authenticated = "true"
  } else {
    delete document.body.dataset.authenticated
  }
}

describe("sessionBroadcast", () => {
  beforeEach(() => {
    vi.stubGlobal("BroadcastChannel", MockBroadcastChannel)
    MockBroadcastChannel.clear()
    setMeta("csrf-token-abc", "2026-02-24T10:00:00+00:00")
    setAuthenticated(true)
  })

  afterEach(() => {
    removeMeta()
    setAuthenticated(false)
    MockBroadcastChannel.clear()
    vi.unstubAllGlobals()
    vi.mocked(showFlash).mockClear()
    resetSessionChangedFlag()
  })

  test("broadcasts session_created_at on init", () => {
    const listener = new MockBroadcastChannel("convictional-session")
    let received: string | null = null
    listener.onmessage = (event: MessageEvent<string>) => {
      received = event.data
    }

    initSessionBroadcast()

    expect(received).toBe("2026-02-24T10:00:00+00:00")
    listener.close()
  })

  test("shows flash when receiving a different session timestamp", () => {
    initSessionBroadcast()
    const channel = MockBroadcastChannel.instances[0]

    channel.onmessage!(new MessageEvent("message", { data: "2026-02-24T11:00:00+00:00" }))

    expect(showFlash).toHaveBeenCalledWith(
      SESSION_CHANGED_MESSAGE,
      "error",
      window.location.href,
      true,
    )
  })

  test("does not show flash when receiving the same session timestamp", () => {
    initSessionBroadcast()
    const channel = MockBroadcastChannel.instances[0]

    channel.onmessage!(new MessageEvent("message", { data: "2026-02-24T10:00:00+00:00" }))

    expect(showFlash).not.toHaveBeenCalled()
  })

  test("ignores broadcast on unauthenticated pages", () => {
    setAuthenticated(false)
    initSessionBroadcast()
    const channel = MockBroadcastChannel.instances[0]

    channel.onmessage!(new MessageEvent("message", { data: "2026-02-24T11:00:00+00:00" }))

    expect(showFlash).not.toHaveBeenCalled()
  })

  test("logout broadcasts empty string which triggers flash on authenticated tabs", () => {
    initSessionBroadcast()
    const channel = MockBroadcastChannel.instances[0]

    // Another tab logged out and broadcast "" — differs from our timestamp
    channel.onmessage!(new MessageEvent("message", { data: "" }))

    expect(showFlash).toHaveBeenCalledWith(
      SESSION_CHANGED_MESSAGE,
      "error",
      window.location.href,
      true,
    )
  })

  test("only shows session-changed flash once per tab", () => {
    initSessionBroadcast()
    const channel = MockBroadcastChannel.instances[0]

    channel.onmessage!(new MessageEvent("message", { data: "2026-02-24T11:00:00+00:00" }))
    channel.onmessage!(new MessageEvent("message", { data: "2026-02-24T12:00:00+00:00" }))

    expect(showFlash).toHaveBeenCalledTimes(1)
  })

  test("broadcasts empty string when no meta tag exists", () => {
    removeMeta()
    const listener = new MockBroadcastChannel("convictional-session")
    let received: string | null = null
    listener.onmessage = (event: MessageEvent<string>) => {
      received = event.data
    }

    initSessionBroadcast()

    expect(received).toBe("")
    listener.close()
  })
})

describe("isCSRFFailure", () => {
  test("returns true for 403 with CSRF header", () => {
    expect(isCSRFFailure(403, true)).toBe(true)
  })

  test("returns false for 403 without CSRF header", () => {
    expect(isCSRFFailure(403, false)).toBe(false)
  })

  test("returns false for non-403 status", () => {
    expect(isCSRFFailure(200, true)).toBe(false)
  })
})

describe("fetchWithCSRF", () => {
  beforeEach(() => {
    vi.stubGlobal("BroadcastChannel", MockBroadcastChannel)
    MockBroadcastChannel.clear()
    setMeta("original-token", "2026-02-24T10:00:00+00:00")
    initSessionBroadcast()
  })

  afterEach(() => {
    removeMeta()
    MockBroadcastChannel.clear()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
    vi.mocked(showFlash).mockClear()
    resetSessionChangedFlag()
  })

  test("attaches CSRF token to requests", async () => {
    const mockResponse = new Response("ok", { status: 200 })
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(mockResponse))

    const result = await fetchWithCSRF("/api/test")

    expect(fetch).toHaveBeenCalledTimes(1)
    const headers = (fetch as ReturnType<typeof vi.fn>).mock.calls[0][1].headers
    expect(headers["X-CSRFToken"]).toBe("original-token")
    expect(result.status).toBe(200)
  })

  test("shows flash on CSRF failure", async () => {
    const mockResponse = new Response("forbidden", {
      status: 403,
      headers: { "X-CSRF-Failure": "true" },
    })
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(mockResponse))

    const result = await fetchWithCSRF("/api/test")

    expect(showFlash).toHaveBeenCalledWith(
      SESSION_CHANGED_MESSAGE,
      "error",
      window.location.href,
      true,
    )
    expect(result.status).toBe(403)
  })

  test("does not show flash on non-CSRF 403", async () => {
    const mockResponse = new Response("forbidden", { status: 403 })
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(mockResponse))

    const result = await fetchWithCSRF("/api/test")

    expect(showFlash).not.toHaveBeenCalled()
    expect(result.status).toBe(403)
  })
})
