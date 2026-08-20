import type { ChannelParams, WebSocketMessage } from "../types/channels"

/**
 * Coerce params to a string map, mirroring Python's `Topic.__init__` (`{k: str(v)}`).
 * Null/undefined values are dropped so they never enter the canonical name.
 */
export function stringifyParams(params: ChannelParams | Record<string, string>): Record<string, string> {
  const result: Record<string, string> = {}
  for (const [key, value] of Object.entries(params)) {
    if (value === null || value === undefined) continue
    result[key] = String(value)
  }
  return result
}

export class Topic {
  readonly stream: string
  readonly params: Record<string, string>

  constructor(stream: string, params: ChannelParams | Record<string, string> = {}) {
    this.stream = stream
    this.params = stringifyParams(params)
  }

  /**
   * Canonical unsigned name: `stream:k:v:k:v` with params sorted by key.
   * MUST byte-match infra/messaging.py:Topic.name — it is the dedup/correlation
   * key shared between the signed and unsigned subscribe forms.
   */
  get name(): string {
    const keys = Object.keys(this.params).sort()
    if (keys.length === 0) return this.stream
    const parts = keys.map(key => `${key}:${this.params[key]}`)
    return `${this.stream}:${parts.join(":")}`
  }

  matches(other: Topic): boolean {
    return this.name === other.name
  }
}

interface TopicCarrier {
  topic_stream?: string
  topic_params?: Record<string, string>
}

/**
 * Resolve the canonical topic name from any message carrying a topic via its
 * `topic_stream`/`topic_params`. Returns null for messages without a topic (e.g. ping/pong).
 */
export function topicKeyFromMessage(message: WebSocketMessage | TopicCarrier): string | null {
  const topicStream = "topic_stream" in message ? message.topic_stream : undefined
  const topicParams = "topic_params" in message ? message.topic_params : undefined

  if (topicStream != null) {
    return new Topic(topicStream, topicParams ?? {}).name
  }
  return null
}
