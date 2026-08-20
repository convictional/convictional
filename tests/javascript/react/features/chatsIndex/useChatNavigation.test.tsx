import { act, renderHook, waitFor } from "../../shared/testUtils"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

const navigateSpy = vi.fn()

// The index URL the hook stamps as the new chat's return_to. Mock useLocation so
// the hook resolves it without a full RouterProvider, and useNavigate so we can
// assert the typed navigation args directly.
vi.mock("@tanstack/react-router", async importActual => ({
  ...(await importActual<typeof import("@tanstack/react-router")>()),
  useNavigate: () => navigateSpy,
  useLocation: (opts?: { select?: (loc: { href: string }) => unknown }) => {
    const location = { href: "/chats", pathname: "/chats", search: "" }
    return opts?.select ? opts.select(location) : location
  },
}))

vi.mock("../../../../../app/javascript/react/shared/apiFetch", () => ({
  apiFetch: vi.fn(),
  ApiError: class extends Error {},
}))

import { apiFetch } from "../../../../../app/javascript/react/shared/apiFetch"
import { useChatNavigation } from "../../../../../app/javascript/react/features/chatsIndex/hooks/useChatNavigation"

const mockApi = vi.mocked(apiFetch)

beforeEach(() => {
  navigateSpy.mockReset()
  mockApi.mockReset()
})

afterEach(() => {
  vi.clearAllMocks()
})

describe("useChatNavigation", () => {
  test("selectChat client-navigates to the chat route, stamping the index as return_to", () => {
    const { result } = renderHook(() => useChatNavigation())

    act(() => result.current.selectChat("c9"))

    expect(navigateSpy).toHaveBeenCalledTimes(1)
    expect(navigateSpy).toHaveBeenCalledWith({
      to: "/chats/$chatId",
      params: { chatId: "c9" },
      search: { return_to: "/chats" },
    })
    expect(result.current.navigating).toBe(true)
    expect(result.current.navigatingId).toBe("c9")
  })

  test("selectChat guards against a double navigation", () => {
    const { result } = renderHook(() => useChatNavigation())

    act(() => {
      result.current.selectChat("c9")
      result.current.selectChat("c9")
    })

    expect(navigateSpy).toHaveBeenCalledTimes(1)
  })

  test("createAndNavigate POSTs then navigates to the created chat; concurrent calls are guarded", async () => {
    mockApi.mockResolvedValue({ chat_id: "new-1", workspace_id: "ws-1" } as never)
    const { result } = renderHook(() => useChatNavigation())

    await act(async () => {
      await Promise.all([
        result.current.createAndNavigate({ recipient_ids: ["u1"] }),
        result.current.createAndNavigate({ recipient_ids: ["u1"] }),
      ])
    })

    expect(mockApi).toHaveBeenCalledTimes(1)
    expect(mockApi).toHaveBeenCalledWith("/api/chats", { method: "POST", body: JSON.stringify({ recipient_ids: ["u1"] }) })
    await waitFor(() =>
      expect(navigateSpy).toHaveBeenCalledWith({
        to: "/chats/$chatId",
        params: { chatId: "new-1" },
        search: { return_to: "/chats" },
      })
    )
  })
})
