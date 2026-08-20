import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

vi.mock("~/react/shared/apiFetch", () => ({ apiFetch: vi.fn() }))
vi.mock("~/shared/flash", () => ({ showFlash: vi.fn() }))
vi.mock("~/react/shared/hooks/useCurrentUser", () => ({ useCurrentUser: vi.fn() }))

const { navigateMock } = vi.hoisted(() => ({ navigateMock: vi.fn() }))
vi.mock("@tanstack/react-router", async () => {
  const actual = await vi.importActual<typeof import("@tanstack/react-router")>("@tanstack/react-router")
  return { ...actual, useNavigate: () => navigateMock }
})
// The unfurl hook is the seam: its debounce/fetch/dismiss internals are covered
// by tests/javascript/react/shared/useLinkPreviewUnfurl.test.ts.
vi.mock("~/react/shared/hooks/useLinkPreviewUnfurl", () => ({ useLinkPreviewUnfurl: vi.fn() }))

const { cancelPendingChangeSpy } = vi.hoisted(() => ({ cancelPendingChangeSpy: vi.fn() }))

// Stub the ProseMirror-backed composer with a ref handle returning fixed content.
vi.mock("~/react/composites/editor/RichTextComposer", async () => {
  const React = await vi.importActual<typeof import("react")>("react")
  return {
    RichTextComposer: React.forwardRef((_props, ref) => {
      React.useImperativeHandle(ref, () => ({
        getContent: () => "body text",
        // isEmpty reports true (text-only emptiness) even though getContent has
        // content — the GIF-only case. The form must key off getContent, not
        // isEmpty, so a GIF-only body still posts.
        isEmpty: () => true,
        insertImage: () => {},
        focus: () => {},
        cancelPendingChange: cancelPendingChangeSpy,
        attachmentClaimId: "claim-123",
      }))
      return React.createElement("div", { "data-testid": "rich-text-composer" })
    }),
  }
})

// Stub the GIF picker so its presence is detectable without the Klipy fetch.
vi.mock("~/react/composites/editor/components/GifPicker", () => ({
  GifPicker: () => <button type="button">GIF</button>,
}))

import { NewPostForm } from "~/react/features/postsIndex/components/NewPostForm"
import { apiFetch } from "~/react/shared/apiFetch"
import { useCurrentUser } from "~/react/shared/hooks/useCurrentUser"
import { useLinkPreviewUnfurl } from "~/react/shared/hooks/useLinkPreviewUnfurl"

const mockApiFetch = vi.mocked(apiFetch)
const mockUseCurrentUser = vi.mocked(useCurrentUser)
const mockUseLinkPreviewUnfurl = vi.mocked(useLinkPreviewUnfurl)

const PREVIEW = {
  url: "https://example.com",
  type: "link" as const,
  title: "Example Site",
  description: "A description",
  image_url: null,
  site_name: null,
  domain: "example.com",
}

function setUnfurl(overrides: Partial<ReturnType<typeof useLinkPreviewUnfurl>> = {}) {
  const value = {
    composePreview: null,
    dismissComposePreview: vi.fn(),
    dismissed: false,
    isUrlDismissed: () => false,
    ...overrides,
  }
  mockUseLinkPreviewUnfurl.mockReturnValue(value)
  return value
}

function setKlipy(key: string | null) {
  mockUseCurrentUser.mockReturnValue({
    user: { id: "user-1", display_name: "Alice", email: "a@b.c", is_superuser: false, picture: null },
    clientConfig: { klipy_api_key: key },
    loading: false,
    error: null,
  } as unknown as ReturnType<typeof useCurrentUser>)
}

