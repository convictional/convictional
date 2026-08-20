import { act, cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, test, vi } from "vitest"

import { SubmitButton } from "~/react/ui/SubmitButton"

afterEach(cleanup)

function renderInForm(ui: React.ReactNode, onSubmit?: (e: React.FormEvent) => void) {
  return render(
    <form
      onSubmit={e => {
        e.preventDefault()
        onSubmit?.(e)
      }}
    >
      <input name="title" required defaultValue="filled" />
      {ui}
    </form>
  )
}

describe("SubmitButton", () => {
  test("renders children and applies default btn-primary class", () => {
    renderInForm(<SubmitButton>Save</SubmitButton>)

    const button = screen.getByRole("button", { name: "Save" })
    expect(button).toHaveAttribute("type", "submit")
    expect(button.className).toContain("btn btn-primary")
  })

  test("applies custom className and forwards extra attributes", () => {
    renderInForm(
      <SubmitButton className="btn btn-square" data-hotkey="c" title="press c">
        Go
      </SubmitButton>
    )

    const button = screen.getByRole("button", { name: "Go" })
    expect(button.className).toContain("btn btn-square")
    expect(button).toHaveAttribute("data-hotkey", "c")
    expect(button).toHaveAttribute("title", "press c")
  })

  test("disables itself when the form is invalid", () => {
    render(
      <form>
        <input name="title" required defaultValue="" />
        <SubmitButton>Save</SubmitButton>
      </form>
    )

    const button = screen.getByRole("button", { name: "Save" })
    expect(button).toBeDisabled()
    expect(button.className).toContain("btn-disabled")
    expect(button.className).toContain("cursor-not-allowed")
  })

  test("becomes enabled when the form becomes valid", () => {
    render(
      <form>
        <input name="title" required defaultValue="" />
        <SubmitButton>Save</SubmitButton>
      </form>
    )

    const button = screen.getByRole("button", { name: "Save" })
    expect(button).toBeDisabled()

    const input = screen.getByRole("textbox")
    fireEvent.input(input, { target: { value: "filled" } })

    expect(button).not.toBeDisabled()
  })

  test("submits the form when clicked and the form is valid", () => {
    const onSubmit = vi.fn()
    renderInForm(<SubmitButton>Save</SubmitButton>, onSubmit)

    fireEvent.click(screen.getByRole("button", { name: "Save" }))

    expect(onSubmit).toHaveBeenCalledTimes(1)
  })

  test("disables and shows spinner class after 250ms while submitting", () => {
    vi.useFakeTimers()
    try {
      const { rerender } = renderInForm(<SubmitButton>Save</SubmitButton>)

      const button = screen.getByRole("button", { name: "Save" })
      expect(button).not.toBeDisabled()
      expect(button.className).not.toContain("loading-spinner")

      rerender(
        <form>
          <input name="title" required defaultValue="filled" />
          <SubmitButton submitting>Save</SubmitButton>
        </form>
      )

      expect(button).toBeDisabled()
      expect(button.className).not.toContain("loading-spinner")

      act(() => {
        vi.advanceTimersByTime(249)
      })
      expect(button.className).not.toContain("loading-spinner")

      act(() => {
        vi.advanceTimersByTime(1)
      })
      expect(button.className).toContain("loading loading-sm loading-spinner")
    } finally {
      vi.useRealTimers()
    }
  })

  test("clears spinner when submitting flips back to false", () => {
    vi.useFakeTimers()
    try {
      const { rerender } = render(
        <form>
          <input name="title" required defaultValue="filled" />
          <SubmitButton submitting>Save</SubmitButton>
        </form>
      )

      const button = screen.getByRole("button", { name: "Save" })
      act(() => {
        vi.advanceTimersByTime(250)
      })
      expect(button.className).toContain("loading-spinner")

      rerender(
        <form>
          <input name="title" required defaultValue="filled" />
          <SubmitButton submitting={false}>Save</SubmitButton>
        </form>
      )

      expect(button.className).not.toContain("loading-spinner")
      expect(button).not.toBeDisabled()
    } finally {
      vi.useRealTimers()
    }
  })

  test("respects a parent-provided disabled prop", () => {
    renderInForm(<SubmitButton disabled>Save</SubmitButton>)

    const button = screen.getByRole("button", { name: "Save" })
    expect(button).toBeDisabled()
    expect(button.className).toContain("btn-disabled")
  })
})
