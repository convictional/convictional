import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

import { InteractiveMessageBubble } from "~/react/composites/chat/InteractiveMessageBubble"
import type { ChatMessage, Decision } from "~/react/shared/types"

// Stub the heavy children so this test isolates the decision-marker wiring.
// MessageActions surfaces the onToggleDecision it receives so we can assert the
// undecided affordance lands in the hover toolbar, not the footer.
vi.mock("~/react/composites/chat/MessageBubble", () => ({
  MessageBubble: ({ afterBubble }: { afterBubble?: React.ReactNode }) => <div>{afterBubble}</div>,
}))
vi.mock("~/react/composites/chat/MessageActions", () => ({
  MessageActions: ({ onToggleDecision }: { onToggleDecision?: () => void }) =>
    onToggleDecision ? (
      <button data-testid="toolbar-decide" onClick={onToggleDecision}>
        decide
      </button>
    ) : null,
}))
vi.mock("~/react/composites/chat/MessageActionSheet", () => ({ MessageActionSheet: () => null }))
vi.mock("~/react/composites/chat/EditMessageForm", () => ({ EditMessageForm: () => null }))
// Chips and the inline add-reaction menu are flat siblings in the footer (not a
// ReactionBar wrapper), so they're stubbed individually. ReactionChips mirrors
// the real "renders nothing when empty" so an empty map asserts as absent.
vi.mock("~/react/composites/reactions/ReactionChips", () => ({
  ReactionChips: ({ reactions }: { reactions: Record<string, unknown[]> }) =>
    Object.values(reactions).some(users => users.length > 0) ? <div data-testid="reaction-chips" /> : null,
}))
vi.mock("~/react/composites/reactions/ReactionMenu", () => ({
  ReactionMenu: () => <div data-testid="add-reaction-menu" />,
}))
vi.mock("~/react/composites/DecisionMarker", () => ({
  DecisionMarker: ({ decision, onToggle }: { decision: unknown; onToggle: () => void }) => (
    <button data-testid="decision-pill" data-decided={decision !== undefined} onClick={onToggle}>
      marker
    </button>
  ),
}))

function makeMessage(overrides: Partial<ChatMessage> = {}): ChatMessage {
  return {
    id: "m1",
    global_id: "gid://convictional/ChatMessage/m1",
    content: "hello",
    created_at: "2026-04-30T12:00:00Z",
    edited_at: null,
    reactions: {},
    user: { id: "u-author", display_name: "Author", picture: null },
    link_preview: null,
    reply_to: null,
    ...overrides,
  }
}

const decision: Decision = {
  id: "d1",
  comment_gid: "gid://convictional/ChatMessage/m1",
  comment_preview: "hello",
  decided_by: { id: "u1", display_name: "Alice", picture: null },
  decided_at: "2026-05-01T00:00:00Z",
}

const baseProps = {
  className: "",
  currentUserId: "u-self",
  isEditing: false,
  chatType: "dm" as const,
  uploadUrl: null,
  mentionableUsers: [],
  klipyApiKey: null,
  onScrollTo: vi.fn(),
  scrollingToId: null,
  onEdit: vi.fn(),
  onCancelEdit: vi.fn(),
  onSaveEdit: vi.fn().mockResolvedValue(undefined),
  onDelete: vi.fn(),
  onReact: vi.fn(),
  onReply: vi.fn(),
}

afterEach(() => cleanup())

