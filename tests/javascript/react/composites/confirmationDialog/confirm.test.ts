import { beforeEach, describe, expect, test } from "vitest"

import { confirm } from "../../../../../app/javascript/react/composites/confirmationDialog/confirm"
import { confirmationDialogStore } from "../../../../../app/javascript/react/composites/confirmationDialog/store"

describe("confirm()", () => {
  beforeEach(() => {
    confirmationDialogStore.setState({ current: null })
  })

  test("resolves true when the store fires resolve()", async () => {
    const promise = confirm({ message: "Continue?" })
    expect(confirmationDialogStore.getState().current?.message).toBe("Continue?")

    confirmationDialogStore.getState().resolve()

    await expect(promise).resolves.toBe(true)
    expect(confirmationDialogStore.getState().current).toBeNull()
  })

  test("resolves false when the store fires reject()", async () => {
    const promise = confirm({ message: "Continue?" })
    confirmationDialogStore.getState().reject()
    await expect(promise).resolves.toBe(false)
  })

  test("forwards title and labels to the store", () => {
    confirm({
      message: "Delete?",
      title: "Hold on",
      confirmLabel: "Do it",
      cancelLabel: "Nope",
    })
    const current = confirmationDialogStore.getState().current
    expect(current).toMatchObject({
      message: "Delete?",
      title: "Hold on",
      confirmLabel: "Do it",
      cancelLabel: "Nope",
    })
  })

  test("a second confirm() while one is pending cancels the first", async () => {
    const first = confirm({ message: "First?" })
    const second = confirm({ message: "Second?" })

    await expect(first).resolves.toBe(false)
    expect(confirmationDialogStore.getState().current?.message).toBe("Second?")

    confirmationDialogStore.getState().resolve()
    await expect(second).resolves.toBe(true)
  })
})
