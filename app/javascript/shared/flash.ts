type FlashLevel = "error" | "success"

export interface ToastEventDetail {
  message: string
  level: FlashLevel
  url?: string
  persistent: boolean
}

// shared/ is framework-agnostic and may not import react/ (enforced by
// .dependency-cruiser.cjs). So showFlash dispatches a window event that the
// Toaster island bridges into its Zustand store — mirroring the
// `command-palette:toggle` cross-boundary pattern.
export const TOAST_EVENT = "toast:show"

export function showFlash(
  message: string,
  level: FlashLevel = "error",
  url?: string,
  persistent: boolean = false
): void {
  const detail: ToastEventDetail = { message, level, url, persistent }
  window.dispatchEvent(new CustomEvent<ToastEventDetail>(TOAST_EVENT, { detail }))
}

interface QueuedFlash {
  message: string
  level: FlashLevel
}

// An in-page showFlash() event can't survive a full-page navigation. queueFlash
// stashes a one-shot flash in sessionStorage before navigating; the destination
// drains it via consumeQueuedFlashes() on mount (see react/app/AppShell.tsx).
const QUEUED_FLASH_KEY = "queued-flashes"

export function queueFlash(message: string, level: FlashLevel = "success"): void {
  try {
    const queued: QueuedFlash[] = JSON.parse(sessionStorage.getItem(QUEUED_FLASH_KEY) ?? "[]")
    queued.push({ message, level })
    sessionStorage.setItem(QUEUED_FLASH_KEY, JSON.stringify(queued))
  } catch {
    // sessionStorage can be unavailable (private mode, quota); a missed confirmation is acceptable.
  }
}

export function consumeQueuedFlashes(): QueuedFlash[] {
  try {
    const raw = sessionStorage.getItem(QUEUED_FLASH_KEY)
    if (!raw) return []
    sessionStorage.removeItem(QUEUED_FLASH_KEY)
    return JSON.parse(raw)
  } catch {
    return []
  }
}
