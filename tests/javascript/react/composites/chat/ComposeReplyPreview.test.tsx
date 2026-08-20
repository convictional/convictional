import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, test, vi } from "vitest"

import { ComposeReplyPreview } from "~/react/composites/chat/ComposeReplyPreview"

afterEach(() => {
  cleanup()
})

describe("ComposeReplyPreview", () => {
  test("renders author name and content preview", () => {
    render(<ComposeReplyPreview replyTo={{ id: "m1", user_name: "Alice", content_preview: "hey there", is_deleted: false }} onClear={() => {}} />)
    expect(screen.getByText("Alice")).toBeTruthy()
    expect(screen.getByText("hey there")).toBeTruthy()
  })

  test("calls onClear when close button is clicked", () => {
    const onClear = vi.fn()
    render(<ComposeReplyPreview replyTo={{ id: "m1", user_name: "Alice", content_preview: "hey", is_deleted: false }} onClear={onClear} />)
    fireEvent.click(screen.getByLabelText("Cancel reply"))
    expect(onClear).toHaveBeenCalledOnce()
  })

  test("renders content_preview as-is (server pre-formats it)", () => {
    render(
      <ComposeReplyPreview
        replyTo={{ id: "m1", user_name: "Alice", content_preview: "bold link", is_deleted: false }}
        onClear={() => {}}
      />
    )
    expect(screen.getByText("bold link")).toBeTruthy()
  })
})
