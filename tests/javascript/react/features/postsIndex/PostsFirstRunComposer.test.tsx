import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

vi.mock("~/react/shared/apiFetch", () => ({ apiFetch: vi.fn() }))
vi.mock("~/shared/flash", () => ({ showFlash: vi.fn() }))
vi.mock("~/react/shared/hooks/useLinkPreviewUnfurl", () => ({ useLinkPreviewUnfurl: vi.fn() }))

// Stub the ProseMirror-backed composer with a ref handle (mirrors NewPostForm.test).
vi.mock("~/react/composites/editor/RichTextComposer", async () => {
  const React = await vi.importActual<typeof import("react")>("react")
  return {
    RichTextComposer: React.forwardRef((_props, ref) => {
      React.useImperativeHandle(ref, () => ({
        getContent: () => "",
        isEmpty: () => true,
        insertImage: () => {},
        focus: () => {},
        cancelPendingChange: () => {},
        attachmentClaimId: "claim-1",
      }))
      return React.createElement("div", { "data-testid": "rich-text-composer" })
    }),
  }
})

import { PostsFirstRunComposer } from "~/react/features/postsIndex/components/PostsFirstRunComposer"
import { useLinkPreviewUnfurl } from "~/react/shared/hooks/useLinkPreviewUnfurl"

import { cleanup, fireEvent, render, screen } from "../../shared/testUtils"

const mockUnfurl = vi.mocked(useLinkPreviewUnfurl)

beforeEach(() => {
  // No link preview in these cases; the unfurl hook's own behavior is tested elsewhere.
  mockUnfurl.mockReturnValue({
    composePreview: null,
    dismissComposePreview: vi.fn(),
    isUrlDismissed: () => false,
  } as unknown as ReturnType<typeof useLinkPreviewUnfurl>)
  // applyWelcome scrolls the composer into view; jsdom doesn't implement it.
  Element.prototype.scrollIntoView = vi.fn()
})

afterEach(() => {
  cleanup()
})

describe("PostsFirstRunComposer", () => {
  test("shows the welcome-post builder for admins and the teaching prompt otherwise", () => {
    // Admin (canAnnounce): the welcome-post builder with migration chips.
    const { rerender } = render(<PostsFirstRunComposer canAnnounce={true} orgGroups={[]} onCreated={vi.fn()} />)
    expect(screen.getByText("Welcome your team")).toBeTruthy()
    expect(screen.getByRole("button", { name: /Slack/ })).toBeTruthy()
    expect(screen.getByRole("button", { name: /Use in a welcome post/ })).toBeTruthy()
    expect(screen.queryByText("Start your team’s record")).toBeNull()

    // Non-admin with no groups: the plain teaching prompt + invite link, no builder.
    rerender(<PostsFirstRunComposer canAnnounce={false} orgGroups={[]} onCreated={vi.fn()} />)
    expect(screen.getByText("Start your team’s record")).toBeTruthy()
    expect(screen.getByRole("link", { name: "Invite your team" })).toBeTruthy()
    expect(screen.queryByText("Welcome your team")).toBeNull()
  })

  test("using the welcome builder fills the composer title", () => {
    render(<PostsFirstRunComposer canAnnounce={true} orgGroups={[]} onCreated={vi.fn()} />)
    const title = screen.getByLabelText("Post title") as HTMLInputElement
    expect(title.value).toBe("")

    fireEvent.click(screen.getByRole("button", { name: /Use in a welcome post/ }))
    expect(title.value).toBe("Welcome to our new home base")
  })
})
