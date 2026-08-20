import "@testing-library/jest-dom/vitest"
import { cleanup } from "@testing-library/react"
import { afterEach } from "vitest"

// @testing-library/react's auto-cleanup only runs when globals are exposed
// (vitest is configured without globals: true). Wire it up here so tests that
// render multiple components in a row don't leak DOM into each other.
afterEach(() => {
  cleanup()
})

// jsdom doesn't implement scrollIntoView
Element.prototype.scrollIntoView = () => {}

// jsdom doesn't implement ResizeObserver; stub with a no-op so components that
// observe layout (e.g. iframe auto-sizing in EmailMessageBody) don't crash.
if (typeof globalThis.ResizeObserver === "undefined") {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver
}

// jsdom doesn't implement scrollTo; tests that use it rely on spying via
// vi.spyOn(window, "scrollTo") which inherits from this no-op.
window.scrollTo = (() => {}) as typeof window.scrollTo

// jsdom doesn't implement <dialog>'s showModal/close — stub to keep behavior reachable in tests.
if (!HTMLDialogElement.prototype.showModal) {
  HTMLDialogElement.prototype.showModal = function (this: HTMLDialogElement) {
    this.setAttribute("open", "")
  }
  HTMLDialogElement.prototype.close = function (this: HTMLDialogElement) {
    this.removeAttribute("open")
  }
}

// jsdom's matchMedia stub returns matches=false for every query, which breaks
// components that branch on viewport width. Evaluate min/max-width queries
// against the actual window.innerWidth (jsdom defaults to 1024×768).
Object.defineProperty(window, "matchMedia", {
  writable: true,
  configurable: true,
  value: (query: string) => {
    const minWidth = /\(min-width:\s*(\d+)px\)/.exec(query)
    const maxWidth = /\(max-width:\s*(\d+)px\)/.exec(query)
    let matches = false
    if (minWidth) matches = window.innerWidth >= Number(minWidth[1])
    else if (maxWidth) matches = window.innerWidth <= Number(maxWidth[1])
    return {
      matches,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }
  },
})
