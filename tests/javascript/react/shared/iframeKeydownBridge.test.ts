import { afterEach, describe, expect, it } from "vitest"

import { bridgeIframeKeydown } from "~/react/shared/iframeKeydownBridge"

// jsdom does not parse an iframe srcdoc into an about:srcdoc document, so the
// bridge can't be exercised through a real iframe here — these cases drive the
// helper directly with two hand-built documents.
describe("bridgeIframeKeydown", () => {
  const cleanups: Array<() => void> = []

  afterEach(() => {
    while (cleanups.length) cleanups.pop()?.()
  })

  // A fresh source document plus a spy on the parent's keydowns, both torn down
  // after the test.
  function setup() {
    const source = document.implementation.createHTMLDocument()
    const received: KeyboardEvent[] = []
    const listener = (e: Event) => received.push(e as KeyboardEvent)
    document.addEventListener("keydown", listener)
    cleanups.push(() => document.removeEventListener("keydown", listener))
    return { source, received }
  }

  it("forwards keydowns with modifiers to a body element on the target document", () => {
    const { source, received } = setup()
    cleanups.push(bridgeIframeKeydown(source, document))

    source.body.dispatchEvent(new KeyboardEvent("keydown", { key: "r", bubbles: true }))
    expect(received).toHaveLength(1)
    expect(received[0].key).toBe("r")

    source.body.dispatchEvent(
      new KeyboardEvent("keydown", { key: "a", shiftKey: true, metaKey: true, bubbles: true })
    )
    expect(received).toHaveLength(2)
    expect(received[1].shiftKey).toBe(true)
    expect(received[1].metaKey).toBe(true)

    // The forwarded event bubbles from body, so its target is the body Element
    // (with .matches), never the document itself.
    const target = received[1].target as Element
    expect(typeof target.matches).toBe("function")
    expect(received[1].target).not.toBe(document)
  })

  it("stops forwarding after cleanup", () => {
    const { source, received } = setup()

    const cleanup = bridgeIframeKeydown(source, document)
    source.body.dispatchEvent(new KeyboardEvent("keydown", { key: "r", bubbles: true }))
    expect(received).toHaveLength(1)

    cleanup()
    source.body.dispatchEvent(new KeyboardEvent("keydown", { key: "r", bubbles: true }))
    expect(received).toHaveLength(1)
  })

  it("does not forward a defaultPrevented source event", () => {
    const { source, received } = setup()
    // Registered before the bridge so it runs first and cancels the event.
    source.addEventListener("keydown", e => e.preventDefault())
    cleanups.push(bridgeIframeKeydown(source, document))

    source.body.dispatchEvent(
      new KeyboardEvent("keydown", { key: "r", bubbles: true, cancelable: true })
    )
    expect(received).toHaveLength(0)
  })
})
