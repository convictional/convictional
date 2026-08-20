import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, test, vi } from "vitest"

vi.mock("~/react/shared/apiFetch", async () => {
  const actual = await vi.importActual<typeof import("~/react/shared/apiFetch")>("~/react/shared/apiFetch")
  return { ...actual, apiFetch: vi.fn() }
})

import { apiFetch } from "~/react/shared/apiFetch"

import { TitleEditor } from "~/react/features/meetingShow/components/TitleEditor"

const mockedFetch = vi.mocked(apiFetch)

function setup(title: string | null = "Original") {
  const onLocalUpdate = vi.fn()
  const onServerUpdate = vi.fn()
  render(<TitleEditor meetingId="m1" title={title} onLocalUpdate={onLocalUpdate} onServerUpdate={onServerUpdate} />)
  const heading = screen.getByText(title ?? "Untitled meeting")
  fireEvent.click(screen.getByLabelText("Edit title"))
  return { heading, onLocalUpdate, onServerUpdate }
}

afterEach(() => {
  cleanup()
  mockedFetch.mockReset()
})

describe("TitleEditor", () => {
  test("does not save an empty/whitespace title — it blocks rather than persisting null or ''", () => {
    mockedFetch.mockResolvedValue({} as never)
    const { heading, onLocalUpdate } = setup("Original")

    heading.innerText = "   "
    fireEvent.blur(heading)

    expect(mockedFetch).not.toHaveBeenCalled()
    expect(onLocalUpdate).not.toHaveBeenCalled()
  })

  test("saves a trimmed non-empty title via PATCH", () => {
    mockedFetch.mockResolvedValue({} as never)
    const { heading, onLocalUpdate } = setup("Original")

    heading.innerText = "  New Title  "
    fireEvent.blur(heading)

    expect(onLocalUpdate).toHaveBeenCalledWith("New Title")
    expect(mockedFetch).toHaveBeenCalledWith(
      "/api/meetings/m1",
      expect.objectContaining({ method: "PATCH", body: JSON.stringify({ title: "New Title" }) })
    )
  })

  test("does not re-PATCH when the title is unchanged", () => {
    mockedFetch.mockResolvedValue({} as never)
    const { heading } = setup("Original")

    heading.innerText = "Original"
    fireEvent.blur(heading)

    expect(mockedFetch).not.toHaveBeenCalled()
  })
})
