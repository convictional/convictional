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
import { QuickLinkForm } from "../../../../../../app/javascript/react/features/commandPalette/active/QuickLinkForm"

const mockApiFetch = vi.mocked(apiFetch)

beforeEach(() => {
  mockApiFetch.mockReset()
})

afterEach(cleanup)

describe("QuickLinkForm", () => {
  test("create flow posts to /api/quick_links", async () => {
    mockApiFetch.mockResolvedValue({
      id: "1",
      label: "Inbox",
      url: "https://example.com",
      open_in_new_tab: true,
    })
    const onSaved = vi.fn()

    render(<QuickLinkForm quickLinkId={null} onSaved={onSaved} onDeleted={() => {}} />)

    fireEvent.change(screen.getByPlaceholderText("label"), { target: { value: "Inbox" } })
    fireEvent.change(screen.getByPlaceholderText("https://example.com"), {
      target: { value: "https://example.com" },
    })
    fireEvent.click(screen.getByText("Create quick link"))

    await waitFor(() => expect(onSaved).toHaveBeenCalled())
    expect(mockApiFetch).toHaveBeenCalledWith(
      "/api/quick_links",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ label: "Inbox", url: "https://example.com", open_in_new_tab: true }),
      })
    )
  })

  test("422 shows inline error and keeps form open", async () => {
    mockApiFetch.mockRejectedValue(new ApiError(422))
    const onSaved = vi.fn()

    render(<QuickLinkForm quickLinkId={null} onSaved={onSaved} onDeleted={() => {}} />)

    fireEvent.change(screen.getByPlaceholderText("label"), { target: { value: "Bad" } })
    fireEvent.change(screen.getByPlaceholderText("https://example.com"), { target: { value: "not-a-url" } })
    fireEvent.click(screen.getByText("Create quick link"))

    await screen.findByText(/HTTP or HTTPS URL/)
    expect(onSaved).not.toHaveBeenCalled()
  })

  test("edit flow loads existing quick link", async () => {
    mockApiFetch.mockResolvedValueOnce({
      id: "1",
      label: "Inbox",
      url: "https://example.com",
      open_in_new_tab: false,
    })

    render(<QuickLinkForm quickLinkId="1" onSaved={() => {}} onDeleted={() => {}} />)

    await screen.findByDisplayValue("Inbox")
    expect(screen.getByDisplayValue("https://example.com")).toBeTruthy()
    expect(mockApiFetch).toHaveBeenCalledWith("/api/quick_links/1", expect.any(Object))
  })
})
