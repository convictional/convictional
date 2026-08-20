import { useEffect, useRef } from "react"

import { markAssetsStale } from "~/react/shared/stores/assetVersionStore"
import { ChannelMessageType, type WebSocketMessage } from "~/types/channels"

import { useChannelsClient } from "./useChannelsClient"

// Reads the asset version stamped into <meta name="asset-version"> at serve
// time. The SPA shell is the only server→React DOM contract surface for client
// routes (see docs/react-migration.md → Client-Side Router ADR), so the version
// lives here rather than a bootstrap payload.
function stampedAssetVersion(): string {
  return document.querySelector<HTMLMetaElement>('meta[name="asset-version"]')?.content ?? ""
}

// Subscribes to the unsigned `version_refresh` channel and marks the session
// stale when the server reports a version differing from the one baked into
// the shell. The reload itself lives in shellRoute's beforeLoad guard
// (loadShellBootstrap), which throws redirect({ reloadDocument: true }) on the
// next navigation — cancelling the SPA route change so the stale destination's
// loaders/effects never run. Deferring to navigation avoids interrupting an
// active editing session; a user who stays on one route stays stale until
// they navigate (the explicit tradeoff for not losing unflushed autosaves).
export function useAssetVersionReloader(): void {
  const channelsClient = useChannelsClient()
  const currentVersionRef = useRef(stampedAssetVersion())

  useEffect(() => {
    if (!channelsClient) return

    const subscription = channelsClient.subscribeTo("version_refresh", {}, (message: WebSocketMessage) => {
      if (
        message.type !== ChannelMessageType.ASSET_VERSION_INFO &&
        message.type !== ChannelMessageType.ASSET_VERSION_CHANGED
      ) {
        return
      }
      const serverVersion = message.version
      if (serverVersion && serverVersion !== currentVersionRef.current) {
        markAssetsStale()
      }
    })

    return () => {
      channelsClient.unsubscribe(subscription)
    }
  }, [channelsClient])
}
