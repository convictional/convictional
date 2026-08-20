import { useCallback, useEffect, useRef, useState } from "react"

import { apiFetch } from "~/react/shared/apiFetch"

interface TitleInputProps {
  saveUrl: string
  initialTitle: string
  placeholder?: string
  autoSelectTitle?: string
}

const DEBOUNCE_MS = 1000

export function TitleInput({ saveUrl, initialTitle, placeholder = "Title", autoSelectTitle }: TitleInputProps) {
  const [title, setTitle] = useState(initialTitle)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const dispatchUnsaved = useCallback(() => {
    inputRef.current?.dispatchEvent(new CustomEvent("unsaved", { bubbles: true }))
  }, [])

  const dispatchSaved = useCallback(() => {
    inputRef.current?.dispatchEvent(new CustomEvent("saved", { bubbles: true }))
  }, [])

  const save = useCallback(
    async (titleToSave: string) => {
      dispatchUnsaved()
      try {
        await apiFetch(saveUrl, {
          method: "PATCH",
          body: JSON.stringify({ title: titleToSave }),
        })
        dispatchSaved()
      } catch {
        // Real errors (network, 500) — leave the "Saving..." indicator showing
        // so the user knows the save didn't complete
      }
    },
    [saveUrl, dispatchUnsaved, dispatchSaved]
  )

  const debouncedSave = useCallback(
    (newTitle: string) => {
      if (timerRef.current) clearTimeout(timerRef.current)
      timerRef.current = setTimeout(() => {
        save(newTitle)
      }, DEBOUNCE_MS)
    },
    [save]
  )

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const newTitle = e.target.value
      setTitle(newTitle)
      dispatchUnsaved()
      debouncedSave(newTitle)
    },
    [dispatchUnsaved, debouncedSave]
  )

  const handleBlur = useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current)
    save(title)
  }, [save, title])

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [])

  // Select title on mount for new resources so the user can immediately rename
  const shouldAutoSelect = autoSelectTitle && initialTitle === autoSelectTitle
  useEffect(() => {
    if (shouldAutoSelect) {
      inputRef.current?.select()
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <input
      ref={inputRef}
      className="input w-full bg-transparent border-0 !rounded-none text-3xl font-accent focus:outline-none px-0 placeholder:text-base-400"
      value={title}
      onChange={handleChange}
      onBlur={handleBlur}
      placeholder={placeholder}
      autoComplete="off"
      autoFocus={!!shouldAutoSelect}
      required
    />
  )
}
