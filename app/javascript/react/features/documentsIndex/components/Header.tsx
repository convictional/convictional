import type React from "react"
import { useEffect, useRef } from "react"

import type { DocumentFilter, Mode } from "~/react/features/documentsIndex/types"
import { StickyHeader } from "~/react/ui/StickyHeader"
import { Tooltip } from "~/react/ui/Tooltip"
import { FilterDropdown } from "./FilterDropdown"

interface HeaderProps {
  mode: Mode
  filter: DocumentFilter
  onChangeFilter: (filter: DocumentFilter) => void
  query: string
  onChangeQuery: (query: string) => void
  onKeyDown: (e: React.KeyboardEvent) => void
  onOpenSearch: () => void
  onCloseSearch: () => void
  searchLoading: boolean
  onNewDocument: () => void
  creating: boolean
}

export function Header({
  mode,
  filter,
  onChangeFilter,
  query,
  onChangeQuery,
  onKeyDown,
  onOpenSearch,
  onCloseSearch,
  searchLoading,
  onNewDocument,
  creating,
}: HeaderProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const isSearch = mode === "search"

  useEffect(() => {
    if (isSearch) inputRef.current?.focus()
  }, [isSearch])

  return (
    <StickyHeader>
      <div className="flex items-center justify-between gap-2 p-2">
        <div className="flex items-center gap-2 flex-1 min-w-0">
          {isSearch ? (
            <div className="relative flex items-center flex-1 min-w-0" onKeyDown={onKeyDown}>
              <input
                ref={inputRef}
                type="text"
                value={query}
                onChange={e => onChangeQuery(e.target.value)}
                placeholder="Search documents..."
                autoComplete="off"
                autoCorrect="off"
                autoCapitalize="off"
                spellCheck={false}
                className="w-full pl-2 pr-16 py-2 bg-transparent outline-none text-base"
              />
              <div className="absolute right-1 top-1/2 -translate-y-1/2 flex items-center gap-2 z-10">
                {searchLoading && <span className="loading loading-spinner loading-xs" />}
                <button
                  type="button"
                  onClick={onCloseSearch}
                  className="btn btn-ghost btn-sm btn-square text-base-content/40 hover:text-base-content/70"
                  aria-label="Close search"
                >
                  <span className="material-symbols-outlined text-lg">close</span>
                </button>
              </div>
            </div>
          ) : (
            <>
              <button
                type="button"
                onClick={onOpenSearch}
                className="btn btn-square border border-neutral sticky-header-search"
                aria-label="Search documents"
              >
                <span className="material-symbols-outlined text-base">search</span>
              </button>
              <FilterDropdown filter={filter} onChange={onChangeFilter} />
            </>
          )}
        </div>
        {!isSearch && (
          <Tooltip content="New document">
            <button
              type="button"
              onClick={onNewDocument}
              disabled={creating}
              className="btn btn-square border border-neutral"
              aria-label="New document"
            >
              {creating ? (
                <span className="loading loading-spinner loading-xs" />
              ) : (
                <span className="material-symbols-outlined text-base">add</span>
              )}
            </button>
          </Tooltip>
        )}
      </div>
    </StickyHeader>
  )
}
