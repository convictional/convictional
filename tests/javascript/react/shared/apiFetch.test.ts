import * as Sentry from "@sentry/browser"
import { expect, test, describe, vi, beforeEach, afterEach } from "vitest"
import { accessDeniedUrl, apiFetch, ApiError } from "../../../../app/javascript/react/shared/apiFetch"
import { showFlash } from "../../../../app/javascript/shared/flash"

vi.mock("@sentry/browser", () => ({ withScope: vi.fn() }))
vi.mock("../../../../app/javascript/shared/flash", () => ({
  showFlash: vi.fn(),
}))

function setCSRFMeta(token: string): void {
  let meta = document.querySelector<HTMLMetaElement>('meta[name="csrf-token"]')
  if (!meta) {
    meta = document.createElement("meta")
    meta.name = "csrf-token"
    document.head.appendChild(meta)
  }
  meta.content = token
}

function removeCSRFMeta(): void {
  document.querySelector('meta[name="csrf-token"]')?.remove()
}

function mockFetch(status: number, body: unknown = null, headers: Record<string, string> = {}): void {
  const responseHeaders = new Headers({ "content-type": "application/json", ...headers })
  vi.stubGlobal("fetch", vi.fn().mockImplementation(() => {
    const response = new Response(body ? JSON.stringify(body) : null, { status, headers: responseHeaders })
    return Promise.resolve(response)
  }))
}

