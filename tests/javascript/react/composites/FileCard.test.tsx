import { cleanup, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, test } from "vitest"

import { FileCard } from "~/react/composites/FileCard"

afterEach(cleanup)

describe("FileCard", () => {
  test("renders the filename, a type icon, a human-readable size, and a download link", () => {
    render(
      <FileCard
        fileName="budget.xlsx"
        contentType="application/vnd.ms-excel"
        byteSize={1536}
        downloadUrl="/chats/c1/attachments/a1/download"
      />
    )

    expect(screen.getByText("budget.xlsx")).toBeInTheDocument()
    expect(screen.getByText("description")).toBeInTheDocument()
    expect(screen.getByText("1.5 KB")).toBeInTheDocument()

    const link = screen.getByRole("link")
    expect(link.getAttribute("href")).toBe("/chats/c1/attachments/a1/download")
    expect(link.getAttribute("target")).toBe("_blank")
  })

  test("omits the size line when the byte size is unknown", () => {
    render(<FileCard fileName="note.txt" contentType="text/plain" byteSize={null} downloadUrl="/d" />)

    expect(screen.getByText("note.txt")).toBeInTheDocument()
    expect(screen.queryByText(/B$|KB|MB/)).not.toBeInTheDocument()
  })

  test.each([
    ["image/png", "image"],
    ["application/pdf", "picture_as_pdf"],
    ["video/mp4", "movie"],
    ["audio/mpeg", "audio_file"],
    ["text/csv", "description"],
    ["application/vnd.openxmlformats-officedocument.wordprocessingml.document", "description"],
    ["application/zip", "attach_file"],
    [null, "attach_file"],
  ])("maps content type %s to the %s icon", (contentType, icon) => {
    render(<FileCard fileName="f" contentType={contentType} byteSize={null} downloadUrl="/d" />)
    expect(screen.getByText(icon)).toBeInTheDocument()
  })

  test.each([
    [512, "512 B"],
    [1024, "1 KB"],
    [1536, "1.5 KB"],
    [1024 * 1024, "1 MB"],
    [5 * 1024 * 1024 * 1024, "5 GB"],
    // Just under a unit ceiling rounds up to 1024 of the smaller unit; it must carry
    // into the next unit ("1 MB"), never render as "1024 KB".
    [1024 * 1024 - 1, "1 MB"],
    [1024 * 1024 * 1024 - 1, "1 GB"],
  ])("formats %d bytes as %s", (byteSize, formatted) => {
    render(<FileCard fileName="f" contentType={null} byteSize={byteSize} downloadUrl="/d" />)
    expect(screen.getByText(formatted)).toBeInTheDocument()
  })
})
