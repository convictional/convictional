import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

import {
  ChannelEventAction as Action,
  ChannelEventResource,
  ChannelMessageType,
  type WebSocketMessage,
} from "~/types/channels"

vi.mock("~/react/shared/apiFetch", () => ({ apiFetch: vi.fn() }))

// organization_id rides the current-user bootstrap; the store reads it from
// getCurrentUser() before subscribing to the org-scoped topic.
vi.mock("~/react/shared/stores/currentUser", () => ({
  getCurrentUser: vi.fn().mockResolvedValue({ organization_id: "org-1" }),
}))

// Live updates are wired through the real channels client (no per-component
// channel hook). Hand it a fake client we can drive.
const hoisted = vi.hoisted(() => ({ client: null as FakeChannelsClient | null }))
vi.mock("~/channels/client", () => ({ getChannelsClient: () => hoisted.client }))

type ReconnectHandler = () => void

class FakeChannelsClient {
  subscribeCalls = 0
  subscribedStream: string | null = null
  subscribedParams: Record<string, unknown> | null = null
  private channelCallback: ((message: WebSocketMessage) => void) | null = null
  private reconnectHandlers = new Set<ReconnectHandler>()

  subscribeTo(stream: string, params: Record<string, unknown>, callback: (message: WebSocketMessage) => void) {
    this.subscribeCalls += 1
    this.subscribedStream = stream
    this.subscribedParams = params
    this.channelCallback = callback
    return { stream, params, callback }
  }

  unsubscribe() {
    this.channelCallback = null
    this.subscribedStream = null
  }

  on(event: string, handler: ReconnectHandler) {
    if (event === "reconnected") this.reconnectHandlers.add(handler)
  }

  off(event: string, handler: ReconnectHandler) {
    if (event === "reconnected") this.reconnectHandlers.delete(handler)
  }

  emitEvent(action: Action) {
    this.channelCallback?.({
      type: ChannelMessageType.EVENT,
      resource: ChannelEventResource.ORGANIZATION_MEMBERS,
      action,
      data: {},
    } as WebSocketMessage)
  }

  emitReconnect() {
    this.reconnectHandlers.forEach(handler => handler())
  }
}

import { apiFetch } from "~/react/shared/apiFetch"
import { useOrganizationMembers } from "~/react/shared/hooks/useOrganizationMembers"
import { queryClient } from "~/react/shared/queryClient"
import { stopOrganizationMembersLiveUpdates } from "~/react/shared/stores/organizationMembers"

import { act, renderHook, waitFor } from "../testUtils"

const mockedFetch = vi.mocked(apiFetch)

function response(userIds: string[]) {
  return {
    users: userIds.map(id => ({ id, display_name: id, picture: null })),
    groups: [],
  }
}

beforeEach(() => {
  stopOrganizationMembersLiveUpdates()
  queryClient.clear()
  mockedFetch.mockReset()
  hoisted.client = new FakeChannelsClient()
})
afterEach(() => {
  stopOrganizationMembersLiveUpdates()
  queryClient.clear()
  vi.clearAllMocks()
})

