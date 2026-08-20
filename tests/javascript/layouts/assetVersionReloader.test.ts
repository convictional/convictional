import { expect, test, vi } from "vitest"
import { assetVersionReloader } from "../../../app/javascript/layouts/assetVersionReloader"
import type { ChannelsStore } from "../../../app/javascript/channels/store"
import { ChannelMessageType, type ChannelSubscription } from "../../../app/javascript/types/channels"

function mount(currentVersion: string) {
  const subscribeTo = vi.fn(() => ({ name: "version_refresh" }) as ChannelSubscription)
  const unsubscribe = vi.fn()
  const store = { client: { subscribeTo }, unsubscribe } as unknown as ChannelsStore

  const component = assetVersionReloader({ stream: "version_refresh", currentVersion })
  const context = Object.assign(component, { $store: { channels: store } })

  return { context, subscribeTo, unsubscribe }
}

test("subscribes by topic (unsigned), not by signed token", () => {
  const { context, subscribeTo } = mount("v1")

  context.init()

  expect(subscribeTo).toHaveBeenCalledWith("version_refresh", {}, expect.any(Function))
})

test("marks stale only when a version message reports a different version", () => {
  const { context, subscribeTo } = mount("v1")

  context.init()
  const onMessage = subscribeTo.mock.calls[0][2]

  onMessage({ type: ChannelMessageType.ASSET_VERSION_INFO, version: "v1" })
  expect(context.isStale).toBe(false)

  onMessage({ type: ChannelMessageType.ASSET_VERSION_CHANGED, version: "v2" })
  expect(context.isStale).toBe(true)
})
