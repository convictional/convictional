import { beforeEach, describe, expect, test, vi } from "vitest"

// Importing for side effects: the bridge registers a document-level
// `htmx:confirm` listener on module load. Tests dispatch the event below to
// drive that listener.
import "../../../../../app/javascript/react/composites/confirmationDialog/htmxBridge"
import { confirmationDialogStore } from "../../../../../app/javascript/react/composites/confirmationDialog/store"

interface FakeDetail {
  elt: HTMLElement
  question: string | null
  issueRequest: (skipConfirmation: boolean) => void
}

function dispatchHtmxConfirm(detail: FakeDetail) {
  const event = new CustomEvent("htmx:confirm", { detail, cancelable: true })
  document.dispatchEvent(event)
  return event
}

function makeElt(attrs: Record<string, string> = {}): HTMLElement {
  const el = document.createElement("button")
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v)
  return el
}

describe("htmxBridge", () => {
  beforeEach(() => {
    confirmationDialogStore.setState({ current: null })
  })

  test("ignores events without an hx-confirm question", () => {
    const issueRequest = vi.fn()
    const event = dispatchHtmxConfirm({ elt: makeElt(), question: null, issueRequest })
    expect(event.defaultPrevented).toBe(false)
    expect(confirmationDialogStore.getState().current).toBeNull()
  })

  test("intercepts hx-confirm events and opens the dialog with the question", () => {
    const issueRequest = vi.fn()
    const event = dispatchHtmxConfirm({
      elt: makeElt(),
      question: "Delete this post?",
      issueRequest,
    })
    expect(event.defaultPrevented).toBe(true)
    expect(confirmationDialogStore.getState().current?.message).toBe("Delete this post?")
  })

  test("resolving the dialog issues the htmx request with skipConfirmation=true", () => {
    const issueRequest = vi.fn()
    dispatchHtmxConfirm({
      elt: makeElt(),
      question: "Delete?",
      issueRequest,
    })

    confirmationDialogStore.getState().resolve()
    expect(issueRequest).toHaveBeenCalledTimes(1)
    expect(issueRequest).toHaveBeenCalledWith(true)
  })

  test("rejecting the dialog does not issue the htmx request", () => {
    const issueRequest = vi.fn()
    dispatchHtmxConfirm({
      elt: makeElt(),
      question: "Delete?",
      issueRequest,
    })

    confirmationDialogStore.getState().reject()
    expect(issueRequest).not.toHaveBeenCalled()
  })

  test("data-confirm-label / data-confirm-cancel-label / data-confirm-title are forwarded", () => {
    dispatchHtmxConfirm({
      elt: makeElt({
        "data-confirm-label": "Yes",
        "data-confirm-cancel-label": "No",
        "data-confirm-title": "Hold on",
      }),
      question: "Proceed?",
      issueRequest: vi.fn(),
    })
    expect(confirmationDialogStore.getState().current).toMatchObject({
      confirmLabel: "Yes",
      cancelLabel: "No",
      title: "Hold on",
    })
  })
})