describe("useOrganizationMembers", () => {
  test("loads members and subscribes to the org members channel", async () => {
    mockedFetch.mockResolvedValueOnce(response(["u1"]))
    const { result } = renderHook(() => useOrganizationMembers())

    await waitFor(() => expect(result.current.users.map(u => u.id)).toEqual(["u1"]))
    // The subscribe awaits getCurrentUser(), so it lands a microtask after load.
    await waitFor(() => expect(hoisted.client!.subscribedStream).toBe("organization_members"))
    expect(hoisted.client!.subscribedParams).toEqual({ organization_id: "org-1" })
    expect(mockedFetch).toHaveBeenCalledWith("/api/organization/members")
  })

  test("wires a single channel subscription no matter how many components mount", async () => {
    mockedFetch.mockResolvedValue(response(["u1"]))
    const first = renderHook(() => useOrganizationMembers())
    const second = renderHook(() => useOrganizationMembers())

    await waitFor(() => expect(first.result.current.users.map(u => u.id)).toEqual(["u1"]))
    await waitFor(() => expect(second.result.current.users.map(u => u.id)).toEqual(["u1"]))

    await waitFor(() => expect(hoisted.client!.subscribeCalls).toBe(1))
  })

  test("refetches on an UPDATED membership event so the list stays current without reload", async () => {
    // Users added/removed and group create/rename/delete all arrive as one UPDATED
    // event (the server collapses them); the client just refetches the full payload.
    mockedFetch
      .mockResolvedValueOnce(response(["u1", "u2"]))
      .mockResolvedValueOnce({ ...response(["u1", "u3"]), groups: [{ id: "g1", name: "Renamed" }] })
    const { result } = renderHook(() => useOrganizationMembers())
    await waitFor(() => expect(result.current.users.map(u => u.id)).toEqual(["u1", "u2"]))

    await act(async () => {
      hoisted.client!.emitEvent(Action.UPDATED)
    })

    await waitFor(() => expect(result.current.users.map(u => u.id)).toEqual(["u1", "u3"]))
    expect(result.current.groups).toEqual([{ id: "g1", name: "Renamed" }])
  })

  test("a burst of UPDATED events converges on the latest server state", async () => {
    // refreshOrganizationMembers coalesces a burst: at most one refetch in flight,
    // plus a single trailing refetch for changes that landed mid-flight. A burst
    // therefore settles on the latest payload rather than a stale mid-burst snapshot.
    mockedFetch.mockResolvedValueOnce(response(["u1"])).mockResolvedValue(response(["u1", "u2"]))
    const { result } = renderHook(() => useOrganizationMembers())
    await waitFor(() => expect(result.current.users.map(u => u.id)).toEqual(["u1"]))

    await act(async () => {
      hoisted.client!.emitEvent(Action.UPDATED)
      hoisted.client!.emitEvent(Action.UPDATED)
      hoisted.client!.emitEvent(Action.UPDATED)
    })

    await waitFor(() => expect(result.current.users.map(u => u.id)).toEqual(["u1", "u2"]))
  })

  test("coalesces a burst of refreshes so the rate limiter isn't hammered", async () => {
    // A bulk membership change broadcasts many UPDATED events, and a flaky/multi-tab socket
    // can emit repeated reconnects. Each refresh must NOT fire its own uncancellable request,
    // or the upstream rate limiter trips (429). The invariant: at most one refetch in flight,
    // plus one trailing refetch for changes that arrived mid-flight — so a burst of N events
    // causes 2 refetches, not N.
    const resolvers: Array<(value: ReturnType<typeof response>) => void> = []
    mockedFetch.mockResolvedValueOnce(response(["u1"]))
    mockedFetch.mockImplementation(
      () =>
        new Promise<ReturnType<typeof response>>(resolve => {
          resolvers.push(resolve)
        }) as never
    )

    const { result } = renderHook(() => useOrganizationMembers())
    await waitFor(() => expect(result.current.users.map(u => u.id)).toEqual(["u1"]))
    expect(mockedFetch).toHaveBeenCalledTimes(1)

    // Five events land while the refetch the first one triggers is still in flight.
    await act(async () => {
      for (let i = 0; i < 5; i += 1) hoisted.client!.emitEvent(Action.UPDATED)
    })

    // One refetch in flight for the whole burst — not one request per event.
    expect(mockedFetch).toHaveBeenCalledTimes(2)
    expect(resolvers).toHaveLength(1)

    // Draining the in-flight refetch fires exactly one trailing refetch for the changes
    // that arrived mid-flight.
    await act(async () => {
      resolvers[0](response(["u1", "u2"]))
    })
    await waitFor(() => expect(resolvers).toHaveLength(2))
    expect(mockedFetch).toHaveBeenCalledTimes(3)

    // Draining the trailing refetch quiesces — no further requests.
    await act(async () => {
      resolvers[1](response(["u1", "u2"]))
    })
    await waitFor(() => expect(result.current.users.map(u => u.id)).toEqual(["u1", "u2"]))
    expect(mockedFetch).toHaveBeenCalledTimes(3)
  })

  test("refetches after a socket reconnect and keeps data on screen during the refetch", async () => {
    let resolveRefetch!: (value: ReturnType<typeof response>) => void
    mockedFetch
      .mockResolvedValueOnce(response(["u1"]))
      .mockReturnValueOnce(
        new Promise<ReturnType<typeof response>>(resolve => {
          resolveRefetch = resolve
        }) as never
      )
    const { result } = renderHook(() => useOrganizationMembers())
    await waitFor(() => expect(result.current.users.map(u => u.id)).toEqual(["u1"]))

    await act(async () => {
      hoisted.client!.emitReconnect()
    })

    // Previous data stays visible while the refetch is in flight — no loading flash.
    expect(result.current.users.map(u => u.id)).toEqual(["u1"])
    expect(result.current.loading).toBe(false)

    await act(async () => {
      resolveRefetch(response(["u1", "u2"]))
    })
    await waitFor(() => expect(result.current.users.map(u => u.id)).toEqual(["u1", "u2"]))
  })

  test("ignores unrelated channel actions", async () => {
    mockedFetch.mockResolvedValueOnce(response(["u1"]))
    const { result } = renderHook(() => useOrganizationMembers())
    await waitFor(() => expect(result.current.users.map(u => u.id)).toEqual(["u1"]))

    act(() => hoisted.client!.emitEvent(Action.TYPING))

    expect(mockedFetch).toHaveBeenCalledTimes(1)
  })

  test("a failed load does not loop and recovers on a channel invalidate", async () => {
    // The first fetch fails and the query lands in error. retryOnMount is off, so a
    // new observer never re-hits the endpoint — the only recovery path is a channel
    // (or reconnect) invalidate, which the still-armed subscription delivers.
    mockedFetch.mockRejectedValueOnce(new Error("boom"))
    const { result } = renderHook(() => useOrganizationMembers())
    await waitFor(() => expect(result.current.error).toBeTruthy())
    expect(mockedFetch).toHaveBeenCalledTimes(1)

    await act(async () => {
      await Promise.resolve()
    })
    expect(mockedFetch).toHaveBeenCalledTimes(1)

    mockedFetch.mockResolvedValueOnce(response(["u1"]))
    await act(async () => {
      hoisted.client!.emitEvent(Action.UPDATED)
    })
    await waitFor(() => expect(result.current.users.map(u => u.id)).toEqual(["u1"]))
  })
})
