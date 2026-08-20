import { beforeEach, describe, expect, test } from "vitest"

import { toastStore } from "~/react/shared/stores/toast"

beforeEach(() => {
  toastStore.setState({ toasts: [] })
})

describe("toast store", () => {
  test("show appends a toast, returns its id, and stacks", () => {
    const id1 = toastStore.getState().show({ message: "first", level: "success", persistent: false })
    const id2 = toastStore.getState().show({ message: "second", level: "error", persistent: false })

    const { toasts } = toastStore.getState()
    expect(toasts).toHaveLength(2)
    expect(id1).not.toBe(id2)
    expect(toasts[0]).toMatchObject({ id: id1, message: "first", level: "success" })
    expect(toasts[1]).toMatchObject({ id: id2, message: "second", level: "error" })
  })

  test("dismiss removes only the matching toast", () => {
    const id1 = toastStore.getState().show({ message: "a", level: "success", persistent: false })
    const id2 = toastStore.getState().show({ message: "b", level: "success", persistent: false })

    toastStore.getState().dismiss(id1)

    const { toasts } = toastStore.getState()
    expect(toasts).toHaveLength(1)
    expect(toasts[0].id).toBe(id2)
  })

  test("carries the persistent flag and url through", () => {
    toastStore.getState().show({
      message: "session changed",
      level: "error",
      url: "https://example.test/reload",
      persistent: true,
    })

    expect(toastStore.getState().toasts[0]).toMatchObject({
      persistent: true,
      url: "https://example.test/reload",
    })
  })
})
