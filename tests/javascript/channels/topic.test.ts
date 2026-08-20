import { expect, test, describe } from "vitest"
import { Topic, stringifyParams, topicKeyFromMessage } from "../../../app/javascript/channels/topic"
import { ChannelMessageType } from "../../../app/javascript/types/channels"

describe("Topic.matches", () => {
  test("matches topics with the same logical identity", () => {
    const topic1 = new Topic("notifications")
    const topic2 = new Topic("notifications")

    expect(topic1.matches(topic2)).toBe(true)
    expect(topic2.matches(topic1)).toBe(true)
  })

  test("does not match topics with different streams", () => {
    const topic1 = new Topic("notifications")
    const topic2 = new Topic("messages")

    expect(topic1.matches(topic2)).toBe(false)
    expect(topic2.matches(topic1)).toBe(false)
  })

  test("does not match topics with same stream but different params", () => {
    const topic1 = new Topic("thread", { thread_id: "123" })
    const topic2 = new Topic("thread", { thread_id: "456" })

    expect(topic1.matches(topic2)).toBe(false)
  })
})

describe("Topic constructor and canonical name", () => {
  // These MUST byte-match infra/messaging.py:Topic.name — the values below mirror
  // tests/unit/infra/test_messaging.py:test_topic_name exactly. This equivalence is the
  // load-bearing guarantee that subscribes dedup and route together.
  test("stream-only name", () => {
    expect(new Topic("workspace").name).toBe("workspace")
  })

  test("name with params", () => {
    expect(new Topic("workspace", { organization_id: "123", user_id: "456" }).name).toBe(
      "workspace:organization_id:123:user_id:456"
    )
  })

  test("params are sorted by key regardless of insertion order", () => {
    expect(new Topic("workspace", { user_id: "456", organization_id: "123" }).name).toBe(
      "workspace:organization_id:123:user_id:456"
    )
  })

  test("coerces non-string param values to strings (mirrors Python str())", () => {
    expect(new Topic("goal_timeline", { goal_id: 5 }).name).toBe("goal_timeline:goal_id:5")
  })
})

describe("stringifyParams", () => {
  test("coerces numbers and booleans to strings", () => {
    expect(stringifyParams({ a: 5, b: true, c: "x" })).toEqual({ a: "5", b: "true", c: "x" })
  })

  test("drops null and undefined", () => {
    expect(stringifyParams({ a: "1", b: null, c: undefined })).toEqual({ a: "1" })
  })
})

describe("topicKeyFromMessage", () => {
  test("resolves the unsigned stream/params form", () => {
    expect(
      topicKeyFromMessage({ topic_stream: "goal_timeline", topic_params: { goal_id: "5" } })
    ).toBe("goal_timeline:goal_id:5")
  })

  test("resolves a stream with no params", () => {
    expect(topicKeyFromMessage({ topic_stream: "workspace" })).toBe("workspace")
  })

  test("returns null for a message with no topic (ping)", () => {
    expect(topicKeyFromMessage({ type: ChannelMessageType.PING })).toBeNull()
  })
})
