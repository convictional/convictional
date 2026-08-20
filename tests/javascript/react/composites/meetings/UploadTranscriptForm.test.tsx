import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("~/react/shared/apiFetch", async () => {
  const actual = await vi.importActual<typeof import("~/react/shared/apiFetch")>("~/react/shared/apiFetch")
  return { ...actual, apiFetch: vi.fn() }
})
vi.mock("~/shared/flash", () => ({ showFlash: vi.fn() }))

import { apiFetch } from "~/react/shared/apiFetch"
import { UploadTranscriptForm } from "~/react/composites/meetings/UploadTranscriptForm"
import { showFlash } from "~/shared/flash"

import { makeMeeting } from "../../shared/meetingsFixtures"

const mockApiFetch = vi.mocked(apiFetch)

let onCreated = vi.fn()

function openForm() {
  const { container } = render(<UploadTranscriptForm onCreated={onCreated} />)
  fireEvent.click(screen.getByLabelText("Upload transcript"))
  return container.querySelector('input[type="file"]') as HTMLInputElement
}

async function chooseFile(input: HTMLInputElement, contents: string) {
  const file = new File([contents], "transcript.txt")
  // jsdom's File doesn't implement Blob.text(), which the component reads.
  Object.defineProperty(file, "text", { value: () => Promise.resolve(contents) })
  fireEvent.change(input, { target: { files: [file] } })
  // The transcript is read asynchronously; Create enables once it lands.
  await waitFor(() => expect((screen.getByText("Create") as HTMLButtonElement).disabled).toBe(false))
}

beforeEach(() => {
  mockApiFetch.mockReset()
  vi.mocked(showFlash).mockReset()
  onCreated = vi.fn()
})

describe("UploadTranscriptForm", () => {
  it("reads the chosen file and POSTs its text as a transcript-type meeting", async () => {
    const created = makeMeeting({ id: "new-meeting" })
    mockApiFetch.mockResolvedValue(created)

    const input = openForm()
    expect((screen.getByText("Create") as HTMLButtonElement).disabled).toBe(true)
    await chooseFile(input, "Alice: hello\nBob: hi")

    fireEvent.click(screen.getByText("Create"))

    await waitFor(() => expect(onCreated).toHaveBeenCalledWith(created))
    expect(mockApiFetch).toHaveBeenCalledWith("/api/meetings", {
      method: "POST",
      body: JSON.stringify({ type: "transcript", transcript: "Alice: hello\nBob: hi" }),
    })
    // The form closes back to the toolbar button after a successful create.
    expect(screen.queryByText("Create")).toBeNull()
  })

  it("flashes an error and stays open when the create fails", async () => {
    mockApiFetch.mockRejectedValue(new Error("boom"))

    const input = openForm()
    await chooseFile(input, "transcript text")
    fireEvent.click(screen.getByText("Create"))

    await waitFor(() => expect(showFlash).toHaveBeenCalledWith(expect.any(String), "error"))
    expect(onCreated).not.toHaveBeenCalled()
    expect(screen.getByText("Create")).toBeTruthy()
  })
})
