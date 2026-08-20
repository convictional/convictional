import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

import { CopyTranscriptButton } from "~/react/features/meetingShow/components/CopyTranscriptButton"
import type { MeetingDetail, TranscriptLine } from "~/react/features/meetingShow/types"
import { formatDateTime } from "~/react/ui/DateTime"

const writeText = vi.fn().mockResolvedValue(undefined)

const SCHEDULED_AT = "2026-06-10T14:30:00Z"

const meeting = { title: "Standup", scheduled_at: SCHEDULED_AT } as unknown as MeetingDetail
const lines = [
  { line_number: 1, speaker: "Alice", content: "Hello", start_time: 0 },
  { line_number: 2, speaker: null, content: "World", start_time: 5 },
] as unknown as TranscriptLine[]

beforeEach(() => {
  writeText.mockClear()
  Object.assign(navigator, { clipboard: { writeText } })
})

afterEach(cleanup)

describe("CopyTranscriptButton", () => {
  test("copies a human-readable, viewer-local date rather than the raw ISO string", () => {
    render(<CopyTranscriptButton meeting={meeting} lines={lines} />)
    fireEvent.click(screen.getByRole("button", { name: "Copy transcript" }))

    const copied = writeText.mock.calls[0][0] as string
    // Computed with the same helper, so the assertion is timezone-independent.
    expect(copied).toContain(`*${formatDateTime(SCHEDULED_AT, "short_month_day_year_time")}*`)
    expect(copied).not.toContain(SCHEDULED_AT)
  })

  test("renders the title heading and transcript body, with and without a speaker", () => {
    render(<CopyTranscriptButton meeting={meeting} lines={lines} />)
    fireEvent.click(screen.getByRole("button", { name: "Copy transcript" }))

    const copied = writeText.mock.calls[0][0] as string
    expect(copied).toContain("# Standup")
    expect(copied).toContain("Alice: Hello")
    expect(copied).toContain("\nWorld\n")
  })
})
