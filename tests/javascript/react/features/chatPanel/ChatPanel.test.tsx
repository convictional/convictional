import { cleanup, render, screen, fireEvent } from "../../shared/testUtils"
import { type RefObject } from "react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

import { ChatPanel } from "../../../../../app/javascript/react/features/chatPanel/ChatPanel"
import { resetCurrentUser, setCurrentUser } from "../../shared/currentUserFixtures"
import type { ChatMessage, ReplyPreview, User } from "../../../../../app/javascript/react/shared/types"
import type { ChatPanelState } from "../../../../../app/javascript/react/features/chatPanel/types"

// Shared mutable state captured by the editor mock so tests can invoke its
// imperative handle and inspect the props the panel passes down.
const editorMock = vi.hoisted(() => ({
  focus: vi.fn(),
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  lastProps: null as any,
}))

// Mock ChatComposerEditor — it depends on ProseMirror internals that don't run in jsdom.
// The mock exposes a focus() handle so the panel's editorRef.current?.focus()
// effects are observable from tests.
vi.mock("../../../../../app/javascript/react/composites/chat/ChatComposerEditor", async () => {
  const React = await import("react")
  return {
    ChatComposerEditor: React.forwardRef(function ChatComposerEditor(props: Record<string, unknown>, ref) {
      editorMock.lastProps = props
      React.useImperativeHandle(ref, () => ({
        focus: editorMock.focus,
        send: () => {},
        triggerUpload: () => {},
        uploadFiles: () => {},
        insertImage: () => {},
      }))
      return <div data-testid="chat-editor">Editor</div>
    }),
  }
})

// Mock useScrollToReply — it relies on DOM scrolling APIs unavailable in jsdom
const mockScrollToReply = vi.fn()
vi.mock("../../../../../app/javascript/react/shared/hooks/useScrollToReply", () => ({
  useScrollToReply: vi.fn(() => ({
    scrollToReply: mockScrollToReply,
    scrollingToReplyRef: { current: false },
    scrollingToId: null,
  })),
}))

const noopFn = () => {}
const noopAsync = async () => {}

const defaultHookReturn = {
  panelState: null as ChatPanelState | null,
  messages: [] as ChatMessage[],
  loading: false,
  loadingMore: false,
  hasMore: false,
  nextCursorRef: { current: null } as RefObject<string | null>,
  sending: false,
  sendError: false,
  replyTo: null as ReplyPreview | null,
  claimId: "claim-1",
  uploadUrl: null as string | null,
  currentUserId: "u1" as string | null,
  editingMessageId: null as string | null,
  typingUsers: [] as User[],
  initialDraft: "",
  sendMessage: noopAsync,
  editMessage: noopAsync,
  deleteMessage: noopAsync,
  toggleReaction: noopAsync,
  setEditingMessageId: noopFn as (messageId: string | null) => void,
  cancelEdit: noopFn,
  loadMore: noopAsync,
  loadNewer: noopAsync,
  loadingNewer: false,
  hasNewer: false,
  jumpToMessage: noopAsync,
  jumpToLatest: noopAsync,
  atTail: true,
  minimize: noopFn,
  restore: noopFn,
  close: noopFn,
  retryLoad: noopFn,
  setDraftContent: noopFn,
  setReplyTo: noopFn as (reply: ReplyPreview | null) => void,
  composePreview: null,
  dismissComposePreview: noopFn,
}

vi.mock("../../../../../app/javascript/react/features/chatPanel/useChatPanelState", () => ({
  useChatPanelState: vi.fn(() => defaultHookReturn),
}))

import { useChatPanelState } from "../../../../../app/javascript/react/features/chatPanel/useChatPanelState"
const mockUseChatPanelState = vi.mocked(useChatPanelState)

function setHookReturn(overrides: Partial<typeof defaultHookReturn>) {
  mockUseChatPanelState.mockReturnValue({ ...defaultHookReturn, ...overrides })
}

function makePanelState(overrides: Partial<ChatPanelState> = {}): ChatPanelState {
  return {
    chatId: "c1",
    workspaceId: "w1",
    uploadUrl: null,
    supportsMentions: false,
    display: {
      title: "Alice",
      type: "dm",
      collaborators: [
        { id: "col-1", user: { id: "u1", display_name: "Me", picture: null } },
        { id: "col-2", user: { id: "u2", display_name: "Alice", picture: null } },
      ],
    },
    minimized: false,
    draftContent: "",
    incomplete: false,
    loadFailed: false,
    ...overrides,
  }
}

function makeMessage(overrides: Partial<ChatMessage> = {}): ChatMessage {
  return {
    id: "m1",
    content: "hello",
    created_at: "2026-01-01T00:00:00Z",
    edited_at: null,
    reactions: {},
    user: { id: "u1", display_name: "Alice", picture: null },
    link_preview: null,
    reply_to: null,
    ...overrides,
  }
}

function makeReplyPreview(overrides: Partial<ReplyPreview> = {}): ReplyPreview {
  return { id: "m1", user_name: "Alice", content_preview: "hello", is_deleted: false, ...overrides }
}

beforeEach(() => {
  setCurrentUser({ id: "u1", display_name: "Me" })
})

