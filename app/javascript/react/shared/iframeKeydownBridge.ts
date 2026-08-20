// Keydowns inside the same-origin email-body iframe don't cross the frame
// boundary, so re-dispatch them on the parent where @github/hotkey listens.
// Dispatch on an Element (not the Document): the hotkey gate calls
// target.matches(...), which a Document lacks.
// Forwards the full keydown stream, so a caller on a page that runs the global
// hotkey initializer would fire any parent [data-hotkey], not just scoped keys.
export function bridgeIframeKeydown(sourceDoc: Document, targetDoc: Document = document): () => void {
  const onKey = (event: KeyboardEvent) => {
    if (event.defaultPrevented) return
    const forwarded = new KeyboardEvent("keydown", {
      key: event.key,
      code: event.code,
      ctrlKey: event.ctrlKey,
      altKey: event.altKey,
      metaKey: event.metaKey,
      shiftKey: event.shiftKey,
      bubbles: true,
      cancelable: true,
    })
    ;(targetDoc.body ?? targetDoc.documentElement).dispatchEvent(forwarded)
  }

  sourceDoc.addEventListener("keydown", onKey)
  return () => sourceDoc.removeEventListener("keydown", onKey)
}