describe("InteractiveMessageBubble decision marker", () => {
  test("renders no marker or footer when the island wired no decisions handler", () => {
    render(<InteractiveMessageBubble {...baseProps} message={makeMessage()} />)
    expect(screen.queryByTestId("decision-pill")).not.toBeInTheDocument()
    expect(screen.queryByTestId("toolbar-decide")).not.toBeInTheDocument()
    // No reactions and no decision → no footer at all.
    expect(screen.queryByTestId("reaction-chips")).not.toBeInTheDocument()
    expect(screen.queryByTestId("add-reaction-menu")).not.toBeInTheDocument()
  })

  test("undecided with no reactions: the Decide affordance is in the hover toolbar", () => {
    const onToggleDecision = vi.fn()
    render(<InteractiveMessageBubble {...baseProps} message={makeMessage()} onToggleDecision={onToggleDecision} />)

    expect(screen.queryByTestId("decision-pill")).not.toBeInTheDocument()
    fireEvent.click(screen.getByTestId("toolbar-decide"))
    expect(onToggleDecision).toHaveBeenCalledWith("gid://convictional/ChatMessage/m1")
  })

  test("undecided with reactions: the Decide marker rides the footer, not the toolbar", () => {
    const onToggleDecision = vi.fn()
    render(
      <InteractiveMessageBubble
        {...baseProps}
        message={makeMessage({ reactions: { "👍": [{ id: "u2", display_name: "Bob", picture: null }] } })}
        onToggleDecision={onToggleDecision}
      />
    )

    // The footer is the host once a reaction exists — decisions read as a
    // special reaction — so the toolbar drops its Decide affordance.
    expect(screen.queryByTestId("toolbar-decide")).not.toBeInTheDocument()
    // Desktop keeps the inline add-reaction menu alongside the chips.
    expect(screen.getByTestId("add-reaction-menu")).toBeInTheDocument()
    expect(screen.getByTestId("reaction-chips")).toBeInTheDocument()
    const marker = screen.getByTestId("decision-pill")
    expect(marker).toHaveAttribute("data-decided", "false")
    fireEvent.click(marker)
    expect(onToggleDecision).toHaveBeenCalledWith("gid://convictional/ChatMessage/m1")
  })

  test("decided: the pill is in the always-visible footer and clears by global_id", () => {
    const onToggleDecision = vi.fn()
    render(
      <InteractiveMessageBubble
        {...baseProps}
        message={makeMessage()}
        decision={decision}
        onToggleDecision={onToggleDecision}
      />
    )

    // Once decided, the toolbar affordance is gone — the pill is the toggle.
    expect(screen.queryByTestId("toolbar-decide")).not.toBeInTheDocument()
    const pill = screen.getByTestId("decision-pill")
    expect(pill).toHaveAttribute("data-decided", "true")
    fireEvent.click(pill)
    expect(onToggleDecision).toHaveBeenCalledWith("gid://convictional/ChatMessage/m1")
  })
})

describe("InteractiveMessageBubble footer on mobile", () => {
  // useIsMobile() reads this attribute off <html>; set it for the mobile branch.
  beforeEach(() => {
    document.documentElement.dataset.isMobile = "true"
  })
  afterEach(() => {
    delete document.documentElement.dataset.isMobile
  })

  const reacted = { reactions: { "👍": [{ id: "u2", display_name: "Bob", picture: null }] } }

  test("reactions without a decision: chips only — no inline add menu, no Decide affordance", () => {
    const onToggleDecision = vi.fn()
    render(
      <InteractiveMessageBubble {...baseProps} message={makeMessage(reacted)} onToggleDecision={onToggleDecision} />
    )

    expect(screen.getByTestId("reaction-chips")).toBeInTheDocument()
    // Reacting happens through the long-press sheet on mobile, so the inline
    // add-reaction menu never rides the footer.
    expect(screen.queryByTestId("add-reaction-menu")).not.toBeInTheDocument()
    // The undecided marker is decided-only on mobile — Decide lives in the sheet.
    expect(screen.queryByTestId("decision-pill")).not.toBeInTheDocument()
    expect(screen.queryByTestId("toolbar-decide")).not.toBeInTheDocument()
  })

  test("decided: the pill shows and toggles, still with no inline add menu", () => {
    const onToggleDecision = vi.fn()
    render(
      <InteractiveMessageBubble
        {...baseProps}
        message={makeMessage(reacted)}
        decision={decision}
        onToggleDecision={onToggleDecision}
      />
    )

    const pill = screen.getByTestId("decision-pill")
    expect(pill).toHaveAttribute("data-decided", "true")
    expect(screen.queryByTestId("add-reaction-menu")).not.toBeInTheDocument()
    fireEvent.click(pill)
    expect(onToggleDecision).toHaveBeenCalledWith("gid://convictional/ChatMessage/m1")
  })
})
