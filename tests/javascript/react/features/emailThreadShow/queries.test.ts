import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

const apiFetchMock = vi.fn()
vi.mock("~/react/shared/apiFetch", () => ({
  apiFetch: (url: string, options?: RequestInit) => apiFetchMock(url, options),
}))

import { emailMessageContentQueryKey, emailThreadQueryOptions } from "~/react/features/emailThreadShow/queries"
import type { EmailMessageSummary, EmailThreadShowResponse, TimelineItem } from "~/react/shared/types"

import { createTestQueryClient } from "../../shared/testUtils"

const message = (id: string): EmailMessageSummary => ({
  id,
  message_type: "received",
  subject: null,
  raw_sender: null,
  sender_name: id,
  sender_email: `${id}@example.com`,
  to: [],
  cc: [],
  bcc: [],
  preview: null,
  received_at: `2026-01-0${id.slice(-1)}T00:00:00Z`,
  sent_at: null,
  created_at: `2026-01-0${id.slice(-1)}T00:00:00Z`,
  external_thread_id: null,
  message_id: null,
  content_url: `/content/${id}`,
  reply_url: "/r",
  forward_url: "/f",
  view_original_url: "/o",
})

const messageItem = (id: string): TimelineItem => ({
  type: "message",
  item_id: id,
  created_at: `2026-01-0${id.slice(-1)}T00:00:00Z`,
  message: message(id),
  event: null,
})

function envelope(timeline: TimelineItem[]): EmailThreadShowResponse {
  return {
    thread: {
      id: "t1",
      title: "Subject",
      workspace_id: "ws-1",
      creator: { id: "creator", display_name: "Creator" },
      can_reply: true,
      is_shared: false,
      own_thread_id: null,
    },
    // Fully read: every message but the newest starts collapsed; the newest starts expanded.
    mailbox_entry: {
      id: "entry-1",
      is_unread: false,
      is_archived: false,
      is_snoozed: false,
      snoozed_until: null,
      is_ai_excluded: false,
      is_shared: false,
      read_at: "2026-02-01T00:00:00Z",
    },
    timeline,
    comments: [],
    draft: null,
    last_event_id: null,
  }
}

const isEnvelopeUrl = (url: unknown) => url === "/api/email_threads/t1"
const isBatchUrl = (url: unknown) => String(url).includes("email_message_contents")
const batchCalls = () => apiFetchMock.mock.calls.filter(([url]) => isBatchUrl(url))

beforeEach(() => apiFetchMock.mockReset())
afterEach(() => vi.clearAllMocks())

describe("emailThreadQueryOptions", () => {
  it("seeds only the expanded messages' bodies into their per-message caches", async () => {
    const env = envelope([messageItem("m1"), messageItem("m2")])
    apiFetchMock.mockImplementation(async (url: string) => {
      if (isEnvelopeUrl(url)) return env
      if (isBatchUrl(url)) return { contents: [{ id: "m2", content_html: "<p>m2</p>", body_plain: null, attachments: [] }] }
      return { contents: [] }
    })

    const client = createTestQueryClient()
    const data = await client.fetchQuery(emailThreadQueryOptions(client, "t1"))

    expect(data.thread.id).toBe("t1")
    // m2 is the newest, so it renders expanded and its body is seeded from the batch.
    expect(client.getQueryData(emailMessageContentQueryKey("m2"))).toEqual({
      id: "m2",
      content_html: "<p>m2</p>",
      body_plain: null,
      attachments: [],
    })
    // m1 starts collapsed on a fully-read thread, so it isn't in the batch and isn't seeded.
    expect(client.getQueryData(emailMessageContentQueryKey("m1"))).toBeUndefined()
    // The batch requested exactly m2's body.
    expect(batchCalls()).toHaveLength(1)
    expect(String(batchCalls()[0][0])).toContain("ids=m2")
    expect(String(batchCalls()[0][0])).not.toContain("ids=m1")
  })

  it("issues no batch request when nothing renders expanded", async () => {
    apiFetchMock.mockImplementation(async (url: string) => {
      if (isEnvelopeUrl(url)) return envelope([])
      return { contents: [] }
    })

    const client = createTestQueryClient()
    await client.fetchQuery(emailThreadQueryOptions(client, "t1"))

    expect(batchCalls()).toHaveLength(0)
  })

  it("swallows a failed batch so the envelope still loads (messages self-fetch)", async () => {
    const env = envelope([messageItem("m2")])
    apiFetchMock.mockImplementation(async (url: string) => {
      if (isEnvelopeUrl(url)) return env
      if (isBatchUrl(url)) throw new Error("batch failed")
      return { contents: [] }
    })

    const client = createTestQueryClient()
    const data = await client.fetchQuery(emailThreadQueryOptions(client, "t1"))

    expect(data.thread.id).toBe("t1")
    // The batch threw, so nothing is seeded; EmailMessage will self-fetch on a cache miss.
    expect(client.getQueryData(emailMessageContentQueryKey("m2"))).toBeUndefined()
  })
})
