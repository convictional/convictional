import { act, renderHook } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { ChannelMessageType, type WebSocketMessage } from "~/types/channels"

// Capture the callback registered with subscribeTo so tests can push messages through it.
let channelCallback: ((message: WebSocketMessage) => void) | null = null
const subscribeTo = vi.fn((_stream: string, _params: Record<string, string>, callback: (message: WebSocketMessage) => void) => {
  channelCallback = callback
  return { name: "version_refresh" }
})
const unsubscribe = vi.fn()

// Hoisted client state so the "client unavailable" test can null it out without
// re-mocking the module (vi.mock is hoisted and applies to every test).
const clientState = vi.hoisted(() => ({ available: true }))

vi.mock("~/react/shared/hooks/useChannelsClient", () => ({
  useChannelsClient: () => (clientState.available ? { subscribeTo, unsubscribe } : null),
}))

import { useAssetVersionReloader } from "~/react/shared/hooks/useAssetVersionReloader"
import { isAssetVersionStale, resetAssetVersionStale } from "~/react/shared/stores/assetVersionStore"

function setStampedVersion(version: string): void {
  let meta = document.querySelector<HTMLMetaElement>('meta[name="asset-version"]')
  if (!meta) {
    meta = document.createElement("meta")
    meta.setAttribute("name", "asset-version")
    document.head.appendChild(meta)
  }
  meta.setAttribute("content", version)
}

function versionMessage(type: ChannelMessageType, version: string): WebSocketMessage {
  return { type, version } as unknown as WebSocketMessage
}

describe("useAssetVersionReloader", () => {
  beforeEach(() => {
    channelCallback = null
    subscribeTo.mockClear()
    unsubscribe.mockClear()
    clientState.available = true
    setStampedVersion("v1")
    resetAssetVersionStale()
  })

  afterEach(() => {
    vi.restoreAllMocks()
    document.querySelector('meta[name="asset-version"]')?.remove()
  })

  it("subscribes to the version_refresh topic on mount", () => {
    renderHook(() => useAssetVersionReloader())

    expect(subscribeTo).toHaveBeenCalledWith("version_refresh", {}, expect.any(Function))
  })

  it("unsubscribes on unmount", () => {
    const { unmount } = renderHook(() => useAssetVersionReloader())
    unmount()

    expect(unsubscribe).toHaveBeenCalledTimes(1)
  })

  it("marks stale when ASSET_VERSION_INFO reports a different version", () => {
    renderHook(() => useAssetVersionReloader())

    act(() => {
      channelCallback?.(versionMessage(ChannelMessageType.ASSET_VERSION_INFO, "v2"))
    })

    expect(isAssetVersionStale()).toBe(true)
  })

  it("marks stale when ASSET_VERSION_CHANGED reports a different version", () => {
    renderHook(() => useAssetVersionReloader())

    act(() => {
      channelCallback?.(versionMessage(ChannelMessageType.ASSET_VERSION_CHANGED, "v2"))
    })

    expect(isAssetVersionStale()).toBe(true)
  })

  it("does not mark stale when the version matches the stamped one", () => {
    renderHook(() => useAssetVersionReloader())

    act(() => {
      channelCallback?.(versionMessage(ChannelMessageType.ASSET_VERSION_CHANGED, "v1"))
    })

    expect(isAssetVersionStale()).toBe(false)
  })

  it("ignores non-asset-version messages", () => {
    renderHook(() => useAssetVersionReloader())

    act(() => {
      channelCallback?.(versionMessage(ChannelMessageType.SUBSCRIPTION_CONFIRMED, "v2"))
    })

    expect(isAssetVersionStale()).toBe(false)
  })

  it("does not mark stale when the server version is empty", () => {
    renderHook(() => useAssetVersionReloader())

    act(() => {
      channelCallback?.(versionMessage(ChannelMessageType.ASSET_VERSION_CHANGED, ""))
    })

    expect(isAssetVersionStale()).toBe(false)
  })

  it("no-ops when the channels client is unavailable", () => {
    clientState.available = false
    renderHook(() => useAssetVersionReloader())

    expect(subscribeTo).not.toHaveBeenCalled()
  })
})
