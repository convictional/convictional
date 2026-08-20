import { getRouteApi, useLocation, useNavigate } from "@tanstack/react-router"
import { useCallback, useState } from "react"

import type { Mode } from "~/react/features/documentsIndex/types"
import { apiFetch, errorMessage } from "~/react/shared/apiFetch"
import { withReturnTo } from "~/react/shared/returnTo"
import { toastStore } from "~/react/shared/stores/toast"
import type { DocumentFilter, DocumentShowResponse } from "~/react/shared/types"
import { EmptyState } from "~/react/ui/EmptyState"
import { ErrorState } from "~/react/ui/ErrorState"
import { LoadingState } from "~/react/ui/LoadingState"
import { LoadMoreSentinel } from "~/react/ui/LoadMoreSentinel"
import { DocumentRow } from "./components/DocumentRow"
import { DocumentSearchResultItem } from "./components/DocumentSearchResultItem"
import { DocumentTemplates } from "./components/DocumentTemplates"
import { Header } from "./components/Header"
import { DocumentsListSkeleton } from "./DocumentsIndexSkeleton"
import { useDocumentsIndex } from "./hooks/useDocumentsIndex"
import { useDocumentsSearch } from "./hooks/useDocumentsSearch"

// The route id carries the pathless shell parent prefix (shellRoute has id
// "shell"), so the typed accessor is addressed as "/shell/documents".
const routeApi = getRouteApi("/shell/documents")

export function DocumentsIndex() {
  const routeSearch = routeApi.useSearch()
  const filter = routeSearch.filter ?? "mine"
  const q = routeSearch.q ?? ""
  const navigate = useNavigate()
  // The current index URL (filter/q included) — the "back" target stamped onto
  // each row link so the show page's back button returns here.
  const returnTo = useLocation({ select: location => location.href })

  const [creating, setCreating] = useState(false)

  const changeFilter = useCallback(
    (next: DocumentFilter) => {
      void navigate({ to: "/documents", search: prev => ({ ...prev, filter: next }) })
    },
    [navigate]
  )

  const commitQuery = useCallback(
    (query: string) => {
      void navigate({ to: "/documents", replace: true, search: prev => ({ ...prev, q: query || undefined }) })
    },
    [navigate]
  )

  const navigateToResult = useCallback((sourceUrl: string) => {
    // Search results are server-resolved gid links, not /documents/{id}, so this
    // is a full-document load the server's gid_redirect resolves (carrying return_to).
    window.location.assign(withReturnTo(sourceUrl))
  }, [])

  const browse = useDocumentsIndex(filter)
  const search = useDocumentsSearch({ routeQuery: q, onCommit: commitQuery, onNavigateToResult: navigateToResult })

  const mode: Mode = search.isOpen ? "search" : "browse"

  const openSearch = useCallback(() => search.setIsOpen(true), [search])

  // A blank New-document click sends {}; a template sends its title + markdown body, which the
  // create endpoint seeds into the Yjs doc before we open the editor.
  const createDocument = useCallback(
    async (body: { title?: string; content?: string } = {}) => {
      if (creating) return
      setCreating(true)
      try {
        const document = await apiFetch<DocumentShowResponse>("/api/documents", {
          method: "POST",
          body: JSON.stringify(body),
        })
        void navigate({ to: "/documents/$documentId/edit", params: { documentId: document.id } })
      } catch (e) {
        setCreating(false)
        toastStore
          .getState()
          .show({ message: errorMessage(e, "Could not create document."), level: "error", persistent: false })
      }
    },
    [creating, navigate]
  )

  return (
    <div>
      <Header
        mode={mode}
        filter={filter}
        onChangeFilter={changeFilter}
        query={search.query}
        onChangeQuery={search.setQuery}
        onKeyDown={search.handleKeyDown}
        onOpenSearch={openSearch}
        onCloseSearch={search.handleClose}
        searchLoading={search.loading && search.results.length > 0}
        onNewDocument={() => createDocument()}
        creating={creating}
      />
      <div className="w-full px-[9px]">
        {mode === "search" ? (
          <SearchPanel search={search} />
        ) : (
          <>
            <DocumentTemplates
              disabled={creating}
              onSelect={template =>
                void createDocument({
                  title: typeof template.title === "function" ? template.title() : template.title,
                  content: template.body,
                })
              }
            />
            <BrowsePanel browse={browse} returnTo={returnTo} />
          </>
        )}
      </div>
    </div>
  )
}

function BrowsePanel({ browse, returnTo }: { browse: ReturnType<typeof useDocumentsIndex>; returnTo: string }) {
  if (browse.loading && browse.documents.length === 0) {
    return <DocumentsListSkeleton />
  }

  if (browse.error) {
    return <ErrorState message="Failed to load documents. Please try refreshing the page." />
  }

  if (browse.documents.length === 0) {
    return <EmptyState title="No documents yet" text="Create a new document to get started" />
  }

  return (
    <>
      <div className="documents-page">
        {browse.documents.map(doc => (
          <DocumentRow key={doc.id} document={doc} returnTo={returnTo} />
        ))}
      </div>
      {browse.hasMore && <LoadMoreSentinel onIntersect={browse.loadMore} loading={browse.loadingMore} />}
    </>
  )
}

function SearchPanel({ search }: { search: ReturnType<typeof useDocumentsSearch> }) {
  const { results, loading, error, query, searchActive, selectedIndex } = search
  const hasResults = results.length > 0
  const showInitialSpinner = loading && !hasResults && searchActive
  const showEmptyPrompt = !loading && !error && !searchActive && !hasResults
  const showNoResults = !loading && !error && searchActive && !hasResults

  if (error) {
    return <ErrorState message="Failed to search documents. Please try refreshing the page." />
  }

  if (showInitialSpinner) {
    return <LoadingState />
  }

  if (showEmptyPrompt) {
    return <EmptyState text="Enter a search query to find documents" />
  }

  if (showNoResults) {
    return <EmptyState text={`No documents found for "${query}"`} />
  }

  return (
    <div className={loading ? "opacity-60 transition-opacity" : "transition-opacity"}>
      {results.map((result, i) => (
        <DocumentSearchResultItem key={result.id} result={result} query={query} isSelected={i === selectedIndex} />
      ))}
    </div>
  )
}
