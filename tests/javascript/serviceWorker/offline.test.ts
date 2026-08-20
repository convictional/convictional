import fs from "node:fs"
import path from "node:path"
import { beforeEach, describe, expect, test, vi } from "vitest"

// The service worker is plain JS served from /static/service-worker.js so the
// browser can register it at the root scope. It isn't a module and references
// SW globals (`self`, `caches`). We load the source and run it inside a
// `new Function` shell so its globals come from mocks we control here.

const SW_SOURCE = fs.readFileSync(
  path.resolve(import.meta.dirname, "../../../static/service-worker.js"),
  "utf-8",
)

type Handlers = {
  install?: (event: ExtendableEvent) => void
  activate?: (event: ExtendableEvent) => void
  fetch?: (event: FetchEvent) => void
  // The SW also registers push / pushsubscriptionchange / notificationclick.
  // We don't exercise those here; capturing them avoids "undefined handler"
  // surprises if registration order changes.
  push?: (event: PushEvent) => void
  pushsubscriptionchange?: (event: Event) => void
  notificationclick?: (event: NotificationEvent) => void
}

type ExtendableEvent = { waitUntil: (promise: Promise<unknown>) => void }
type RequestLike = { url: string; mode?: string }
type FetchEvent = ExtendableEvent & {
  request: RequestLike
  respondWith: (response: Response | Promise<Response>) => void
}
type PushEvent = ExtendableEvent & { data: { json: () => unknown } | null }
type NotificationEvent = ExtendableEvent & { notification: { close: () => void; data: unknown } }

function loadServiceWorker() {
  const handlers: Handlers = {}
  const cacheStore = new Map<string, Map<string, Response>>()

  const cacheFor = (name: string) => {
    if (!cacheStore.has(name)) cacheStore.set(name, new Map())
    return cacheStore.get(name)!
  }

  const fakeCaches = {
    open: vi.fn(async (name: string) => ({
      add: vi.fn(async (req: RequestLike | string) => {
        const url = typeof req === "string" ? req : req.url
        // Real Cache.add issues the fetch itself; we simulate the result with
        // a placeholder Response so match() returns something truthy later.
        cacheFor(name).set(url, new Response("cached-body", { status: 200 }))
      }),
      addAll: vi.fn(async (requests: (RequestLike | string)[]) => {
        for (const req of requests) {
          const url = typeof req === "string" ? req : req.url
          cacheFor(name).set(url, new Response("cached-body", { status: 200 }))
        }
      }),
      match: vi.fn(async (req: RequestLike | string) => {
        const url = typeof req === "string" ? req : req.url
        return cacheFor(name).get(url) ?? undefined
      }),
    })),
    keys: vi.fn(async () => Array.from(cacheStore.keys())),
    delete: vi.fn(async (name: string) => cacheStore.delete(name)),
    match: vi.fn(),
  }

  // jsdom's `Request` rejects relative URLs (the SW caches "/static/offline.html")
  // and the `navigate` mode (the SW only intercepts mode === "navigate"). Pass a
  // lightweight shim into the SW closure so neither constraint matters here.
  class FakeRequest implements RequestLike {
    url: string
    mode?: string
    cache?: string
    constructor(url: string, init?: { mode?: string; cache?: string }) {
      this.url = url
      this.mode = init?.mode
      this.cache = init?.cache
    }
  }

  const fakeSelf = {
    addEventListener: vi.fn((event: keyof Handlers, handler: Handlers[keyof Handlers]) => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      handlers[event] = handler as any
    }),
    skipWaiting: vi.fn(),
    clients: {
      claim: vi.fn(async () => undefined),
      matchAll: vi.fn(async () => []),
      openWindow: vi.fn(),
    },
    registration: {
      showNotification: vi.fn(),
      pushManager: { subscribe: vi.fn() },
    },
  }

  // `new Function` runs the SW source with `self` / `caches` / `Request`
  // resolved to our mocks. Other SW globals (`fetch`, `Response`, `URL`,
  // `atob`, `btoa`, `navigator`) come from jsdom and don't need stubbing
  // here — the push handlers that would use them never fire in these tests.
  const exec = new Function("self", "caches", "Request", SW_SOURCE)
  exec(fakeSelf, fakeCaches, FakeRequest)

  return { handlers, fakeSelf, fakeCaches, cacheStore }
}

