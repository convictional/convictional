import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"
import * as Y from "yjs"

const { indexeddbPersistenceMock, instances } = vi.hoisted(() => {
  interface FakeInstance {
    whenSynced: Promise<void>
    resolveSynced: () => void
    rejectSynced: (err: Error) => void
    destroy: ReturnType<typeof vi.fn>
  }
  const recorded: FakeInstance[] = []
  const mock = vi.fn().mockImplementation(function () {
    let resolveSynced!: () => void
    let rejectSynced!: (err: Error) => void
    const whenSynced = new Promise<void>((resolve, reject) => {
      resolveSynced = resolve
      rejectSynced = reject
    })
    const inst: FakeInstance = { whenSynced, resolveSynced, rejectSynced, destroy: vi.fn() }
    recorded.push(inst)
    return inst
  })
  return { indexeddbPersistenceMock: mock, instances: recorded }
})

vi.mock("y-indexeddb", () => ({
  IndexeddbPersistence: indexeddbPersistenceMock,
}))

import {
  createLocalPersistence,
  isIndexedDBAvailable,
} from "../../../app/javascript/shared/localPersistence"

describe("localPersistence", () => {
  beforeEach(() => {
    indexeddbPersistenceMock.mockClear()
    instances.length = 0
    delete (window as { __yIndexeddbSynced?: boolean }).__yIndexeddbSynced
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    delete (window as { __yIndexeddbSynced?: boolean }).__yIndexeddbSynced
  })

  test("isIndexedDBAvailable reflects the global", () => {
    vi.stubGlobal("indexedDB", undefined)
    expect(isIndexedDBAvailable()).toBe(false)

    vi.stubGlobal("indexedDB", { open: vi.fn() })
    expect(isIndexedDBAvailable()).toBe(true)
  })

  test("when indexedDB is unavailable, falls back without touching y-indexeddb", async () => {
    vi.stubGlobal("indexedDB", undefined)
    const persistence = createLocalPersistence("topic-1", new Y.Doc())
    const handler = vi.fn()

    persistence.scheduleAfterSync(handler)
    expect(handler).not.toHaveBeenCalled()

    await Promise.resolve()

    expect(indexeddbPersistenceMock).not.toHaveBeenCalled()
    expect(persistence.provider).toBeNull()
    expect(handler).toHaveBeenCalledTimes(1)
    expect(() => persistence.destroy()).not.toThrow()
    expect((window as { __yIndexeddbSynced?: boolean }).__yIndexeddbSynced).toBeUndefined()
  })

  test("when indexedDB is available, constructs the provider and wires sync side effects", async () => {
    vi.stubGlobal("indexedDB", { open: vi.fn() })
    const ydoc = new Y.Doc()
    const persistence = createLocalPersistence("topic-2", ydoc)

    expect(indexeddbPersistenceMock).toHaveBeenCalledWith("topic-2", ydoc)
    expect(persistence.provider).toBe(instances[0])

    instances[0].resolveSynced()
    await instances[0].whenSynced

    expect((window as { __yIndexeddbSynced?: boolean }).__yIndexeddbSynced).toBe(true)

    persistence.destroy()
    expect(instances[0].destroy).toHaveBeenCalledTimes(1)
  })

  test("scheduleAfterSync runs the handler whether whenSynced resolves or rejects", async () => {
    vi.stubGlobal("indexedDB", { open: vi.fn() })
    const ydoc = new Y.Doc()

    const onResolved = vi.fn()
    createLocalPersistence("topic-resolved", ydoc).scheduleAfterSync(onResolved)
    instances[0].resolveSynced()
    await instances[0].whenSynced
    expect(onResolved).toHaveBeenCalledTimes(1)

    const onRejected = vi.fn()
    createLocalPersistence("topic-rejected", ydoc).scheduleAfterSync(onRejected)
    instances[1].rejectSynced(new Error("idb failed"))
    await instances[1].whenSynced.catch(() => {})
    expect(onRejected).toHaveBeenCalledTimes(1)
  })
})

// Regression for Sentry DECIDE-813: the real y-indexeddb constructor calls
// indexedDB.open() synchronously inside a Promise executor. With indexedDB
// undefined (Mobile Safari Lockdown / Private Browsing), that throws into a
// rejected internal promise and surfaces as an unhandled rejection. The guard
// in createLocalPersistence must skip construction so this never happens.
describe("localPersistence regression (real y-indexeddb)", () => {
  let unhandledRejections: unknown[]
  let processHandler: (reason: unknown) => void
  let windowHandler: (e: PromiseRejectionEvent) => void

  beforeEach(() => {
    unhandledRejections = []
    processHandler = reason => unhandledRejections.push(reason)
    windowHandler = e => {
      e.preventDefault()
      unhandledRejections.push(e.reason)
    }
    process.on("unhandledRejection", processHandler)
    window.addEventListener("unhandledrejection", windowHandler)
  })

  afterEach(() => {
    process.off("unhandledRejection", processHandler)
    window.removeEventListener("unhandledrejection", windowHandler)
    vi.unstubAllGlobals()
    vi.resetModules()
  })

  test("no unhandled rejection when indexedDB is undefined", async () => {
    vi.stubGlobal("indexedDB", undefined)

    vi.doUnmock("y-indexeddb")
    vi.resetModules()
    const { createLocalPersistence: real } = await import(
      "../../../app/javascript/shared/localPersistence"
    )

    const persistence = real("topic-regression", new Y.Doc())

    await new Promise(resolve => setTimeout(resolve, 0))

    expect(unhandledRejections).toHaveLength(0)
    expect(persistence.provider).toBeNull()
    expect(() => persistence.destroy()).not.toThrow()
  })
})
