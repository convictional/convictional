import { type KeyboardEvent, useEffect, useRef, useState } from "react"

import { ApiError, errorMessage } from "~/react/shared/apiFetch"
import { createResearchQuestion } from "../api"

const SUGGESTIONS: Record<string, string> = {
  "Catch me up with bullet points": "Catch me up on work from last week. Use bullet points, no more than 10.",
  "Daily to-do list": "Generate my to-do list based on the past day.",
}

interface ResearchFormProps {
  onSuccess: () => void
}

export function ResearchForm({ onSuccess }: ResearchFormProps) {
  const [body, setBody] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    textareaRef.current?.focus()
  }, [])

  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = "auto"
    el.style.height = `${el.scrollHeight}px`
  }, [body])

  const submit = async () => {
    if (!body.trim() || submitting) return
    setSubmitting(true)
    setError(null)
    try {
      await createResearchQuestion(body)
      onSuccess()
    } catch (err) {
      if (err instanceof ApiError && err.status === 422) {
        setError("Please enter a question.")
      } else {
        setError(errorMessage(err, "Couldn't submit research request."))
      }
      setSubmitting(false)
    }
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
      event.preventDefault()
      submit()
      return
    }
    // Swallow keys the parent palette consumes for navigation so they don't fire here.
    if (event.key === "Enter" || event.key === "ArrowUp" || event.key === "ArrowDown") {
      event.stopPropagation()
    }
  }

  return (
    <div className="p-2 grid gap-3" data-test-id="research-form">
      <div>
        <p className="text-xs text-base-500 px-2 pb-2">Research</p>
        <span className="text-xs text-base-600/70 inline-flex items-center gap-1 px-2 pb-4">
          Get a research report based on your available emails and meetings, delivered to your inbox when it's
          complete.
        </span>
        <ul className="flex flex-wrap gap-1 px-1">
          <span className="material-symbols-outlined text-lg text-base-500">lightbulb_2</span>
          {Object.entries(SUGGESTIONS).map(([title, prompt]) => (
            <button
              key={title}
              type="button"
              onClick={() => setBody(prompt)}
              className="flex items-center gap-1 py-1 px-2 border border-base-300 rounded-lg text-xs text-base-600/70 hover:bg-base-200 transition shadow-xs cursor-pointer"
            >
              {title}
            </button>
          ))}
        </ul>
      </div>
      <form
        onSubmit={e => {
          e.preventDefault()
          submit()
        }}
        onKeyDown={e => {
          // Stop palette-level Backspace/Delete handlers (clear filter / close).
          if (e.key === "Backspace" || e.key === "Delete") e.stopPropagation()
        }}
        className="grid gap-2 pl-4 pr-2 bg-base-200 rounded-lg"
      >
        <div className="grid grid-cols-[1fr_auto] gap-2 items-end">
          <textarea
            ref={textareaRef}
            value={body}
            onChange={e => setBody(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="What would you like to research?"
            className="textarea w-full min-h-1 max-h-[calc(50dvh-100px)] px-0 py-2 border-none bg-transparent resize-none focus:outline-hidden focus:border-none"
            rows={1}
          />
          <button
            type="submit"
            disabled={submitting || !body.trim()}
            className="btn btn-square btn-sm btn-ghost mb-1.5"
            aria-label="Submit"
          >
            <span className="material-symbols-outlined text-lg">arrow_upward</span>
          </button>
        </div>
        {error && <p className="text-xs text-error pb-2">{error}</p>}
      </form>
    </div>
  )
}