function makeExtendableEvent(): ExtendableEvent & { settled: Promise<unknown> } {
  let settled: Promise<unknown> = Promise.resolve()
  return {
    waitUntil(promise: Promise<unknown>) {
      settled = promise
    },
    get settled() {
      return settled
    },
  }
}

function makeFetchEvent(request: RequestLike): FetchEvent & {
  response: Promise<Response> | null
  settled: Promise<unknown>
} {
  let response: Promise<Response> | null = null
  let settled: Promise<unknown> = Promise.resolve()
  return {
    request,
    waitUntil(promise: Promise<unknown>) {
      settled = promise
    },
    respondWith(value: Response | Promise<Response>) {
      response = Promise.resolve(value)
      settled = response
    },
    get response() {
      return response
    },
    get settled() {
      return settled
    },
  }
}

describe("service worker offline behavior", () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  test("install pre-caches the offline page", async () => {
    const { handlers, fakeCaches, cacheStore, fakeSelf } = loadServiceWorker()

    const event = makeExtendableEvent()
    handlers.install!(event)
    await event.settled

    expect(fakeCaches.open).toHaveBeenCalledWith("offline-v2")
    const cached = cacheStore.get("offline-v2")
    expect(cached?.has("/static/offline.html")).toBe(true)
    expect(fakeSelf.skipWaiting).toHaveBeenCalled()
  })

  test("activate evicts old caches and keeps the current one", async () => {
    const { handlers, cacheStore, fakeSelf } = loadServiceWorker()

    // Seed stale caches alongside the current one (as if a prior install ran).
    cacheStore.set("offline-v0", new Map())
    cacheStore.set("offline-v1", new Map())
    cacheStore.set("offline-v2", new Map())
    cacheStore.set("random-other-cache", new Map())

    const event = makeExtendableEvent()
    handlers.activate!(event)
    await event.settled

    expect([...cacheStore.keys()]).toEqual(["offline-v2"])
    expect(fakeSelf.clients.claim).toHaveBeenCalled()
  })

  test("navigation fetch falls back to the cached offline page when network fails", async () => {
    const { handlers, cacheStore } = loadServiceWorker()

    // Prime the cache the way install would.
    cacheStore.set(
      "offline-v2",
      new Map([["/static/offline.html", new Response("<offline-page/>", { status: 200 })]]),
    )

    const offlineError = new TypeError("Failed to fetch")
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(offlineError)))

    const event = makeFetchEvent({ url: "https://app.example/dashboard", mode: "navigate" })
    handlers.fetch!(event)

    const response = await event.response!
    expect(await response.text()).toBe("<offline-page/>")
  })

  test("navigation fetch returns the network response when online", async () => {
    const { handlers } = loadServiceWorker()

    const networkResponse = new Response("<html>hi</html>", { status: 200 })
    vi.stubGlobal("fetch", vi.fn(async () => networkResponse))

    const event = makeFetchEvent({ url: "https://app.example/dashboard", mode: "navigate" })
    handlers.fetch!(event)

    const response = await event.response!
    expect(response).toBe(networkResponse)
  })

  test("non-navigation requests pass through without interception", async () => {
    const { handlers } = loadServiceWorker()
    // If fetch is called from inside the handler, we'd see this spy fire —
    // we want the opposite: the SW must not touch sub-resource requests.
    const fetchSpy = vi.fn()
    vi.stubGlobal("fetch", fetchSpy)

    const event = makeFetchEvent({ url: "https://app.example/api/things", mode: "cors" })
    handlers.fetch!(event)

    expect(event.response).toBeNull()
    expect(fetchSpy).not.toHaveBeenCalled()
  })
})
