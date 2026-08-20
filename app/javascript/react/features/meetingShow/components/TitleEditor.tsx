import { useCallback, useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react"

import { apiFetch } from "~/react/shared/apiFetch"
import { showFlash } from "~/shared/flash"

import type { MeetingDetail } from "../types"

interface TitleEditorProps {
  meetingId: string
  title: string | null
  onLocalUpdate: (value: string) => void
  onServerUpdate: (meeting: MeetingDetail) => void
}

const DEBOUNCE_MS = 1000

export function TitleEditor({ meetingId, title, onLocalUpdate, onServerUpdate }: TitleEditorProps) {
  const elementRef = useRef<HTMLHeadingElement>(null)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const lastSavedRef = useRef<string>(title ?? "")
  const [hasError, setHasError] = useState(false)
  const [isEditing, setIsEditing] = useState(false)

  // Sync external prop changes (server refetch, channel push) into the DOM
  // only when the user isn't actively editing — comparing innerText to the
  // incoming value avoids ping-pong during fast typing.
  useEffect(() => {
    const el = elementRef.current
    if (!el) return
    if (isEditing || document.activeElement === el) return
    const incoming = title ?? ""
    if (el.innerText !== incoming) {
      el.innerText = incoming
      lastSavedRef.current = incoming
    }
  }, [title, isEditing])

  // Focus + select all when entering edit mode.
  useEffect(() => {
    if (!isEditing) return
    const el = elementRef.current
    if (!el) return
    el.focus()
    const range = document.createRange()
    range.selectNodeContents(el)
    const sel = window.getSelection()
    sel?.removeAllRanges()
    sel?.addRange(range)
  }, [isEditing])

  const save = useCallback(
    (value: string): boolean => {
      const trimmed = value.trim()
      if (!trimmed) {
        setHasError(true)
        return false
      }
      setHasError(false)
      if (trimmed === lastSavedRef.current) return true
      const previousSaved = lastSavedRef.current
      lastSavedRef.current = trimmed
      onLocalUpdate(trimmed)
      void (async () => {
        try {
          const updated = await apiFetch<MeetingDetail>(`/api/meetings/${meetingId}`, {
            method: "PATCH",
            body: JSON.stringify({ title: trimmed }),
          })
          onServerUpdate(updated)
        } catch {
          // apiFetch reports to Sentry, but the DOM still shows the typed text,
          // so flash the failure and revert the dedupe marker so a follow-up
          // save retries instead of being skipped as a no-op.
          showFlash("Could not save the meeting title.", "error")
          lastSavedRef.current = previousSaved
        }
      })()
      return true
    },
    [meetingId, onLocalUpdate, onServerUpdate]
  )

  const saveAndExit = useCallback(
    (value: string) => {
      if (timerRef.current) clearTimeout(timerRef.current)
      if (save(value)) setIsEditing(false)
    },
    [save]
  )

  const flushSoon = useCallback(
    (value: string) => {
      if (timerRef.current) clearTimeout(timerRef.current)
      timerRef.current = setTimeout(() => save(value), DEBOUNCE_MS)
    },
    [save]
  )

  const handleInput = useCallback(
    (e: FormEvent<HTMLHeadingElement>) => {
      if (!isEditing) return
      const value = e.currentTarget.innerText
      setHasError(false)
      flushSoon(value)
    },
    [isEditing, flushSoon]
  )

  const handleBlur = useCallback(() => {
    if (!isEditing) return
    const el = elementRef.current
    if (!el) return
    saveAndExit(el.innerText)
  }, [isEditing, saveAndExit])

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLHeadingElement>) => {
      if (!isEditing) return
      if (e.key === "Enter") {
        e.preventDefault()
        saveAndExit(e.currentTarget.innerText)
      }
      if (e.key === "Escape") {
        e.preventDefault()
        if (elementRef.current) elementRef.current.innerText = lastSavedRef.current
        setHasError(false)
        setIsEditing(false)
      }
    },
    [isEditing, saveAndExit]
  )

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [])

  const cursorClass = isEditing ? (hasError ? "cursor-default" : "cursor-text") : "cursor-default"

  return (
    <div className={`group flex items-center gap-2${hasError ? " border border-error-content rounded" : ""}`}>
      <h1
        ref={elementRef}
        contentEditable={isEditing}
        suppressContentEditableWarning
        spellCheck
        className={`text-xl text-pretty font-accent wrap-anywhere outline-none flex-1 ${cursorClass}`}
        onInput={handleInput}
        onBlur={handleBlur}
        onKeyDown={handleKeyDown}
      >
        {title || "Untitled meeting"}
      </h1>
      <button
        type="button"
        onClick={e => {
          e.stopPropagation()
          setIsEditing(true)
        }}
        className={`shrink-0 p-1 text-base-content/40 hover:text-base-content/60 cursor-pointer transition-opacity [@media(hover:hover)]:opacity-0 [@media(hover:hover)]:group-hover:opacity-100${isEditing ? " invisible" : ""}`}
        aria-label="Edit title"
      >
        <span className="material-symbols-outlined text-lg">edit</span>
      </button>
    </div>
  )
}
