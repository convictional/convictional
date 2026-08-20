import { useEffect, useState } from "react"

interface DraftSubjectChangedDetail {
  subject?: string
}

// The email composer dispatches a `draft-subject-changed` window event when
// the subject input changes. The show page header subscribes to it so the
// page <h1> stays in sync with the in-progress reply without round-tripping
// through state. Returns the current subject (defaulting to `initialSubject`
// until the first event fires).
export function useDraftSubjectListener(initialSubject: string): string {
  const [subject, setSubject] = useState(initialSubject)

  useEffect(() => {
    const handle = (event: Event) => {
      const detail = (event as CustomEvent<DraftSubjectChangedDetail>).detail
      if (detail && typeof detail.subject === "string") setSubject(detail.subject)
    }
    window.addEventListener("draft-subject-changed", handle)
    return () => window.removeEventListener("draft-subject-changed", handle)
  }, [])

  // If the prop changes (eg. navigating between threads in the same SPA-ish
  // session) reset the local state to track it.
  useEffect(() => {
    setSubject(initialSubject)
  }, [initialSubject])

  return subject
}
