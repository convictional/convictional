import { useEffect, useRef } from "react"

// Return focus to the composer when an inline edit closes. Pressing Up moves
// focus into the message/comment being edited; when editing ends (save or
// cancel, i.e. editingId returns to null) the user expects to keep typing in the
// composer. Fires only on the true→null transition, so it never steals focus on
// mount or while entering edit mode.
export function useRefocusOnEditClose(editingId: string | null, focus: () => void): void {
  const wasEditingRef = useRef(false)
  useEffect(() => {
    if (wasEditingRef.current && editingId === null) focus()
    wasEditingRef.current = editingId !== null
  }, [editingId, focus])
}