describe("apiFetch", () => {
  beforeEach(() => {
    setCSRFMeta("test-csrf-token")
  })

  afterEach(() => {
    removeCSRFMeta()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
    vi.mocked(showFlash).mockClear()
  })

  test("includes CSRF token and Accept header", async () => {
    mockFetch(200, { ok: true })

    await apiFetch("/api/test")

    const [url, options] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0]
    expect(url).toBe("/api/test")
    expect(options.headers["X-CSRFToken"]).toBe("test-csrf-token")
    expect(options.headers["Accept"]).toBe("application/json")
    expect(options.credentials).toBe("same-origin")
  })

  test("sets Content-Type for string body", async () => {
    mockFetch(200, { created: true })

    await apiFetch("/api/items", {
      method: "POST",
      body: JSON.stringify({ name: "test" }),
    })

    const options = (fetch as ReturnType<typeof vi.fn>).mock.calls[0][1]
    expect(options.headers["Content-Type"]).toBe("application/json")
  })

  test("parses JSON response on success", async () => {
    mockFetch(200, { id: "123", name: "Item" })

    const result = await apiFetch<{ id: string; name: string }>("/api/items/123")

    expect(result).toEqual({ id: "123", name: "Item" })
  })

  test("throws ApiError carrying status and body on 500", async () => {
    mockFetch(500, { detail: "Internal server error" })

    try {
      await apiFetch("/api/broken")
      expect.unreachable("should have thrown")
    } catch (e) {
      expect(e).toBeInstanceOf(ApiError)
      const error = e as ApiError
      expect(error.status).toBe(500)
      expect(error.body).toEqual({ detail: "Internal server error" })
      // Generic message — no server detail leaks to the user-facing Error.
      expect(error.message).toBe("Request failed with status 500")
    }
  })

  test("preserves validation-error body without leaking it into the message", async () => {
    mockFetch(422, { detail: [{ loc: ["body", "url"], msg: "Field required", type: "missing" }] })

    try {
      await apiFetch("/api/items")
      expect.unreachable("should have thrown")
    } catch (e) {
      expect(e).toBeInstanceOf(ApiError)
      const error = e as ApiError
      expect(error.message).toBe("Request failed with status 422")
      expect(error.body?.detail).toBeInstanceOf(Array)
    }
  })

  test("throws ApiError on 403", async () => {
    mockFetch(403, { detail: "Forbidden" })

    try {
      await apiFetch("/api/secret")
      expect.unreachable("should have thrown")
    } catch (e) {
      expect(e).toBeInstanceOf(ApiError)
      expect((e as ApiError).status).toBe(403)
    }
  })

  function stubSentryScope() {
    const scope = {
      setFingerprint: vi.fn(),
      setTags: vi.fn(),
      setExtras: vi.fn(),
      captureException: vi.fn(),
    }
    // Reset first: withScope is a shared module mock, and other error-path
    // tests call it too, so its count/impl would otherwise leak across tests.
    vi.mocked(Sentry.withScope).mockReset()
    vi.mocked(Sentry.withScope).mockImplementation((cb: (s: any) => void) => cb(scope))
    return { scope }
  }

  test("reports non-ok responses to Sentry, grouped by status and endpoint", async () => {
    const { scope } = stubSentryScope()

    mockFetch(500, { detail: "Internal server error" })

    await expect(apiFetch("/api/broken")).rejects.toBeInstanceOf(ApiError)

    expect(Sentry.withScope).toHaveBeenCalledTimes(1)
    // Fingerprint + tags split the shared throw site into per-(status, endpoint) issues.
    expect(scope.setFingerprint).toHaveBeenCalledWith(["api-error", "500", "/api/broken"])
    expect(scope.setTags).toHaveBeenCalledWith({ "api.status": "500", "api.endpoint": "/api/broken" })
    expect(scope.setExtras).toHaveBeenCalledWith({
      url: "/api/broken",
      status: 500,
      body: { detail: "Internal server error" },
    })
    expect(scope.captureException).toHaveBeenCalledTimes(1)
    expect(scope.captureException.mock.calls[0][0]).toBeInstanceOf(ApiError)
  })

  test("normalizes resource ids and drops the query string in the fingerprint/endpoint", async () => {
    const { scope } = stubSentryScope()

    mockFetch(422, { detail: "['Message body is required']" })

    await expect(
      apiFetch("/api/email_threads/6d611d51-5763-40ad-b33c-103543099f04/draft/send?foo=bar")
    ).rejects.toBeInstanceOf(ApiError)

    const endpoint = "/api/email_threads/:id/draft/send"
    expect(scope.setFingerprint).toHaveBeenCalledWith(["api-error", "422", endpoint])
    expect(scope.setTags).toHaveBeenCalledWith({ "api.status": "422", "api.endpoint": endpoint })
  })

  test("still rejects with ApiError when the Sentry capture path is a no-op", async () => {
    // The default @sentry/browser mock leaves withScope as a no-op (as it is
    // when the SDK is uninitialized), so the capture path must not swallow or
    // alter the thrown error.
    mockFetch(500, { detail: "Boom" })

    await expect(apiFetch("/api/broken")).rejects.toBeInstanceOf(ApiError)
  })

  test("redirects to /login on 401, carrying the current location as redirect_to", async () => {
    const locationDescriptor = Object.getOwnPropertyDescriptor(window, "location")
    const mockLocation = { ...window.location, href: "https://app.test/goals/123" }
    Object.defineProperty(window, "location", {
      value: mockLocation,
      writable: true,
      configurable: true,
    })

    const noJsonHeaders = new Headers()
    vi.stubGlobal("fetch", vi.fn().mockImplementation(() =>
      Promise.resolve(new Response(null, { status: 401, headers: noJsonHeaders }))
    ))

    await expect(apiFetch("/api/protected")).rejects.toThrow(ApiError)
    expect(mockLocation.href).toBe("/login?redirect_to=%2Fgoals%2F123")

    if (locationDescriptor) {
      Object.defineProperty(window, "location", locationDescriptor)
    }
  })

  test("returns null for 204 No Content without parsing body", async () => {
    mockFetch(204)

    const result = await apiFetch("/api/items/123", { method: "DELETE" })

    expect(result).toBeNull()
  })

  test("shows session changed flash on CSRF failure", async () => {
    vi.stubGlobal("fetch", vi.fn().mockImplementation(() => {
      const responseHeaders = new Headers({
        "content-type": "application/json",
        "X-CSRF-Failure": "true",
      })
      return Promise.resolve(
        new Response(JSON.stringify({ detail: "CSRF failed" }), { status: 403, headers: responseHeaders })
      )
    }))

    await expect(apiFetch("/api/test")).rejects.toThrow(ApiError)
    expect(showFlash).toHaveBeenCalled()
  })
})

describe("accessDeniedUrl", () => {
  test("returns the request-access URL from a 403", () => {
    const err = new ApiError(403, { request_access_url: "/workspaces/ws-1/collaborators/access" })
    expect(accessDeniedUrl(err)).toBe("/workspaces/ws-1/collaborators/access")
  })

  test("returns undefined for a 403 without a request-access URL", () => {
    expect(accessDeniedUrl(new ApiError(403, {}))).toBeUndefined()
  })

  test("returns undefined for non-403 errors and non-errors", () => {
    expect(accessDeniedUrl(new ApiError(404, { request_access_url: "/x" }))).toBeUndefined()
    expect(accessDeniedUrl(new Error("boom"))).toBeUndefined()
    expect(accessDeniedUrl(null)).toBeUndefined()
  })
})
