import { act, cleanup, fireEvent, render, screen } from "@testing-library/react"
import { useState } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { EmailContactsTypeahead } from "~/react/composites/EmailContactsTypeahead"

const apiFetchMock = vi.fn()

vi.mock("~/react/shared/apiFetch", () => ({
  apiFetch: (url: string, options?: RequestInit) => apiFetchMock(url, options),
}))

interface HarnessProps {
  initialValue?: string[]
  useCondensedDisplay?: boolean
}

function Harness({ initialValue = [], useCondensedDisplay }: HarnessProps) {
  const [value, setValue] = useState<string[]>(initialValue)
  return (
    <>
      <EmailContactsTypeahead
        value={value}
        onChange={setValue}
        placeholder="Recipients"
        testId="recipients-input"
        useCondensedDisplay={useCondensedDisplay}
      />
      <div data-testid="value-snapshot">{JSON.stringify(value)}</div>
    </>
  )
}

function getInput(): HTMLInputElement {
  return screen.getByTestId("recipients-input") as HTMLInputElement
}

function readSnapshot(): string[] {
  return JSON.parse(screen.getByTestId("value-snapshot").textContent ?? "[]")
}

describe("EmailContactsTypeahead", () => {
  beforeEach(() => {
    vi.useFakeTimers()
    apiFetchMock.mockReset()
  })

  afterEach(() => {
    cleanup()
    vi.useRealTimers()
  })

  it("renders initial chips from value", () => {
    render(<Harness initialValue={["Alice <alice@example.com>", "bob@example.com"]} />)
    expect(screen.getByText("Alice (example.com)")).toBeInTheDocument()
    expect(screen.getByText("bob (example.com)")).toBeInTheDocument()
  })

  it("debounces input and fetches contacts once", async () => {
    apiFetchMock.mockResolvedValue({ contacts: [] })
    render(<Harness />)
    const input = getInput()

    fireEvent.change(input, { target: { value: "a" } })
    fireEvent.change(input, { target: { value: "al" } })
    fireEvent.change(input, { target: { value: "ali" } })

    expect(apiFetchMock).not.toHaveBeenCalled()

    await act(async () => {
      vi.advanceTimersByTime(300)
    })

    expect(apiFetchMock).toHaveBeenCalledTimes(1)
    expect(apiFetchMock.mock.calls[0][0]).toContain("query=ali")
  })

  it("selecting a dropdown result calls onChange with new array", async () => {
    apiFetchMock.mockResolvedValue({
      contacts: [{ id: "1", email: "alice@example.com", name: "Alice", photo_url: null }],
    })
    render(<Harness />)
    const input = getInput()

    fireEvent.change(input, { target: { value: "al" } })
    await act(async () => {
      vi.advanceTimersByTime(300)
    })
    await act(async () => {
      await Promise.resolve()
    })

    const option = screen.getByRole("option", { name: /alice@example.com/ })
    fireEvent.click(option)

    expect(readSnapshot()).toEqual(["Alice <alice@example.com>"])
  })

  it("removing a chip calls onChange without it", () => {
    render(<Harness initialValue={["alice@example.com", "bob@example.com"]} />)
    const removeButtons = screen.getAllByRole("button", { name: /^Remove / })
    fireEvent.click(removeButtons[0])
    expect(readSnapshot()).toEqual(["bob <bob@example.com>"])
  })

  it("Backspace on empty input removes the last chip", () => {
    render(<Harness initialValue={["alice@example.com", "bob@example.com"]} />)
    const input = getInput()
    fireEvent.keyDown(input, { key: "Backspace" })
    expect(readSnapshot()).toEqual(["alice <alice@example.com>"])
  })

  it("pasting a comma-separated list adds all addresses", () => {
    render(<Harness />)
    const input = getInput()

    fireEvent.paste(input, {
      clipboardData: { getData: () => "alice@x.com, bob@y.com" },
    })

    expect(readSnapshot()).toEqual(["alice <alice@x.com>", "bob <bob@y.com>"])
  })

  it("invalid email on blur is rejected", async () => {
    render(<Harness />)
    const input = getInput()
    fireEvent.change(input, { target: { value: "not-an-email" } })
    fireEvent.blur(input)

    await act(async () => {
      vi.advanceTimersByTime(150)
    })

    expect(readSnapshot()).toEqual([])
  })

  it("clicking a dropdown option wins over the blur-commit timer", async () => {
    apiFetchMock.mockResolvedValue({
      contacts: [{ id: "1", email: "alice@example.com", name: "Alice", photo_url: null }],
    })
    render(<Harness />)
    const input = getInput()

    fireEvent.change(input, { target: { value: "al" } })
    await act(async () => {
      vi.advanceTimersByTime(300)
    })
    await act(async () => {
      await Promise.resolve()
    })

    const option = screen.getByRole("option", { name: /alice@example.com/ })
    // mousedown on the dropdown calls preventDefault, which stops the input
    // from losing focus in a real browser, so handleBlur never fires. The
    // click then lands on the still-open dropdown and commits the contact
    // (not the typed "al"). Validates the preventDefault wiring.
    const mouseDownEvent = fireEvent.mouseDown(option)
    expect(mouseDownEvent).toBe(false)
    fireEvent.click(option)

    expect(readSnapshot()).toEqual(["Alice <alice@example.com>"])
  })

  it("Enter on typed valid email commits a chip when no dropdown is open", () => {
    render(<Harness />)
    const input = getInput()
    fireEvent.change(input, { target: { value: "carol@example.com" } })
    fireEvent.keyDown(input, { key: "Enter" })
    expect(readSnapshot()).toEqual(["carol <carol@example.com>"])
  })

  it("does not add duplicates by email (case-insensitive)", () => {
    render(<Harness initialValue={["Alice <alice@example.com>"]} />)
    const input = getInput()
    fireEvent.change(input, { target: { value: "ALICE@example.com" } })
    fireEvent.keyDown(input, { key: "Enter" })
    expect(readSnapshot()).toEqual(["Alice <alice@example.com>"])
  })

  it("ArrowDown highlights next contact and Enter commits the highlighted one", async () => {
    apiFetchMock.mockResolvedValue({
      contacts: [
        { id: "1", email: "alice@example.com", name: "Alice", photo_url: null },
        { id: "2", email: "bob@example.com", name: "Bob", photo_url: null },
      ],
    })
    render(<Harness />)
    const input = getInput()

    fireEvent.change(input, { target: { value: "al" } })
    await act(async () => {
      vi.advanceTimersByTime(300)
    })
    await act(async () => {
      await Promise.resolve()
    })

    fireEvent.keyDown(input, { key: "ArrowDown" })
    fireEvent.keyDown(input, { key: "Enter" })

    expect(readSnapshot()).toEqual(["Bob <bob@example.com>"])
  })

  it("Tab on valid typed email commits and consumes; Tab on empty input does not", () => {
    render(<Harness />)
    const input = getInput()

    fireEvent.change(input, { target: { value: "carol@example.com" } })
    const committedTab = fireEvent.keyDown(input, { key: "Tab" })
    expect(committedTab).toBe(false)
    expect(readSnapshot()).toEqual(["carol <carol@example.com>"])

    const emptyTab = fireEvent.keyDown(input, { key: "Tab" })
    expect(emptyTab).toBe(true)
  })

  it("Escape closes the dropdown without committing", async () => {
    apiFetchMock.mockResolvedValue({
      contacts: [{ id: "1", email: "alice@example.com", name: "Alice", photo_url: null }],
    })
    render(<Harness />)
    const input = getInput()

    fireEvent.change(input, { target: { value: "al" } })
    await act(async () => {
      vi.advanceTimersByTime(300)
    })
    await act(async () => {
      await Promise.resolve()
    })

    expect(screen.queryByRole("listbox")).toBeInTheDocument()

    fireEvent.keyDown(input, { key: "Escape" })

    expect(screen.queryByRole("listbox")).not.toBeInTheDocument()
    expect(readSnapshot()).toEqual([])
  })
})
