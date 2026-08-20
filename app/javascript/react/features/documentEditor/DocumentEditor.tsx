import { useQuery, useQueryClient } from "@tanstack/react-query"
import { getRouteApi, useNavigate } from "@tanstack/react-router"
import { useCallback, useEffect, useRef, useState } from "react"

import { RequestDocumentAccess } from "~/react/composites/RequestDocumentAccess"
import { accessDeniedUrl } from "~/react/shared/apiFetch"
import { useCurrentUser } from "~/react/shared/hooks/useCurrentUser"
import { useDocumentTitle } from "~/react/shared/hooks/useDocumentTitle"
import { useWorkspaceVisitRecording } from "~/react/shared/hooks/useVisitRecording"
import { safeReturnTo } from "~/react/shared/returnTo"
import { documentBackNavigation, documentQueryOptions } from "~/react/shared/stores/documents"
import type { Sharing } from "~/react/shared/types"
import { ErrorState } from "~/react/ui/ErrorState"

import { DocumentEditorBody } from "./DocumentEditorBody"
import { DocumentEditorHeader } from "./DocumentEditorHeader"
import { DocumentEditorSkeleton } from "./DocumentEditorSkeleton"

// The route id carries the pathless shell parent prefix (shellRoute has id
// "shell"), so the typed accessor is addressed as
// "/shell/documents/$documentId/edit".
const routeApi = getRouteApi("/shell/documents/$documentId/edit")

// Per-option subscription copy for documents. The bell is built here rather than
// passed as a prop because the editor is a client route — only workspaceId (from
// the detail query) varies.
const SUBSCRIPTION_OPTIONS = {
  all: { hint: "Every comment" },
  relevant: { hint: "@mentions, comments on yours" },
  default: { hint: "Use your document settings" },
} as const

export function DocumentEditor() {
  const { documentId } = routeApi.useParams()
  const { return_to: returnTo } = routeApi.useSearch()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { user, clientConfig } = useCurrentUser()

  const containerRef = useRef<HTMLDivElement>(null)

  const detail = useQuery(documentQueryOptions(documentId))
  const data = detail.data
  useDocumentTitle(data?.title ?? "Document")

  // Non-collaborators don't get the editor — they get the read-only show page.
  // This is the inverse of documentShow's collaborator→editor redirect, and it's
  // the access gate for deep links and the comment/mention mailers (which point
  // straight at the editor). replace() keeps the editor out of history.
  const isCollaborator = data?.is_collaborator ?? false
  useEffect(() => {
    if (!data || isCollaborator) return
    const safe = safeReturnTo(returnTo)
    void navigate({
      to: "/documents/$documentId",
      params: { documentId },
      search: safe ? { return_to: safe } : {},
      replace: true,
    })
  }, [data, isCollaborator, documentId, returnTo, navigate])

  // Record the workspace visit once, when the document loads for a collaborator.
  // Non-collaborators are redirected to the show page, which records its own.
  const recordVisit = useWorkspaceVisitRecording(data?.workspace_id ?? null)
  const trackedVisitRef = useRef(false)
  useEffect(() => {
    if (!data || !isCollaborator || trackedVisitRef.current) return
    trackedVisitRef.current = true
    recordVisit()
  }, [data, isCollaborator, recordVisit])

  // TitleInput dispatches bubbling "unsaved"/"saved" events when a debounced
  // PATCH starts/completes. Catching them at the container drives the header's
  // save indicator without coupling the header to TitleInput's internals.
  const [savingTitle, setSavingTitle] = useState(false)
  const [titleEverChanged, setTitleEverChanged] = useState(false)
  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const onUnsaved = () => {
      setSavingTitle(true)
      setTitleEverChanged(true)
    }
    const onSaved = () => setSavingTitle(false)
    el.addEventListener("unsaved", onUnsaved)
    el.addEventListener("saved", onSaved)
    return () => {
      el.removeEventListener("unsaved", onUnsaved)
      el.removeEventListener("saved", onSaved)
    }
  }, [])

  // Reflect an optimistic sharing change (and its revert) from the header's
  // SharingDropdown into the cached detail, so the dropdown trigger icon stays
  // in sync without a refetch.
  const onSharingChange = useCallback(
    (sharing: Sharing) => {
      queryClient.setQueryData(documentQueryOptions(documentId).queryKey, prev => (prev ? { ...prev, sharing } : prev))
    },
    [queryClient, documentId]
  )

  // Only detail.error is checked (unlike documentShow, which also checks its
  // content query): the editor has no content query — collaborators get content
  // over Yjs, not the rendered-markdown endpoint.
  const requestAccessUrl = accessDeniedUrl(detail.error)
  if (requestAccessUrl) return <RequestDocumentAccess requestAccessUrl={requestAccessUrl} />
  if (detail.isError) return <ErrorState message="Could not load this document." />
  // Hold loading until the document resolves as editable for the current user;
  // a non-collaborator stays in loading through the redirect rather than flashing
  // the editor chrome.
  if (!data || !isCollaborator || !user) return <DocumentEditorSkeleton />

  const back = documentBackNavigation(returnTo)
  const currentUser = { id: user.id, displayName: user.display_name, picture: user.picture }
  const subscriptionBell = {
    workspaceId: data.workspace_id,
    options: SUBSCRIPTION_OPTIONS,
    manageUrl: "/notifications",
  }

  return (
    <div ref={containerRef} className="max-w-4xl w-full mx-auto">
      <DocumentEditorHeader
        documentId={documentId}
        back={back}
        metadata={data}
        onSharingChange={onSharingChange}
        savingTitle={savingTitle}
        titleEverChanged={titleEverChanged}
        subscriptionBell={subscriptionBell}
      />
      <div id="document-editor" className="max-w-3xl w-full mx-auto relative">
        <div className="pl-8 pr-12 space-y-2 relative">
          <DocumentEditorBody
            documentId={documentId}
            initialTitle={data.title}
            workspaceId={data.workspace_id}
            currentUser={currentUser}
            uploadUrl={data.upload_url}
            hasKlipy={!!clientConfig?.klipy_api_key}
          />
        </div>
      </div>
    </div>
  )
}
