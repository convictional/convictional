import { type ChangeEvent, type KeyboardEvent, type RefObject, useLayoutEffect } from "react"

import { FilterChip } from "./FilterChip"
import type { FilterMeta, Mode } from "./types"

interface PaletteInputProps {
  inputRef: RefObject<HTMLInputElement | null>
  input: string
  placeholder: string
  mode: Mode
  filter: FilterMeta | null
  showLoadingBar: boolean
  showTimeoutError: boolean
  onChange: (value: string) => void
  onKeyDown: (event: KeyboardEvent<HTMLInputElement>) => void
  onClearFilter: () => void
  onBack: () => void
}

export function PaletteInput({
  inputRef,
  input,
  placeholder,
  mode,
  filter,
  showLoadingBar,
  showTimeoutError,
  onChange,
  onKeyDown,
  onClearFilter,
  onBack,
}: PaletteInputProps) {
  // useLayoutEffect (not useEffect) so focus runs synchronously after the DOM
  // mutates — including when an active-mode sub-form unmounts and we need to
  // reclaim focus on the palette input before any post-paint side effects
  // (e.g. document-level hotkey handlers) can interpret the keystroke.
  useLayoutEffect(() => {
    inputRef.current?.focus()
  }, [inputRef, mode])

  const showBackButton = mode === "commands" || mode === "active"
  const isReadonly = mode === "active"

  return (
    <>
      {showTimeoutError && (
        <div className="bg-error/20 border-b border-error/40">
          <div className="flex items-center gap-2 px-4 py-2 text-error-content">
            <span className="material-symbols-outlined text-lg">error</span>
            <span className="text-xs">
              This search is taking longer than usual. Results will appear when ready, or you can try again later.
            </span>
          </div>
        </div>
      )}
      <div className="relative overflow-hidden border-b border-neutral">
        {showLoadingBar && !showTimeoutError && (
          <div className="absolute inset-0 bg-base-200/60 w-0 animate-[fillToNinetyFive_8s_cubic-bezier(0,0,0.05,1)_forwards]" />
        )}
        <div className="relative flex items-center px-4 gap-2">
          {showBackButton && (
            <button onClick={onBack} type="button" className="btn btn-sm btn-square">
              <span className="material-symbols-outlined text-lg">arrow_back</span>
            </button>
          )}
          {filter && <FilterChip filter={filter} onClear={onClearFilter} />}
          <input
            ref={inputRef}
            type="text"
            role="combobox"
            aria-label="Search or run a command"
            aria-expanded="true"
            aria-autocomplete="list"
            value={input}
            placeholder={placeholder}
            readOnly={isReadonly}
            onChange={(e: ChangeEvent<HTMLInputElement>) => onChange(e.target.value)}
            onKeyDown={onKeyDown}
            data-test-id="palette-input"
            autoComplete="off"
            autoCorrect="off"
            autoCapitalize="off"
            spellCheck={false}
            className={`flex-1 py-4 text-lg bg-transparent focus:outline-none ${
              isReadonly ? "opacity-70 cursor-default" : ""
            }`}
          />
        </div>
      </div>
    </>
  )
}
