import { renderHook } from "@testing-library/react"
import { useRef, type RefObject } from "react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { useKeyboardSend } from "~/react/composites/emailComposer/hooks/useKeyboardSend"

interface HookOptions {
  canSend?: boolean
  sending?: boolean
  onSend?: () => void
  container?: HTMLElement | null
}

function renderUseKeyboardSend(options: HookOptions = {}) {
  const onSend = options.onSend ?? vi.fn()
  const container = options.container === undefined ? document.body : options.container
  const { rerender, unmount } = renderHook(
    ({ canSend, sending }: { canSend: boolean; sending: boolean }) => {
      const ref = useRef<HTMLElement | null>(container)
      useKeyboardSend({
        canSend,
        sending,
        onSend,
        containerRef: ref as RefObject<HTMLElement | null>,
      })
    },
    { initialProps: { canSend: options.canSend ?? true, sending: options.sending ?? false } }
  )
  return { onSend, rerender, unmount }
}

function dispatchCmdEnter(target: EventTarget) {
  const event = new KeyboardEvent("keydown", {
    key: "Enter",
    metaKey: true,
    bubbles: true,
    cancelable: true,
  })
  target.dispatchEvent(event)
  return event
}

describe("useKeyboardSend", () => {
  afterEach(() => {
    document.body.innerHTML = ""
  })

  it("sends on Cmd+Enter when the event originates inside the container", () => {
    const inside = document.createElement("div")
    document.body.appendChild(inside)
    const { onSend } = renderUseKeyboardSend({ container: document.body })

    const event = dispatchCmdEnter(inside)

    expect(onSend).toHaveBeenCalledTimes(1)
    expect(event.defaultPrevented).toBe(true)
  })

  it("sends on Ctrl+Enter as well", () => {
    const inside = document.createElement("div")
    document.body.appendChild(inside)
    const { onSend } = renderUseKeyboardSend({ container: document.body })

    inside.dispatchEvent(
      new KeyboardEvent("keydown", {
        key: "Enter",
        ctrlKey: true,
        bubbles: true,
        cancelable: true,
      })
    )

    expect(onSend).toHaveBeenCalledTimes(1)
  })

  it("ignores Cmd+Enter from a sibling editor outside the container (the regression)", () => {
    const composer = document.createElement("div")
    const otherEditor = document.createElement("div")
    document.body.append(composer, otherEditor)
    const { onSend } = renderUseKeyboardSend({ container: composer })

    dispatchCmdEnter(otherEditor)

    expect(onSend).not.toHaveBeenCalled()
  })

  it("ignores plain Enter inside the container", () => {
    const inside = document.createElement("div")
    document.body.appendChild(inside)
    const { onSend } = renderUseKeyboardSend({ container: document.body })

    inside.dispatchEvent(
      new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true })
    )

    expect(onSend).not.toHaveBeenCalled()
  })

  it("does not send when canSend is false", () => {
    const inside = document.createElement("div")
    document.body.appendChild(inside)
    const { onSend } = renderUseKeyboardSend({ container: document.body, canSend: false })

    dispatchCmdEnter(inside)

    expect(onSend).not.toHaveBeenCalled()
  })

  it("does not send when already sending", () => {
    const inside = document.createElement("div")
    document.body.appendChild(inside)
    const { onSend } = renderUseKeyboardSend({ container: document.body, sending: true })

    dispatchCmdEnter(inside)

    expect(onSend).not.toHaveBeenCalled()
  })

  it("does not send when the container ref has not attached yet", () => {
    const inside = document.createElement("div")
    document.body.appendChild(inside)
    const { onSend } = renderUseKeyboardSend({ container: null })

    dispatchCmdEnter(inside)

    expect(onSend).not.toHaveBeenCalled()
  })

  it("stops listening after unmount", () => {
    const inside = document.createElement("div")
    document.body.appendChild(inside)
    const { onSend, unmount } = renderUseKeyboardSend({ container: document.body })

    unmount()
    dispatchCmdEnter(inside)

    expect(onSend).not.toHaveBeenCalled()
  })
})
