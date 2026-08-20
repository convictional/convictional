import type { AlpineComponent } from "alpinejs"
import type { ChannelsStore } from "../channels/store"
import {
  ChannelMessageType,
  type ChannelSubscription,
  type AssetVersionInfoMessage,
  type AssetVersionChangedMessage,
  type WebSocketMessage,
} from "../types/channels"

interface AlpineContext {
  $store: {
    channels: ChannelsStore
  }
}

interface AssetVersionReloaderData {
  subscription?: ChannelSubscription
  navigationEventListener?: (evt: Event) => void
  isStale: boolean
  init: () => void
  destroy: () => void
  handleSocketMessage: (message: WebSocketMessage) => void
  setNavigationEventListener: () => void
}

interface AssetVersionReloaderOptions {
  stream: string
  currentVersion: string
}

export const assetVersionReloader = (
  options: AssetVersionReloaderOptions
): AlpineComponent<AssetVersionReloaderData> => ({
  subscription: undefined,
  navigationEventListener: undefined,
  isStale: false,

  init(this: AssetVersionReloaderData & AlpineContext) {
    const channelsStore = this.$store.channels
    if (!channelsStore) {
      console.error("[AssetVersionReloader] Channels store not available")
      return
    }

    this.subscription = channelsStore.client.subscribeTo(options.stream, {}, (message: WebSocketMessage) => {
      this.handleSocketMessage(message)
    })
  },

  destroy(this: AssetVersionReloaderData & AlpineContext) {
    const channelsStore = this.$store.channels
    if (this.subscription && channelsStore) {
      channelsStore.client.unsubscribe(this.subscription)
      this.subscription = undefined
    }

    if (this.navigationEventListener) {
      document.body.removeEventListener("click", this.navigationEventListener, true)
      this.navigationEventListener = undefined
    }
  },

  handleSocketMessage(message: WebSocketMessage) {
    if (message.type === ChannelMessageType.ASSET_VERSION_INFO) {
      const versionInfo = message as AssetVersionInfoMessage

      if (versionInfo.version !== options.currentVersion) {
        this.isStale = true
        this.setNavigationEventListener()
      }
    } else if (message.type === ChannelMessageType.ASSET_VERSION_CHANGED) {
      const versionChanged = message as AssetVersionChangedMessage

      if (versionChanged.version !== options.currentVersion) {
        this.isStale = true
        this.setNavigationEventListener()
      }
    }
  },

  setNavigationEventListener() {
    if (this.navigationEventListener) {
      return
    }

    // Listen for click events on links and forms BEFORE HTMX processes them
    // This allows us to intercept user-initiated navigation when assets are stale
    this.navigationEventListener = (evt: Event) => {
      const target = evt.target as HTMLElement

      // Find the closest link or form element
      const link = target.closest("a[href]") as HTMLAnchorElement | null

      if (link) {
        // Check if this is a navigation link (not just an anchor fragment or javascript:)
        const href = link.getAttribute("href")
        if (href && !href.startsWith("#") && !href.startsWith("javascript:")) {
          evt.preventDefault()
          evt.stopImmediatePropagation() // Prevent HTMX from processing this
          window.location.href = href
          return
        }
      }
    }

    // Listen for clicks with high priority (capture phase) to intercept before HTMX
    document.body.addEventListener("click", this.navigationEventListener, true)
  },
})
