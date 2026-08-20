import { useEffect } from "react"

export function useBeforeUnloadGuard(unsavedChanges: boolean): void {
  useEffect(() => {
    if (!unsavedChanges) return
    const handler = (event: BeforeUnloadEvent) => {
      event.preventDefault()
      event.returnValue = ""
    }
    window.addEventListener("beforeunload", handler)
    return () => window.removeEventListener("beforeunload", handler)
  }, [unsavedChanges])
}
