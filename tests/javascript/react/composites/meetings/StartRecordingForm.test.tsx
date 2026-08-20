import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("~/react/shared/apiFetch", async () => {
  const actual = await vi.importActual<typeof import("~/react/shared/apiFetch")>("~/react/shared/apiFetch")
  return { ...actual, apiFetch: vi.fn() }
})
vi.mock("~/shared/flash", () => ({ showFlash: vi.fn() }))

import { apiFetch } from "~/react/shared/apiFetch"
import { StartRecordingForm } from "~/react/composites/meetings/StartRecordingForm"
import { showFlash } from "~/shared/flash"

import { makeMeeting } from "../../shared/meetingsFixtures"

const mockApiFetch = vi.mocked(apiFetch)

beforeEach(() => {
  mockApiFetch.mockReset()
  vi.mocked(showFlash).mockReset()
})

function openForm() {
  render(<StartRecordingForm onCreated={onCreated} />)
  fireEvent.click(screen.getByLabelText("Start recording from link"))
}

let onCreated = vi.fn()

describe("StartRecordingForm", () => {
  beforeEach(() => {
    onCreated = vi.fn()
  })

  it("POSTs the trimmed URL as a url-type meeting and hands the result to onCreated", async () => {
    const created = makeMeeting({ id: "new-meeting" })
    mockApiFetch.mockResolvedValue(created)
    openForm()

    fireEvent.change(screen.getByPlaceholderText("Meeting URL"), {
      target: { value: "  https://meet.example/abc  " },
    })
    fireEvent.click(screen.getByText("Record"))

    await waitFor(() => expect(onCreated).toHaveBeenCalledWith(created))
    expect(mockApiFetch).toHaveBeenCalledWith("/api/meetings", {
      method: "POST",
      body: JSON.stringify({ type: "url", conferencing_url: "https://meet.example/abc" }),
    })
    // The form closes back to the toolbar button after a successful create.
    expect(screen.queryByPlaceholderText("Meeting URL")).toBeNull()
  })

  it("disables submission until a URL is entered", () => {
    openForm()
    expect(screen.getByText("Record")).toHaveProperty("disabled", true)

    fireEvent.change(screen.getByPlaceholderText("Meeting URL"), { target: { value: "https://x" } })
    expect(screen.getByText("Record")).toHaveProperty("disabled", false)
  })

  it("flashes an error and stays open when the create fails", async () => {
    mockApiFetch.mockRejectedValue(new Error("boom"))
    openForm()

    fireEvent.change(screen.getByPlaceholderText("Meeting URL"), { target: { value: "https://x" } })
    fireEvent.click(screen.getByText("Record"))

    await waitFor(() => expect(showFlash).toHaveBeenCalledWith(expect.any(String), "error"))
    expect(onCreated).not.toHaveBeenCalled()
    expect(screen.getByPlaceholderText("Meeting URL")).toBeTruthy()
  })
})
