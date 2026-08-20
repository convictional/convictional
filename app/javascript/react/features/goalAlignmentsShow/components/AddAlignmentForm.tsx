import { useEffect, useRef, useState } from "react"

import { ApiError } from "~/react/shared/apiFetch"
import { CONTENT_TYPE_ICONS } from "~/react/shared/contentTypes"
import { useContentSearch } from "../hooks/useContentSearch"

export function AddAlignmentForm({
  onSubmit,
}: {
  onSubmit: (contentId: string, description: string) => Promise<void>
}) {
  const [isFormOpen, setIsFormOpen] = useState(false)
  const [description, setDescription] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const { state, setQuery, highlightNext, highlightPrev, selectActive, select, clearSelection, close } =
    useContentSearch()

  const searchRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const activeItemRef = useRef<HTMLLIElement>(null)

  // Focus the search input when the form opens or the selected content is cleared
  // to search again.
  useEffect(() => {
    if (isFormOpen && !state.selected) inputRef.current?.focus()
  }, [isFormOpen, state.selected])

  // Keep the keyboard-highlighted result scrolled into view.
  useEffect(() => {
    activeItemRef.current?.scrollIntoView({ block: "nearest" })
  }, [state.activeIndex])

  // Close the results menu on an outside click.
  useEffect(() => {
    if (!state.isOpen) return
    const onPointerDown = (event: MouseEvent) => {
      if (searchRef.current && !searchRef.current.contains(event.target as Node)) close()
    }
    document.addEventListener("mousedown", onPointerDown)
    return () => document.removeEventListener("mousedown", onPointerDown)
  }, [state.isOpen, close])

  const resetAndClose = () => {
    setIsFormOpen(false)
    setDescription("")
    setSubmitError(null)
    clearSelection()
  }

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!state.selected || submitting) return
    setSubmitting(true)
    setSubmitError(null)
    try {
      await onSubmit(state.selected.id, description)
      resetAndClose()
    } catch (error) {
      setSubmitError(messageForError(error))
    } finally {
      setSubmitting(false)
    }
  }

  const handleKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === "ArrowDown") {
      event.preventDefault()
      highlightNext()
    } else if (event.key === "ArrowUp") {
      event.preventDefault()
      highlightPrev()
    } else if (event.key === "Enter") {
      event.preventDefault()
      selectActive()
    } else if (event.key === "Escape") {
      close()
    }
  }

  return (
    <div className="card card-compact bg-base-200 p-4">
      <h3 className="text-lg font-semibold">Did we miss something?</h3>
      <p className="text-sm text-base-500 mb-4">
        We are collecting data to improve automated goal alignment, if you know of other content that aligns with this
        goal, please add it below.
      </p>

      {!isFormOpen && (
        <button type="button" className="btn btn-ghost btn-sm mr-auto" onClick={() => setIsFormOpen(true)}>
          Add aligned content
        </button>
      )}

      {isFormOpen && (
        <form onSubmit={handleSubmit} className="mt-4">
          <div className="flex flex-col gap-4">
            <div className="flex flex-col gap-1">
              <label htmlFor="content_search" className="text-xs">
                Search for content
              </label>
              {!state.selected ? (
                <div className="relative" ref={searchRef}>
                  <input
                    id="content_search"
                    ref={inputRef}
                    type="text"
                    className="input input-bordered w-full"
                    placeholder="Search for a post or meeting..."
                    autoComplete="off"
                    value={state.query}
                    onChange={e => setQuery(e.target.value)}
                    onKeyDown={handleKeyDown}
                  />
                  {state.isOpen && (
                    <div className="absolute z-10 w-full mt-1 bg-base-100 border border-base-300 rounded-lg shadow-lg max-h-64 overflow-y-auto">
                      {state.results.length > 0 ? (
                        <ul className="menu p-0">
                          {state.results.map((result, i) => (
                            <li key={result.id} ref={i === state.activeIndex ? activeItemRef : undefined}>
                              <button
                                type="button"
                                onClick={() => select(result)}
                                className={`flex items-center gap-2 py-2 px-3 cursor-pointer rounded-lg hover:bg-base-300 ${
                                  i === state.activeIndex ? "bg-base-300" : ""
                                }`}
                              >
                                <span className="material-symbols-outlined text-lg">
                                  {CONTENT_TYPE_ICONS[result.content_type] ?? "description"}
                                </span>
                                <div className="flex-1 min-w-0 text-left">
                                  <p className="text-sm line-clamp-1">{result.title}</p>
                                  {result.author && <p className="text-xs text-base-500">{result.author}</p>}
                                </div>
                              </button>
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <p className="text-sm text-base-500 p-3">No results found.</p>
                      )}
                    </div>
                  )}
                </div>
              ) : (
                <div className="flex items-center gap-2 p-3 bg-base-100 rounded-lg border border-base-300">
                  <span className="material-symbols-outlined text-lg text-primary">check_circle</span>
                  <span className="text-sm flex-1">{state.selected.title}</span>
                  <button type="button" className="btn btn-ghost btn-xs btn-circle" onClick={clearSelection}>
                    <span className="material-symbols-outlined text-base">close</span>
                  </button>
                </div>
              )}
              <p className="text-xs text-base-500">
                Content search includes posts and meetings. Content created this week is not included in the search
                results.
              </p>
            </div>

            <div className="flex flex-col gap-1">
              <label htmlFor="description" className="text-xs">
                Description
              </label>
              <textarea
                name="description"
                id="description"
                className="textarea textarea-bordered w-full"
                placeholder="Let us know how this content aligns with the goal"
                required
                value={description}
                onChange={e => setDescription(e.target.value)}
              />
            </div>

            {submitError && <p className="text-sm text-error">{submitError}</p>}

            <div className="flex gap-2 justify-end ml-auto">
              <button type="button" className="btn btn-ghost" onClick={resetAndClose}>
                Cancel
              </button>
              <button type="submit" className="btn btn-primary ml-auto" disabled={!state.selected || submitting}>
                Save
              </button>
            </div>
          </div>
        </form>
      )}
    </div>
  )
}

function messageForError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 409) return "This content is already aligned with the goal."
    if (error.status === 404) return "Content not found."
  }
  return "Could not add alignment. Please try again."
}