beforeEach(() => {
  mockApiFetch.mockReset()
  cancelPendingChangeSpy.mockReset()
  setKlipy(null)
  setUnfurl()
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe("NewPostForm", () => {
  test("expands when the editor area is clicked, revealing the New Post chip", () => {
    render(<NewPostForm canAnnounce={false} orgGroups={[]} onCreated={vi.fn()} />)
    // The editor is always mounted; collapsed state just hides the New Post chip.
    expect(screen.queryByText("New Post")).not.toBeInTheDocument()

    fireEvent.click(screen.getByTestId("rich-text-composer"))

    expect(screen.getByText("New Post")).toBeInTheDocument()
  })

  test("hides the Announcement option when canAnnounce is false", () => {
    render(<NewPostForm canAnnounce={false} orgGroups={[{ id: "g1", name: "Eng" }]} onCreated={vi.fn()} />)
    fireEvent.click(screen.getByText("Everyone"))
    expect(screen.getByText("Eng")).toBeInTheDocument()
    expect(screen.queryByText("Announcement")).not.toBeInTheDocument()
  })

  test("shows the Announcement option when canAnnounce is true", () => {
    render(<NewPostForm canAnnounce={true} orgGroups={[]} onCreated={vi.fn()} />)
    fireEvent.click(screen.getByText("Everyone"))
    expect(screen.getByText("Announcement")).toBeInTheDocument()
  })

  test("hides the GIF picker without a Klipy key, shows it with one", () => {
    const { rerender } = render(<NewPostForm canAnnounce={false} orgGroups={[]} onCreated={vi.fn()} />)
    expect(screen.queryByText("GIF")).not.toBeInTheDocument()

    setKlipy("klipy-key")
    rerender(<NewPostForm canAnnounce={false} orgGroups={[]} onCreated={vi.fn()} />)
    expect(screen.getByText("GIF")).toBeInTheDocument()
  })

  test("Post creates a published post via POST /api/posts and prepends it", async () => {
    const created = { id: "new-post" }
    mockApiFetch.mockResolvedValue(created)
    const onCreated = vi.fn()
    render(<NewPostForm canAnnounce={false} orgGroups={[]} onCreated={onCreated} />)

    fireEvent.click(screen.getByTestId("rich-text-composer"))
    fireEvent.change(screen.getByLabelText("Post title"), { target: { value: "My title" } })
    fireEvent.click(screen.getByRole("button", { name: "Post" }))

    await waitFor(() => expect(onCreated).toHaveBeenCalledWith(created))
    const [url, init] = mockApiFetch.mock.calls[0]
    expect(url).toBe("/api/posts")
    expect((init as RequestInit).method).toBe("POST")
    const body = JSON.parse((init as RequestInit).body as string)
    expect(body.title).toBe("My title")
    expect(body.content).toBe("body text")
    expect(body.unfurl_links).toBe(true)
    expect(body.attachment_claim_id).toBe("claim-123")
  })

  test("renders the live link preview card and wires its dismiss button", () => {
    const { dismissComposePreview } = setUnfurl({ composePreview: PREVIEW })
    render(<NewPostForm canAnnounce={false} orgGroups={[]} onCreated={vi.fn()} />)

    expect(screen.getByText("Example Site")).toBeInTheDocument()
    fireEvent.click(screen.getByLabelText("Dismiss link preview"))
    expect(dismissComposePreview).toHaveBeenCalled()
  })

  test("auto-fills a blank title from the preview, but never clobbers user input", () => {
    setUnfurl()
    const { rerender } = render(<NewPostForm canAnnounce={false} orgGroups={[]} onCreated={vi.fn()} />)
    const titleInput = screen.getByLabelText("Post title") as HTMLInputElement

    // Preview arrives with the title blank → auto-fill.
    setUnfurl({ composePreview: PREVIEW })
    rerender(<NewPostForm canAnnounce={false} orgGroups={[]} onCreated={vi.fn()} />)
    expect(titleInput.value).toBe("Example Site")

    // The user clears it; the same preview must not refill.
    fireEvent.change(titleInput, { target: { value: "" } })
    rerender(<NewPostForm canAnnounce={false} orgGroups={[]} onCreated={vi.fn()} />)
    expect(titleInput.value).toBe("")
  })

  test("does not overwrite a title the user already typed", () => {
    setUnfurl()
    const { rerender } = render(<NewPostForm canAnnounce={false} orgGroups={[]} onCreated={vi.fn()} />)
    const titleInput = screen.getByLabelText("Post title") as HTMLInputElement
    fireEvent.change(titleInput, { target: { value: "Mine" } })

    setUnfurl({ composePreview: PREVIEW })
    rerender(<NewPostForm canAnnounce={false} orgGroups={[]} onCreated={vi.fn()} />)
    expect(titleInput.value).toBe("Mine")
  })

  test("a dismissed preview posts with unfurl_links: false, judged on the fresh content", async () => {
    const isUrlDismissed = vi.fn(() => true)
    setUnfurl({ isUrlDismissed })
    mockApiFetch.mockResolvedValue({ id: "new-post" })
    const onCreated = vi.fn()
    render(<NewPostForm canAnnounce={false} orgGroups={[]} onCreated={onCreated} />)

    fireEvent.change(screen.getByLabelText("Post title"), { target: { value: "My title" } })
    fireEvent.click(screen.getByRole("button", { name: "Post" }))

    await waitFor(() => expect(onCreated).toHaveBeenCalled())
    // The verdict comes from the freshly-serialized editor content, not the
    // hook's debounced state.
    expect(isUrlDismissed).toHaveBeenCalledWith("body text")
    const body = JSON.parse((mockApiFetch.mock.calls[0][1] as RequestInit).body as string)
    expect(body.unfurl_links).toBe(false)
  })

  test("title auto-fill is capped at the server's 1000-char limit", () => {
    setUnfurl()
    const { rerender } = render(<NewPostForm canAnnounce={false} orgGroups={[]} onCreated={vi.fn()} />)

    setUnfurl({ composePreview: { ...PREVIEW, title: "x".repeat(1500) } })
    rerender(<NewPostForm canAnnounce={false} orgGroups={[]} onCreated={vi.fn()} />)

    expect((screen.getByLabelText("Post title") as HTMLInputElement).value).toBe("x".repeat(1000))
  })

  test("a successful post cancels any pending editor change flush before remounting", async () => {
    mockApiFetch.mockResolvedValue({ id: "new-post" })
    render(<NewPostForm canAnnounce={false} orgGroups={[]} onCreated={vi.fn()} />)

    fireEvent.change(screen.getByLabelText("Post title"), { target: { value: "My title" } })
    fireEvent.click(screen.getByRole("button", { name: "Post" }))

    await waitFor(() => expect(cancelPendingChangeSpy).toHaveBeenCalled())
  })

  test("search filters the group list", () => {
    render(
      <NewPostForm
        canAnnounce={false}
        orgGroups={[
          { id: "g1", name: "Engineering" },
          { id: "g2", name: "Design" },
        ]}
        onCreated={vi.fn()}
      />
    )

    fireEvent.click(screen.getByText("Everyone"))
    expect(screen.getByText("Engineering")).toBeInTheDocument()
    expect(screen.getByText("Design")).toBeInTheDocument()

    fireEvent.change(screen.getByPlaceholderText("Search groups…"), { target: { value: "eng" } })
    expect(screen.getByText("Engineering")).toBeInTheDocument()
    expect(screen.queryByText("Design")).toBeNull()
  })

  test("Create sharable draft posts to /api/posts/drafts and navigates to the editor", async () => {
    navigateMock.mockReset()
    mockApiFetch.mockResolvedValue({ id: "draft-9" })
    render(<NewPostForm canAnnounce={false} orgGroups={[]} onCreated={vi.fn()} />)

    fireEvent.click(screen.getByTestId("rich-text-composer"))
    fireEvent.click(screen.getByText("Create sharable draft"))

    await waitFor(() =>
      expect(navigateMock).toHaveBeenCalledWith({ to: "/posts/$postId/edit", params: { postId: "draft-9" } })
    )
    expect(mockApiFetch.mock.calls[0][0]).toBe("/api/posts/drafts")
  })
})
