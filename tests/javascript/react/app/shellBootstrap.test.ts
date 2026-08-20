import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

import { ApiError } from "~/react/shared/apiFetch"
import { redirectToLogin } from "~/react/shared/routerGuards"
import { loadShellBootstrap } from "~/react/app/shellBootstrap"
import { getCurrentUser } from "~/react/shared/stores/currentUser"
import { getChannelsClient, setChannelsClient } from "~/channels/client"
import { registerToastEventBridge } from "~/react/composites/toaster/eventBridge"
import { markAssetsStale, resetAssetVersionStale } from "~/react/shared/stores/assetVersionStore"

import { buildCurrentUser } from "../shared/currentUserFixtures"

vi.mock("~/react/shared/stores/currentUser", () => ({
  getCurrentUser: vi.fn(),
}))

vi.mock("~/react/shared/routerGuards", () => ({
  redirectToLogin: vi.fn(() => {
    throw new Error("redirect:login")
  }),
}))

const redirectMock = vi.hoisted(() => vi.fn((opts: Record<string, unknown>) => ({ __redirect: true, opts })))
vi.mock("@tanstack/react-router", () => ({
  redirect: redirectMock,
}))

const channelsClientCtor = vi.hoisted(() =>
  // Plain function (not an arrow) so `new ChannelsClient()` is constructable.
  vi.fn(function () {
    return { connect: () => Promise.resolve() }
  })
)
vi.mock("~/channels/client", () => ({
  ChannelsClient: channelsClientCtor,
  setChannelsClient: vi.fn(),
  getChannelsClient: vi.fn(() => null),
}))
vi.mock("~/channels/logging", () => ({ logConnectionFailureToSentry: vi.fn() }))
vi.mock("~/react/composites/toaster/eventBridge", () => ({ registerToastEventBridge: vi.fn() }))

const getCurrentUserMock = vi.mocked(getCurrentUser)
const getChannelsClientMock = vi.mocked(getChannelsClient)

describe("loadShellBootstrap", () => {
  beforeEach(() => {
    resetAssetVersionStale()
  })

  afterEach(() => {
    vi.clearAllMocks()
    getChannelsClientMock.mockReturnValue(null)
    resetAssetVersionStale()
  })

  test("returns the user, applies no guard, and wires the SPA singletons", async () => {
    getCurrentUserMock.mockResolvedValue(buildCurrentUser({ id: "u1" }))

    const user = await loadShellBootstrap("/documents")

    expect(user.id).toBe("u1")
    expect(redirectToLogin).not.toHaveBeenCalled()
    // Channels + toast bridge are wired before the shell subtree renders.
    expect(channelsClientCtor).toHaveBeenCalledOnce()
    expect(setChannelsClient).toHaveBeenCalledOnce()
    expect(registerToastEventBridge).toHaveBeenCalledOnce()
  })

  test("does not reconstruct the channels client when one already exists", async () => {
    getCurrentUserMock.mockResolvedValue(buildCurrentUser({ id: "u1" }))
    getChannelsClientMock.mockReturnValue({} as never)

    await loadShellBootstrap("/documents")

    expect(channelsClientCtor).not.toHaveBeenCalled()
    expect(setChannelsClient).not.toHaveBeenCalled()
  })

  test("redirects to login on a 401 bootstrap fetch", async () => {
    getCurrentUserMock.mockRejectedValue(new ApiError(401, null))

    await expect(loadShellBootstrap("/documents")).rejects.toThrow("redirect:login")
    expect(redirectToLogin).toHaveBeenCalledOnce()
    expect(channelsClientCtor).not.toHaveBeenCalled()
  })

  test("rethrows non-auth fetch errors without redirecting", async () => {
    getCurrentUserMock.mockRejectedValue(new ApiError(500, null))

    await expect(loadShellBootstrap("/documents")).rejects.toBeInstanceOf(ApiError)
    expect(redirectToLogin).not.toHaveBeenCalled()
  })

  test("throws a reloadDocument redirect to the destination href when assets are stale", async () => {
    getCurrentUserMock.mockResolvedValue(buildCurrentUser({ id: "u1" }))
    markAssetsStale()

    await expect(loadShellBootstrap("/chats")).rejects.toEqual({ __redirect: true, opts: { href: "/chats", reloadDocument: true } })
    expect(redirectMock).toHaveBeenCalledWith({ href: "/chats", reloadDocument: true })
  })

  test("does not redirect when assets are fresh", async () => {
    getCurrentUserMock.mockResolvedValue(buildCurrentUser({ id: "u1" }))

    await loadShellBootstrap("/chats")

    expect(redirectMock).not.toHaveBeenCalled()
  })
})