afterEach(() => {
  cleanup()
  resetCurrentUser()
  vi.clearAllMocks()
  editorMock.lastProps = null
})

describe("ChatPanel", () => {
  test("renders nothing when panelState is null", () => {
    setHookReturn({ panelState: null })
    const { container } = render(<ChatPanel />)
    expect(container.innerHTML).toBe("")
  })

  test("renders minimized bar with display title", () => {
    setHookReturn({ panelState: makePanelState({ minimized: true }) })
    render(<ChatPanel />)
    expect(screen.getByText("Alice")).toBeTruthy()
    expect(screen.queryByTestId("chat-editor")).toBeNull()
  })

  test("calls restore when clicking the minimized bar", () => {
    const restore = vi.fn()
    setHookReturn({ panelState: makePanelState({ minimized: true }), restore })
    render(<ChatPanel />)
    fireEvent.click(screen.getByText("Alice"))
    expect(restore).toHaveBeenCalledOnce()
  })

  test("calls close from minimized bar without restoring", () => {
    const close = vi.fn()
    const restore = vi.fn()
    setHookReturn({ panelState: makePanelState({ minimized: true }), close, restore })
    render(<ChatPanel />)
    fireEvent.click(screen.getByText("close"))
    expect(close).toHaveBeenCalledOnce()
    expect(restore).not.toHaveBeenCalled()
  })

  test("renders full panel with header, messages, and editor", () => {
    setHookReturn({
      panelState: makePanelState(),
      messages: [makeMessage()],
    })
    render(<ChatPanel />)
    expect(screen.getAllByText("Alice").length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText("hello")).toBeTruthy()
    expect(screen.getByTestId("chat-editor")).toBeTruthy()
  })

  test("renders group chat header with group icon", () => {
    setHookReturn({
      panelState: makePanelState({
        display: {
          title: "Eng",
          type: "group",
          collaborators: [{ id: "col-1", user: { id: "u2", display_name: "Bob", picture: null } }],
        },
      }),
    })
    render(<ChatPanel />)
    expect(screen.getByText("group")).toBeTruthy()
    expect(screen.getAllByText("Eng").length).toBeGreaterThanOrEqual(1)
  })

  test("renders self chat header with edit_note icon", () => {
    setHookReturn({
      panelState: makePanelState({
        display: { title: "Me", type: "self", collaborators: [] },
      }),
    })
    render(<ChatPanel />)
    expect(screen.getByText("edit_note")).toBeTruthy()
  })

  test("renders multi chat header with avatar group", () => {
    const { container } = (() => {
      setHookReturn({
        panelState: makePanelState({
          display: {
            title: "Project",
            type: "multi",
            collaborators: [
              { id: "col-1", user: { id: "u2", display_name: "Bob", picture: null } },
              { id: "col-2", user: { id: "u3", display_name: "Carol", picture: null } },
              { id: "col-3", user: { id: "u4", display_name: "Dave", picture: null } },
            ],
          },
        }),
      })
      return render(<ChatPanel />)
    })()
    expect(screen.getAllByText("Project").length).toBeGreaterThanOrEqual(1)
    // AvatarGroup renders the first letters of the visible users plus an overflow badge.
    expect(container.textContent).toContain("+1")
  })

  test("shows 'open in new' link when chatId is set", () => {
    setHookReturn({ panelState: makePanelState({ chatId: "c42" }) })
    render(<ChatPanel />)
    const link = screen.getByTitle("Open full chat")
    expect(link.getAttribute("href")).toBe("/chats/c42")
  })

  test("hides editor when chatId is null (still loading chat)", () => {
    setHookReturn({ panelState: makePanelState({ chatId: null }) })
    render(<ChatPanel />)
    expect(screen.queryByTestId("chat-editor")).toBeNull()
  })

  test("shows loading state when loading with no messages", () => {
    setHookReturn({ panelState: makePanelState(), loading: true, messages: [] })
    render(<ChatPanel />)
    expect(screen.getByText("Loading...")).toBeTruthy()
  })

  test("shows empty state when not loading and no messages", () => {
    setHookReturn({ panelState: makePanelState(), loading: false, messages: [] })
    render(<ChatPanel />)
    expect(screen.getByText("No messages yet. Say hello!")).toBeTruthy()
  })

  test("renders multiple messages", () => {
    setHookReturn({
      panelState: makePanelState(),
      messages: [
        makeMessage({
          id: "m1",
          content: "first",
          user: { id: "u1", display_name: "Alice", picture: null },
        }),
        makeMessage({
          id: "m2",
          content: "second",
          user: { id: "u2", display_name: "Bob", picture: null },
        }),
      ],
    })
    render(<ChatPanel />)
    expect(screen.getByText("first")).toBeTruthy()
    expect(screen.getByText("second")).toBeTruthy()
    expect(screen.getByText("Bob")).toBeTruthy()
  })

  test("shows send error message", () => {
    setHookReturn({ panelState: makePanelState(), sendError: true })
    render(<ChatPanel />)
    expect(screen.getByText("Message failed to send. Try again.")).toBeTruthy()
  })

  test("calls minimize and close from the full panel header", () => {
    const minimize = vi.fn()
    const close = vi.fn()
    setHookReturn({ panelState: makePanelState(), minimize, close })
    render(<ChatPanel />)
    fireEvent.click(screen.getByTitle("Minimize"))
    expect(minimize).toHaveBeenCalledOnce()
    fireEvent.click(screen.getByTitle("Close"))
    expect(close).toHaveBeenCalledOnce()
  })

  test("each message has a reply button that calls setReplyTo", () => {
    const setReplyTo = vi.fn()
    setHookReturn({
      panelState: makePanelState(),
      messages: [
        makeMessage({ id: "m1", content: "hey there", user: { id: "u2", display_name: "Bob", picture: null } }),
      ],
      setReplyTo,
    })
    render(<ChatPanel />)
    fireEvent.click(screen.getByLabelText("Reply"))
    expect(setReplyTo).toHaveBeenCalledWith({
      id: "m1",
      user_name: "Bob",
      content_preview: "hey there",
      is_deleted: false,
    })
  })

  test("shows reply preview in compose area when replyTo is set", () => {
    setHookReturn({
      panelState: makePanelState(),
      replyTo: makeReplyPreview({ user_name: "Bob", content_preview: "original message" }),
    })
    render(<ChatPanel />)
    expect(screen.getByText("Bob")).toBeTruthy()
    expect(screen.getByText("original message")).toBeTruthy()
  })

  test("cancel reply button calls setReplyTo with null", () => {
    const setReplyTo = vi.fn()
    setHookReturn({
      panelState: makePanelState(),
      replyTo: makeReplyPreview(),
      setReplyTo,
    })
    render(<ChatPanel />)
    fireEvent.click(screen.getByLabelText("Cancel reply"))
    expect(setReplyTo).toHaveBeenCalledWith(null)
  })

  test("does not show reply preview when replyTo is null", () => {
    setHookReturn({ panelState: makePanelState(), replyTo: null })
    render(<ChatPanel />)
    expect(screen.queryByLabelText("Cancel reply")).toBeNull()
  })

  describe("jump-to-latest pill", () => {
    test("shows the pill and routes to onJumpToLatest while not at the tail", () => {
      const jumpToLatest = vi.fn()
      setHookReturn({
        panelState: makePanelState(),
        messages: [makeMessage()],
        atTail: false,
        jumpToLatest,
      })
      render(<ChatPanel />)
      const pill = screen.getByRole("button", { name: /Jump to latest/i })
      fireEvent.click(pill)
      expect(jumpToLatest).toHaveBeenCalledOnce()
    })

    test("does not show the pill when at the tail", () => {
      setHookReturn({ panelState: makePanelState(), messages: [makeMessage()], atTail: true })
      render(<ChatPanel />)
      expect(screen.queryByRole("button", { name: /Jump to latest|New messages/i })).toBeNull()
    })
  })

  describe("up arrow to edit previous message", () => {
    test("onEditPrevious selects the current user's most recent message", () => {
      const setEditingMessageId = vi.fn()
      setHookReturn({
        panelState: makePanelState(),
        currentUserId: "u1",
        setEditingMessageId,
        messages: [
          makeMessage({ id: "m1", user: { id: "u1", display_name: "Alice", picture: null } }),
          makeMessage({ id: "m2", user: { id: "u2", display_name: "Bob", picture: null } }),
          makeMessage({ id: "m3", user: { id: "u1", display_name: "Alice", picture: null } }),
          makeMessage({ id: "m4", user: { id: "u2", display_name: "Bob", picture: null } }),
        ],
      })
      render(<ChatPanel />)
      const handled = editorMock.lastProps.onEditPrevious()
      expect(handled).toBe(true)
      expect(setEditingMessageId).toHaveBeenCalledWith("m3")
    })

    test("onEditPrevious returns false when the user has no prior messages", () => {
      const setEditingMessageId = vi.fn()
      setHookReturn({
        panelState: makePanelState(),
        currentUserId: "u1",
        setEditingMessageId,
        messages: [makeMessage({ id: "m1", user: { id: "u2", display_name: "Bob", picture: null } })],
      })
      render(<ChatPanel />)
      expect(editorMock.lastProps.onEditPrevious()).toBe(false)
      expect(setEditingMessageId).not.toHaveBeenCalled()
    })
  })

  describe("editor refocus", () => {
    test("focuses the editor when editingMessageId transitions back to null", () => {
      setHookReturn({ panelState: makePanelState(), editingMessageId: "m1" })
      const { rerender } = render(<ChatPanel />)
      // Initial render with active edit; no focus yet.
      expect(editorMock.focus).not.toHaveBeenCalled()
      setHookReturn({ panelState: makePanelState(), editingMessageId: null })
      rerender(<ChatPanel />)
      expect(editorMock.focus).toHaveBeenCalledOnce()
    })

    test("does not focus the editor on initial mount when not editing", () => {
      setHookReturn({ panelState: makePanelState(), editingMessageId: null })
      render(<ChatPanel />)
      expect(editorMock.focus).not.toHaveBeenCalled()
    })
  })
})
