import { IndexeddbPersistence } from "y-indexeddb"
import * as Y from "yjs"

export function isIndexedDBAvailable(): boolean {
  return typeof indexedDB !== "undefined" && indexedDB !== null
}

export interface LocalPersistence {
  provider: IndexeddbPersistence | null
  scheduleAfterSync: (handler: () => void) => void
  destroy: () => void
}

export function createLocalPersistence(topicId: string, ydoc: Y.Doc): LocalPersistence {
  // try/catch defends against environments where indexedDB is defined but the
  // constructor throws synchronously — sandboxed iframes without storage-access,
  // some embedded webviews. The Sentry signal targets the undefined-indexedDB
  // case, which the availability check already handles.
  let provider: IndexeddbPersistence | null = null
  if (isIndexedDBAvailable()) {
    try {
      provider = new IndexeddbPersistence(topicId, ydoc)
    } catch {
      provider = null
    }
  }

  if (provider !== null) {
    provider.whenSynced
      .then(() => {
        ;(window as { __yIndexeddbSynced?: boolean }).__yIndexeddbSynced = true
      })
      .catch(() => {})
  }

  // Dual-arm `.then(handler, handler)` so the seed handler runs even if IndexedDB
  // rejects (e.g. private browsing). queueMicrotask mirrors that timing when the
  // provider isn't created at all.
  const scheduleAfterSync = (handler: () => void): void => {
    if (provider !== null) {
      provider.whenSynced.then(handler, handler)
    } else {
      queueMicrotask(handler)
    }
  }

  const destroy = (): void => {
    provider?.destroy()
  }

  return { provider, scheduleAfterSync, destroy }
}
