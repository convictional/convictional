import { useEffect, useRef } from "react"

import {
  type ChannelEventAction,
  ChannelEventResource,
  ChannelMessageType,
  type ChannelParams,
  type ChannelStream,
  type EventMessage,
  type WebSocketMessage,
} from "~/types/channels"
import { useChannelsClient } from "./useChannelsClient"

/**
 * A channel subscription target: the topic to subscribe to, or `null` to subscribe to
 * nothing this render. Call sites pass `null` until their identity params are ready (the
 * gating pattern — the hook itself can't be called conditionally), then the real target
 * once they resolve. Bundling stream + params means readiness is expressed once, at the
 * `null` boundary, instead of also leaking into the params as `?? ""` placeholders.
 *
 * `params` form the topic identity (the canonical `Topic.name`). `extraParams` are
 * non-identity subscribe args (the server's SubscribeMessage.params, e.g. mailbox_sync's
 * `view_id`) — changing them re-subscribes so the server sees the new values.
 */
export interface ChannelSubscriptionTarget {
  stream: ChannelStream
  params: ChannelParams
  extraParams?: ChannelParams
}

/**
 * Subscribe to EVENT messages on a channel topic, filtered by resource type. This is the
 * React-native subscription path — no signed token is needed; the server authorizes the
 * params at subscribe time.
 *
 * No-ops gracefully when `target` is null or the client isn't initialized.
 */
export function useChannel(
  target: ChannelSubscriptionTarget | null,
  resource: ChannelEventResource,
  onMessage: (action: ChannelEventAction, data: Record<string, unknown>) => void
): void {
  const channelsClient = useChannelsClient()
  const callbackRef = useRef(onMessage)
  const targetRef = useRef(target)
  // No dependency array (the "always-current ref" pattern): this runs on every render so the
  // subscription effect below always reads the latest callback/target via refs without having
  // to re-subscribe each render. It is intentional, not a missing-deps bug.
  useEffect(() => {
    callbackRef.current = onMessage
    targetRef.current = target
  })

  const stream = target?.stream ?? null
  const paramsKey = target ? JSON.stringify(target.params) : null
  const extraParamsKey = target?.extraParams ? JSON.stringify(target.extraParams) : null

  useEffect(() => {
    if (!channelsClient || !stream) return
    const current = targetRef.current
    if (!current) return

    const subscription = channelsClient.subscribeTo(
      current.stream,
      current.params,
      (message: WebSocketMessage) => {
        if (message.type === ChannelMessageType.EVENT) {
          const eventMessage = message as EventMessage
          if (eventMessage.resource === resource) {
            callbackRef.current(eventMessage.action, eventMessage.data)
          }
        }
      },
      current.extraParams ?? {}
    )

    return () => {
      channelsClient.unsubscribe(subscription)
    }
    // paramsKey/extraParamsKey are the change signals; targetRef holds the stable values passed to subscribeTo
  }, [channelsClient, stream, resource, paramsKey, extraParamsKey])
}
