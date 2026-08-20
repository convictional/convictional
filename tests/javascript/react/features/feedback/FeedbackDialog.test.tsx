import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { forwardRef, useImperativeHandle } from "react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

vi.mock("../../../../../app/javascript/react/shared/apiFetch", () => ({
  apiFetch: vi.fn(),
  ApiError: class extends Error {
    status: number
    body: null
    constructor(status: number, body: null = null) {
      super(`Request failed with status ${status}`)
      this.status = status
      this.body = body
    }
  },
}))

vi.mock("../../../../../app/javascript/react/features/feedback/sentry", () => ({
  captureFeedback: vi.fn().mockResolvedValue({ success: false }),
}))

// The real ProseMirror editor is exercised by the editor test suite. Here we
// stub it so tests can deterministically drive content + emptiness without
// running ProseMirror in jsdom.
const editorState = {
  empty: true,
  content: "",
  onChange: null as ((markdown: string) => void) | null,
}

vi.mock("../../../../../app/javascript/react/features/feedback/FeedbackEditor", () => {
  // eslint-disable-next-line react/display-name
  const FeedbackEditor = forwardRef<
    unknown,
    {
      uploadUrl: string | null
      autoFocus?: boolean
      onChange?: (markdown: string) => void
    }
  >(({ onChange }, ref) => {
    editorState.onChange = onChange ?? null
    useImperativeHandle(ref, () => ({
      getContent: () => editorState.content,
      isEmpty: () => editorState.empty,
      clear: () => {
        editorState.content = ""
        editorState.empty = true
        editorState.onChange?.("")
      },
      focus: () => {},
      attachmentClaimId: "00000000-0000-0000-0000-000000000001",
    }))
    return <div data-testid="mock-feedback-editor" />
  })
  return { FeedbackEditor }
})

import { apiFetch, ApiError } from "../../../../../app/javascript/react/shared/apiFetch"
import { FeedbackDialog } from "../../../../../app/javascript/react/features/feedback/FeedbackDialog"
import { feedbackDialogStore } from "../../../../../app/javascript/react/shared/stores/feedbackDialog"

const mockApiFetch = vi.mocked(apiFetch)

function openDialog() {
  act(() => {
    feedbackDialogStore.getState().open()
  })
}

function setEditorContent(content: string) {
  editorState.content = content
  editorState.empty = content.trim().length === 0
  act(() => {
    editorState.onChange?.(content)
  })
}

function clearEditor() {
  editorState.content = ""
  editorState.empty = true
}

describe("FeedbackDialog", () => {
  beforeEach(() => {
    mockApiFetch.mockReset()
    clearEditor()
    act(() => {
      feedbackDialogStore.setState({ isOpen: false })
    })
  })
  afterEach(cleanup)

  test("submitting normally posts once, clears the editor, and closes the dialog", async () => {
    mockApiFetch.mockResolvedValueOnce({ success: true })
    render(<FeedbackDialog uploadUrl="/attachments/upload" />)
    openDialog()

    setEditorContent("It works great")

    const submit = await screen.findByRole("button", { name: /submit/i })
    await waitFor(() => expect(submit).not.toBeDisabled())
    fireEvent.click(submit)

    await waitFor(() => expect(mockApiFetch).toHaveBeenCalledTimes(1))
    const [url, options] = mockApiFetch.mock.calls[0]
    expect(url).toBe("/api/feedback")
    expect(options?.method).toBe("POST")
    const body = JSON.parse(options?.body as string)
    expect(body).toMatchObject({
      description: "It works great",
      attachment_claim_id: "00000000-0000-0000-0000-000000000001",
      sentry_event_id: null,
      current_url: expect.any(String),
    })

    await waitFor(() => expect(feedbackDialogStore.getState().isOpen).toBe(false))
  })

  test("submit button stays disabled with an empty description and no POST happens", async () => {
    render(<FeedbackDialog uploadUrl={null} />)
    openDialog()

    const submit = await screen.findByRole("button", { name: /submit/i })
    expect(submit).toBeDisabled()
    fireEvent.click(submit)
    expect(mockApiFetch).not.toHaveBeenCalled()
    expect(feedbackDialogStore.getState().isOpen).toBe(true)
  })

  test("rapid clicks de-dup to one request; on failure the dialog stays open and a retry succeeds", async () => {
    mockApiFetch.mockRejectedValueOnce(new ApiError(500, null))
    mockApiFetch.mockResolvedValueOnce({ success: true })

    render(<FeedbackDialog uploadUrl={null} />)
    openDialog()
    setEditorContent("Something broke")

    const submit = await screen.findByRole("button", { name: /submit/i })
    await waitFor(() => expect(submit).not.toBeDisabled())

    fireEvent.click(submit)
    fireEvent.click(submit)
    fireEvent.click(submit)
    fireEvent.click(submit)

    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(/request failed|wrong on our end|couldn't send/i)
    )
    expect(mockApiFetch).toHaveBeenCalledTimes(1)
    expect(feedbackDialogStore.getState().isOpen).toBe(true)
    expect(submit).not.toBeDisabled()

    fireEvent.click(submit)

    await waitFor(() => expect(mockApiFetch).toHaveBeenCalledTimes(2))
    await waitFor(() => expect(feedbackDialogStore.getState().isOpen).toBe(false))
  })

  test("dialog is rendered with a constrained width", () => {
    render(<FeedbackDialog uploadUrl={null} />)
    openDialog()
    const dialog = screen.getByTestId("feedback-dialog")
    expect(dialog.className).toContain("w-11/12")
    expect(dialog.className).toContain("max-w-xl")
  })
})
