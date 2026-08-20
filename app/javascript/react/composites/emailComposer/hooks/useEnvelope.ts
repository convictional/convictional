import { useCallback, useEffect, useRef, useState } from "react"

import { apiFetch } from "~/react/shared/apiFetch"
import { getCSRFToken } from "~/shared/csrf"
import type { EmailEnvelope, EnvelopeField } from "../types"

const DEBOUNCE_MS = 500

interface UseEnvelopeOptions {
  patchUrl: string
  initialEnvelope: EmailEnvelope
}

export interface DirtyFlags {
  to: boolean
  cc: boolean
  bcc: boolean
  subject: boolean
}

export interface UseEnvelopeResult {
  to: string[]
  cc: string[]
  bcc: string[]
  subject: string
  inReplyToId: string | null
  showCc: boolean
  showBcc: boolean
  showSubject: boolean
  unsavedChanges: boolean
  dirty: DirtyFlags
  setTo: (value: string[]) => void
  setCc: (value: string[]) => void
  setBcc: (value: string[]) => void
  setSubject: (value: string) => void
  setShowCc: (value: boolean) => void
  setShowBcc: (value: boolean) => void
  setShowSubject: (value: boolean) => void
  cancelCc: () => void
  cancelBcc: () => void
  // Apply remote broadcast values if the corresponding local copy is clean.
  // Returns true if the value was applied, false if dropped because of a
  // pending local edit.
  applyRemoteTo: (value: string[]) => boolean
  applyRemoteCc: (value: string[]) => boolean
  applyRemoteBcc: (value: string[]) => boolean
  applyRemoteSubject: (value: string) => boolean
  flushSave: () => Promise<void>
  resetDirty: () => void
}

function arraysEqual(a: string[], b: string[]): boolean {
  if (a.length !== b.length) return false
  return a.every((v, i) => v === b[i])
}

