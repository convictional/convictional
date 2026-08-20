import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

vi.mock("../../../../../../app/javascript/react/shared/apiFetch", () => {
  class ApiError extends Error {
    status: number
    body: null
    constructor(status: number) {
      super(`Request failed with status ${status}`)
      this.status = status
      this.body = null
    }
  }
  return {
    apiFetch: vi.fn(),
    errorMessage: (err: unknown, fallback: string) =>
      err instanceof ApiError ? err.message : fallback,
    ApiError,
  }
})

import { apiFetch, ApiError } from "../../../../../../app/javascript/react/shared/apiFetch"
import { ResearchForm } from "../../../../../../app/javascript/react/features/commandPalette/active/ResearchForm"

const mockApiFetch = vi.mocked(apiFetch)

beforeEach(() => {
  mockApiFetch.mockReset()
})

afterEach(cleanup)

describe("ResearchForm", () => {
  test("submit posts body and calls onSuccess", async () => {
    mockApiFetch.mockResolvedValue({ id: "r1", body: "test", title: null, created_at: "" })
    const onSuccess = vi.fn()

    render(<ResearchForm onSuccess={onSuccess} />)

    fireEvent.change(screen.getByPlaceholderText("What would you like to research?"), {
      target: { value: "what's new" },
    })
    fireEvent.click(screen.getByLabelText("Submit"))

    await waitFor(() => expect(onSuccess).toHaveBeenCalled())
    expect(mockApiFetch).toHaveBeenCalledWith(
      "/api/research_questions",
      expect.objectContaining({ method: "POST", body: JSON.stringify({ body: "what's new" }) })
    )
  })

  test("suggestion chip pre-fills the textarea", () => {
    render(<ResearchForm onSuccess={() => {}} />)

    fireEvent.click(screen.getByText("Daily to-do list"))
    expect(screen.getByPlaceholderText("What would you like to research?")).toHaveValue(
      "Generate my to-do list based on the past day."
    )
  })

  test("⌘+Enter submits", async () => {
    mockApiFetch.mockResolvedValue({ id: "r1", body: "test", title: null, created_at: "" })
    const onSuccess = vi.fn()

    render(<ResearchForm onSuccess={onSuccess} />)

    const textarea = screen.getByPlaceholderText("What would you like to research?")
    fireEvent.change(textarea, { target: { value: "test" } })
    fireEvent.keyDown(textarea, { key: "Enter", metaKey: true })

    await waitFor(() => expect(onSuccess).toHaveBeenCalled())
  })

  test("API error keeps form open with message", async () => {
    mockApiFetch.mockRejectedValue(new ApiError(422))
    const onSuccess = vi.fn()

    render(<ResearchForm onSuccess={onSuccess} />)

    fireEvent.change(screen.getByPlaceholderText("What would you like to research?"), {
      target: { value: "  " },
    })
    fireEvent.change(screen.getByPlaceholderText("What would you like to research?"), {
      target: { value: "test" },
    })
    fireEvent.click(screen.getByLabelText("Submit"))

    await screen.findByText("Please enter a question.")
    expect(onSuccess).not.toHaveBeenCalled()
  })
})
