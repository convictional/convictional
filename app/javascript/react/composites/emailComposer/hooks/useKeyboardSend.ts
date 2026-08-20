import { useEffect, type RefObject } from "react"

interface UseKeyboardSendOptions {
  canSend: boolean
  sending: boolean
  onSend: () => void
  // Listener fires only when the key event originates inside this container,
  // so Cmd+Enter in unrelated editors on the page (e.g. comment forms in an
  // email thread) doesn't trigger send on an open reply.
  containerRef: RefObject<HTMLElement | null>
}

export function useKeyboardSend({ canSend, sending, onSend, containerRef }: UseKeyboardSendOptions): void {
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (event.key !== "Enter") return
      if (!(event.metaKey || event.ctrlKey)) return
      if (!canSend || sending) return
      const container = containerRef.current
      if (!container || !container.contains(event.target as Node)) return
      event.preventDefault()
      onSend()
    }
    window.addEventListener("keydown", handler)
    return () => window.removeEventListener("keydown", handler)
  }, [canSend, sending, onSend, containerRef])
}
