import { afterEach, describe, expect, test, vi } from "vitest"

import { chatMetadataQueryKey } from "~/react/composites/chat/chatMetadata"
import { queryClient } from "~/react/shared/queryClient"
import type { ChatCollaborator, ChatMetadata } from "~/react/shared/types"

vi.mock("../../../../../app/javascript/react/shared/apiFetch", () => ({
  apiFetch: vi.fn(),
  ApiError: class extends Error {
    status: number
    body: Record<string, unknown> | null
    constructor(status: number, body: Record<string, unknown> | null = null) {
      super(typeof body?.detail === "string" ? body.detail : `err ${status}`)
      this.status = status
      this.body = body
    }
  },
}))

type ChannelCallback = (action: string, data: Record<string, unknown>) => void
let channelCallback: ChannelCallback | null = null
let channelStream: string | null = null
let channelParams: Record<string, unknown> | null = null

vi.mock("../../../../../app/javascript/react/shared/hooks/useChannel", () => ({
  useChannel: (
    target: { stream: string; params: Record<string, unknown>; extraParams?: Record<string, unknown> } | null,
    _resource: string,
    cb: ChannelCallback
  ) => {
    channelStream = target?.stream ?? null
    channelParams = target?.params ?? null
    channelCallback = cb
  },
}))

import { apiFetch, ApiError } from "../../../../../app/javascript/react/shared/apiFetch"
import { useChatCollaborators } from "../../../../../app/javascript/react/features/chatShow/useChatCollaborators"
import { act, renderHook, waitFor } from "../../shared/testUtils"

const mockApi = vi.mocked(apiFetch)

const seedCollaborators: ChatCollaborator[] = [
  { id: "c1", user: { id: "u1", display_name: "Alice", picture: null } },
  { id: "c2", user: { id: "u2", display_name: "Me", picture: null } },
  { id: "c3", user: { id: "u3", display_name: "Carol", picture: null } },
]

// Collaborators now live on the shared chat-metadata cache; seed it so the hook's
// useQuery reads it without firing GET /api/chats/:id (which would consume the
// POST/DELETE mocks below). channelQueryDefaults (staleTime Infinity,
// refetchOnMount false) means a warm cache is read straight through.
function seedMetadata(chatId: string, collaborators: ChatCollaborator[]) {
  const metadata: ChatMetadata = {
    chat_id: chatId,
    workspace_id: "ws-1",
    chat_title: "Chat",
    type: "multi",
    is_group_chat: false,
    group_id: null,
    collaborators,
    supports_mentions: true,
    last_read_at: null,
    unread_message_count: 0,
    mailbox: null,
  }
  queryClient.setQueryData(chatMetadataQueryKey(chatId), metadata)
}

describe("useChatCollaborators", () => {
  afterEach(() => {
    queryClient.clear()
  })

  test("addCollaborator returns server result and propagates errors", async () => {
    seedMetadata("chat-1", seedCollaborators)
    mockApi.mockResolvedValueOnce({ chat_id: "chat-1", added: true })
    const { result } = renderHook(() => useChatCollaborators("chat-1", "ws-1", "u2"))
    const ok = await act(async () => result.current.addCollaborator("u9", true))
    expect(ok).toEqual({ chatId: "chat-1", added: true })

    mockApi.mockRejectedValueOnce(new ApiError(422, { detail: "nope" }))
    const bad = await act(async () => result.current.addCollaborator("u9", false))
    expect(bad.error).toBe("nope")
  })

  test("removeCollaborator issues a DELETE and surfaces errors; archive/remove side effects arrive via the channel", async () => {
    seedMetadata("chat-1", seedCollaborators)
    mockApi.mockResolvedValueOnce(null)
    const { result } = renderHook(() => useChatCollaborators("chat-1", "ws-1", "u2"))

    const ok = await act(async () => result.current.removeCollaborator("u3"))
    expect(ok).toEqual({})
    expect(mockApi).toHaveBeenLastCalledWith("/api/chats/chat-1/collaborators/u3", { method: "DELETE" })

    mockApi.mockRejectedValueOnce(new ApiError(422, { detail: "cannot remove" }))
    const bad = await act(async () => result.current.removeCollaborator("u3"))
    expect(bad.error).toBe("cannot remove")
  })

  test("CHAT_COLLABORATOR events update state", async () => {
    seedMetadata("chat-1", seedCollaborators)
    const { result } = renderHook(() => useChatCollaborators("chat-1", "ws-1", "u2"))
    await waitFor(() => expect(channelCallback).not.toBeNull())
    expect(channelStream).toBe("chat")
    expect(channelParams).toEqual({ chat_id: "chat-1", workspace_id: "ws-1" })

    // Channel events patch the metadata cache; setQueryData notifies the useQuery
    // observer asynchronously, so assert through waitFor.
    act(() => channelCallback!("added", { user: { id: "u9", display_name: "Dana", picture: null } }))
    await waitFor(() => expect(result.current.collaborators.map(c => c.user.id)).toContain("u9"))

    act(() => channelCallback!("removed", { user_id: "u1" }))
    await waitFor(() => expect(result.current.collaborators.map(c => c.user.id)).not.toContain("u1"))

    act(() => channelCallback!("removed", { user_id: "u2" }))
    await waitFor(() => expect(result.current.selfRemoved).toBe(true))

    act(() => channelCallback!("archived", { conflicting_dm_id: "dm-5" }))
    await waitFor(() => expect(result.current.archived).toEqual({ conflictingDmId: "dm-5" }))
  })
})
