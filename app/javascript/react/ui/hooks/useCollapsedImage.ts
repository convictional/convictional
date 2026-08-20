import { useCallback, useState } from "react"

const STORAGE_PREFIX = "chat-image-collapsed:"

// Attachment download URLs look like /…/attachments/{id}/download. Key off the
// stable attachment id so a user's collapse choice survives reload and applies
// wherever the same attachment renders; fall back to the raw value otherwise.
export function attachmentKey(src: string): string {
  return src.match(/\/attachments\/([^/]+)\/download/)?.[1] ?? src
}

function read(key: string): boolean {
  try {
    return window.localStorage.getItem(key) === "1"
  } catch {
    return false
  }
}

// `id` is a stable logical identifier (one attachment key, or several joined for
// a gallery) — not the raw src — so every render of the same image shares state.
export function useCollapsedImage(id: string): [boolean, () => void] {
  const key = STORAGE_PREFIX + id
  const [collapsed, setCollapsed] = useState(() => read(key))

  const toggle = useCallback(() => {
    setCollapsed(prev => {
      const next = !prev
      try {
        window.localStorage.setItem(key, next ? "1" : "0")
      } catch {
        // private mode / storage disabled — collapse still works for the session
      }
      return next
    })
  }, [key])

  return [collapsed, toggle]
}
