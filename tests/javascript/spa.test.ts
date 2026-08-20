import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

const { createRootMock, renderMock } = vi.hoisted(() => {
  const renderMock = vi.fn()
  return {
    renderMock,
    createRootMock: vi.fn(() => ({ render: renderMock, unmount: vi.fn() })),
  }
})

vi.mock("react-dom/client", () => ({ createRoot: createRootMock }))
vi.mock("~/react/app/router", () => ({ router: {} }))
vi.mock("~/shared/themeApplicator", () => ({}))
vi.mock("~/nativeShell", () => ({ applyNativeShellBodyClass: vi.fn(), isNativeShell: vi.fn() }))

describe("spa boot", () => {
  beforeEach(() => {
    vi.resetModules()
    createRootMock.mockClear()
    renderMock.mockClear()
    document.body.innerHTML = ""
  })

  afterEach(() => {
    document.body.innerHTML = ""
  })

  test("mounts the router into #root when present", async () => {
    document.body.innerHTML = '<div id="root"></div>'

    await import("~/spa")

    expect(createRootMock).toHaveBeenCalledTimes(1)
    expect(renderMock).toHaveBeenCalledTimes(1)
  })

  test("does nothing when #root is absent (legacy pages keep the main.ts boot)", async () => {
    await import("~/spa")

    expect(createRootMock).not.toHaveBeenCalled()
  })
})