export function useEnvelope({ patchUrl, initialEnvelope }: UseEnvelopeOptions): UseEnvelopeResult {
  const [to, setToState] = useState(initialEnvelope.to)
  const [cc, setCcState] = useState(initialEnvelope.cc)
  const [bcc, setBccState] = useState(initialEnvelope.bcc)
  const [subject, setSubjectState] = useState(initialEnvelope.subject)
  const inReplyToId = initialEnvelope.inReplyToId

  const [showCc, setShowCc] = useState(initialEnvelope.cc.length > 0)
  const [showBcc, setShowBcc] = useState(initialEnvelope.bcc.length > 0)
  const [showSubject, setShowSubject] = useState(initialEnvelope.inReplyToId === null)

  const [dirty, setDirty] = useState<DirtyFlags>({ to: false, cc: false, bcc: false, subject: false })
  const [unsavedChanges, setUnsavedChanges] = useState(false)

  // Tracked via ref so dirty flags update outside of React render — useDraftBroadcast
  // reads these synchronously to decide whether to drop an inbound field.
  const dirtyRef = useRef(dirty)
  useEffect(() => {
    dirtyRef.current = dirty
  })

  const pendingRef = useRef<Partial<Record<EnvelopeField, string[] | string>>>({})
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  // Without this guard, a PATCH scheduled while another is in flight can complete out-of-order: if
  // PATCH #1 fails silently after PATCH #2 succeeds, the success clears
  // `unsavedChanges` and `beforeunload` never warns about the lost write.
  const inFlightRef = useRef(false)
  // Gates post-await setState so we don't update an unmounted component when
  // a PATCH resolves after DRAFT_REMOVED has torn the composer down.
  const mountedRef = useRef(true)
  const patchUrlRef = useRef(patchUrl)
  useEffect(() => {
    patchUrlRef.current = patchUrl
  }, [patchUrl])

  const flushSave = useCallback(async () => {
    if (timerRef.current) {
      clearTimeout(timerRef.current)
      timerRef.current = null
    }
    if (inFlightRef.current) return
    const payload = pendingRef.current
    if (Object.keys(payload).length === 0) return
    const sentFields = Object.keys(payload) as EnvelopeField[]
    pendingRef.current = {}
    inFlightRef.current = true
    // Capture whether new writes accumulated during the flight so we can decide
    // in the finally whether to auto-reschedule (vs. waiting for user input).
    let writesDuringFlight = false
    try {
      await apiFetch(patchUrl, {
        method: "PATCH",
        body: JSON.stringify(payload),
      })
      writesDuringFlight = Object.keys(pendingRef.current).length > 0
      if (mountedRef.current) {
        if (!writesDuringFlight) setUnsavedChanges(false)
        setDirty(d => {
          const next = { ...d }
          for (const f of sentFields) next[f] = false
          return next
        })
      }
    } catch {
      // Re-merge the failed payload so the next flush retries it. Newer writes
      // (already in pendingRef from queueSave during the flight) win.
      writesDuringFlight = Object.keys(pendingRef.current).length > 0
      pendingRef.current = { ...payload, ...pendingRef.current }
    } finally {
      inFlightRef.current = false
      // Auto-reschedule only when new writes came in during the flight. On pure
      // failure with no fresh input, leave the re-merged payload pending and
      // wait for the user's next write (or beforeUnload) instead of spamming
      // the server every DEBOUNCE_MS during a sustained outage.
      if (writesDuringFlight && mountedRef.current) {
        timerRef.current = setTimeout(() => {
          void flushSave()
        }, DEBOUNCE_MS)
      }
    }
  }, [patchUrl])

  const queueSave = useCallback(
    (field: EnvelopeField, value: string[] | string) => {
      pendingRef.current[field] = value
      setUnsavedChanges(true)
      // Skip rescheduling while a PATCH is on the wire — the finally block in
      // flushSave will schedule one after it resolves.
      if (inFlightRef.current) return
      if (timerRef.current) clearTimeout(timerRef.current)
      timerRef.current = setTimeout(() => {
        void flushSave()
      }, DEBOUNCE_MS)
    },
    [flushSave]
  )

  useEffect(() => {
    return () => {
      mountedRef.current = false
      if (timerRef.current) clearTimeout(timerRef.current)
      // Flush pending writes with keepalive so a debounce timer that hadn't
      // fired yet doesn't lose the user's last keystrokes on unmount. If the
      // draft has already been removed server-side this will 404 — that's the
      // correct outcome (the writes have nowhere to go).
      if (Object.keys(pendingRef.current).length === 0) return
      const csrf = getCSRFToken()
      const headers: Record<string, string> = {
        Accept: "application/json",
        "Content-Type": "application/json",
      }
      if (csrf) headers["X-CSRFToken"] = csrf
      void fetch(patchUrlRef.current, {
        method: "PATCH",
        body: JSON.stringify(pendingRef.current),
        headers,
        credentials: "same-origin",
        keepalive: true,
      })
      pendingRef.current = {}
    }
  }, [])

  const setTo = useCallback(
    (value: string[]) => {
      setToState(prev => (arraysEqual(prev, value) ? prev : value))
      setDirty(d => ({ ...d, to: true }))
      queueSave("to", value)
    },
    [queueSave]
  )

  const setCc = useCallback(
    (value: string[]) => {
      setCcState(prev => (arraysEqual(prev, value) ? prev : value))
      setDirty(d => ({ ...d, cc: true }))
      queueSave("cc", value)
    },
    [queueSave]
  )

  const setBcc = useCallback(
    (value: string[]) => {
      setBccState(prev => (arraysEqual(prev, value) ? prev : value))
      setDirty(d => ({ ...d, bcc: true }))
      queueSave("bcc", value)
    },
    [queueSave]
  )

  const setSubject = useCallback(
    (value: string) => {
      setSubjectState(value)
      setDirty(d => ({ ...d, subject: true }))
      queueSave("subject", value)
      window.dispatchEvent(new CustomEvent("draft-subject-changed", { detail: { subject: value } }))
    },
    [queueSave]
  )

  const cancelCc = useCallback(() => {
    setCcState([])
    setShowCc(false)
    setDirty(d => ({ ...d, cc: true }))
    queueSave("cc", [])
  }, [queueSave])

  const cancelBcc = useCallback(() => {
    setBccState([])
    setShowBcc(false)
    setDirty(d => ({ ...d, bcc: true }))
    queueSave("bcc", [])
  }, [queueSave])

  // Drop inbound when a local write is in flight OR pending. Both checks are
  // load-bearing: pendingRef.current[field] is written synchronously by
  // queueSave() on every keystroke (the dirty React state hasn't committed
  // yet at that moment); dirtyRef survives until the post-PATCH dirty reset
  // flips it back. Removing either check reopens a race where a server-sent
  // envelope overwrites an uncommitted local edit.
  const applyRemoteTo = useCallback((value: string[]): boolean => {
    if (dirtyRef.current.to || pendingRef.current.to !== undefined) return false
    setToState(value)
    return true
  }, [])

  const applyRemoteCc = useCallback((value: string[]): boolean => {
    if (dirtyRef.current.cc || pendingRef.current.cc !== undefined) return false
    setCcState(value)
    if (value.length > 0) setShowCc(true)
    return true
  }, [])

  const applyRemoteBcc = useCallback((value: string[]): boolean => {
    if (dirtyRef.current.bcc || pendingRef.current.bcc !== undefined) return false
    setBccState(value)
    if (value.length > 0) setShowBcc(true)
    return true
  }, [])

  const applyRemoteSubject = useCallback((value: string): boolean => {
    if (dirtyRef.current.subject || pendingRef.current.subject !== undefined) return false
    setSubjectState(value)
    window.dispatchEvent(new CustomEvent("draft-subject-changed", { detail: { subject: value } }))
    return true
  }, [])

  const resetDirty = useCallback(() => {
    setDirty({ to: false, cc: false, bcc: false, subject: false })
    setUnsavedChanges(false)
  }, [])

  return {
    to,
    cc,
    bcc,
    subject,
    inReplyToId,
    showCc,
    showBcc,
    showSubject,
    unsavedChanges,
    dirty,
    setTo,
    setCc,
    setBcc,
    setSubject,
    setShowCc,
    setShowBcc,
    setShowSubject,
    cancelCc,
    cancelBcc,
    applyRemoteTo,
    applyRemoteCc,
    applyRemoteBcc,
    applyRemoteSubject,
    flushSave,
    resetDirty,
  }
}
