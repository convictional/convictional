import { QueryClientProvider } from "@tanstack/react-query"
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
  RouterProvider,
} from "@tanstack/react-router"
import { act, cleanup, fireEvent, render as rtlRender, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

vi.mock("../../../../../app/javascript/react/shared/apiFetch", () => ({
  apiFetch: vi.fn(),
  ApiError: class extends Error {
    status: number
    body: Record<string, unknown> | null
    constructor(status: number, body: Record<string, unknown> | null = null) {
      super(`Request failed with status ${status}`)
      this.status = status
      this.body = body
    }
  },
}))

import { apiFetch } from "../../../../../app/javascript/react/shared/apiFetch"
import { EmailMessageOriginal } from "../../../../../app/javascript/react/features/emailMessageOriginal/EmailMessageOriginal"
import type { EmailMessage } from "../../../../../app/javascript/react/shared/types"
import { createTestQueryClient } from "../../shared/testUtils"

const mockApiFetch = vi.mocked(apiFetch)

function makeMessage(overrides: Partial<EmailMessage> = {}): EmailMessage {
  return {
    id: "m1",
    message_type: "received",
    subject: "Original subject",
    raw_sender: "Alice <alice@example.com>",
    sender_name: "Alice",
    sender_email: "alice@example.com",
    to: ["me@example.com"],
    cc: [],
    bcc: [],
    preview: "preview",
    received_at: "2026-01-01T00:00:00Z",
    sent_at: null,
    created_at: "2026-01-01T00:00:00Z",
    external_thread_id: "ext-thread-1",
    message_id: "<rfc@example.com>",
    content_url: "/api/email_threads/t1/email_messages/m1/content",
    reply_url: "/reply",
    forward_url: "/forward",
    view_original_url: "/email_threads/t1/email_messages/m1",
    content_html: null,
    body_plain: "plain body",
    body_html: null,
    headers: [],
    raw_data: null,
    attachments: [],
    ...overrides,
  }
}

async function renderOriginal(initialEntry = "/email_threads/t1/email_messages/m1") {
  const rootRoute = createRootRoute()
  const shellTestRoute = createRoute({ getParentRoute: () => rootRoute, id: "shell", component: () => <Outlet /> })
  const threadShowTestRoute = createRoute({
    getParentRoute: () => shellTestRoute,
    path: "/email_threads/$emailThreadId",
    component: function ThreadStub() {
      const { emailThreadId } = threadShowTestRoute.useParams()
      return <div data-testid="thread-page" data-thread-id={emailThreadId} />
    },
  })
  const originalTestRoute = createRoute({
    getParentRoute: () => shellTestRoute,
    path: "/email_threads/$emailThreadId/email_messages/$emailMessageId",
    component: EmailMessageOriginal,
  })
  const router = createRouter({
    routeTree: rootRoute.addChildren([shellTestRoute.addChildren([threadShowTestRoute, originalTestRoute])]),
    history: createMemoryHistory({ initialEntries: [initialEntry] }),
  })
  const utils = rtlRender(
    <QueryClientProvider client={createTestQueryClient()}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  )
  await act(async () => {
    await router.load()
  })
  return utils
}

beforeEach(() => {
  mockApiFetch.mockReset()
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe("EmailMessageOriginal", () => {
  test("renders the message details from its route params", async () => {
    mockApiFetch.mockResolvedValue(makeMessage())

    await renderOriginal()

    expect(mockApiFetch).toHaveBeenCalledWith("/api/email_threads/t1/email_messages/m1")
    expect(await screen.findByText("Original subject")).toBeTruthy()
    expect(screen.getByText("plain body")).toBeTruthy()
  })

  test("'Back to thread' client-navigates to the thread route (no full load)", async () => {
    mockApiFetch.mockResolvedValue(makeMessage())

    await renderOriginal()

    const back = await screen.findByLabelText("Back to thread")
    await act(async () => {
      fireEvent.click(back)
    })

    const thread = await screen.findByTestId("thread-page")
    expect(thread.getAttribute("data-thread-id")).toBe("t1")
    // The original view is gone — this was a client transition, not a reload.
    expect(screen.queryByText("Original subject")).toBeNull()
  })

  test("shows an error state when the message fails to load", async () => {
    mockApiFetch.mockRejectedValue(new Error("boom"))

    await renderOriginal()

    expect(await screen.findByText("Could not load this message.")).toBeTruthy()
  })
})
