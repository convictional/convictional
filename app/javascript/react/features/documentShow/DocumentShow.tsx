import { useQuery } from "@tanstack/react-query"
import { getRouteApi, useNavigate } from "@tanstack/react-router"
import { useEffect, useRef } from "react"

import { AvatarGroup } from "~/react/composites/AvatarGroup"
import { BackButton } from "~/react/composites/BackButton"
import { Markdown } from "~/react/composites/markdown/Markdown"
import { RequestDocumentAccess } from "~/react/composites/RequestDocumentAccess"
import { accessDeniedUrl } from "~/react/shared/apiFetch"
import { useDocumentTitle } from "~/react/shared/hooks/useDocumentTitle"
import { useWorkspaceVisitRecording } from "~/react/shared/hooks/useVisitRecording"
import { safeReturnTo } from "~/react/shared/returnTo"
import {
  documentBackNavigation,
  documentContentQueryOptions,
  documentQueryOptions,
} from "~/react/shared/stores/documents"
import { DateTime } from "~/react/ui/DateTime"
import { ErrorState } from "~/react/ui/ErrorState"
import { StickyHeader } from "~/react/ui/StickyHeader"
import { DocumentShowSkeleton } from "./DocumentShowSkeleton"

// The route id carries the pathless shell parent prefix (shellRoute has id
// "shell"), so the typed accessor is addressed as "/shell/documents/$documentId".
const routeApi = getRouteApi("/shell/documents/$documentId")

export function DocumentShow() {
  const { documentId } = routeApi.useParams()
  const { return_to: returnTo } = routeApi.useSearch()
  const navigate = useNavigate()

  const detail = useQuery(documentQueryOptions(documentId))
  const content = useQuery(documentContentQueryOptions(documentId))

  const data = detail.data
  useDocumentTitle(data?.title ?? "Document")

  // Collaborators don't get the read-only view — they edit, so redirect once the
  // detail query resolves. replace() keeps the show page out of history so Back
  // doesn't bounce through it.
  const isCollaborator = data?.is_collaborator ?? false
  useEffect(() => {
    if (!isCollaborator) return
    const safe = safeReturnTo(returnTo)
    void navigate({
      to: "/documents/$documentId/edit",
      params: { documentId },
      search: safe ? { return_to: safe } : {},
      replace: true,
    })
  }, [isCollaborator, documentId, returnTo, navigate])

  // Record the workspace visit once the read-only view loads. Collaborators are
  // redirected to the editor, which records its own visit — don't double-count.
  const recordVisit = useWorkspaceVisitRecording(data?.workspace_id ?? null)
  const trackedVisitRef = useRef(false)
  useEffect(() => {
    if (!data || isCollaborator || trackedVisitRef.current) return
    trackedVisitRef.current = true
    recordVisit()
  }, [data, isCollaborator, recordVisit])

  // A viewer who can't access the document gets a 403 from the API carrying the
  // request-access URL (see request_access_handler). Offer that path rather than
  // a dead-end error — this is the read-only counterpart to the editor's own
  // request-access flow.
  const requestAccessUrl = accessDeniedUrl(detail.error) ?? accessDeniedUrl(content.error)

  // Hold loading through the collaborator redirect first, so a transient error on
  // either query can't flash the read-only error state before the page swaps.
  if (isCollaborator) return <DocumentShowSkeleton />
  if (requestAccessUrl) return <RequestDocumentAccess requestAccessUrl={requestAccessUrl} />
  if (detail.isError || content.isError) return <ErrorState message="Could not load this document." />
  if (!data || content.data == null) return <DocumentShowSkeleton />

  const back = documentBackNavigation(returnTo)
  const markdown = content.data.markdown

  return (
    <div className="max-w-4xl w-full mx-auto">
      <StickyHeader>
        <div className="flex items-center justify-between gap-2 p-2">
          <BackButton back={back} navLink />
          <div className="flex items-center gap-2">
            {data.collaborators.length > 0 && <AvatarGroup layout="stack" users={data.collaborators} max={5} />}
            <a
              href={data.request_access_url}
              className="btn btn-primary"
              aria-label="Request editing"
              data-testid="request-collaborator-editing"
            >
              <span className="material-symbols-outlined text-lg">person_add</span>
              <span className="hidden sm:inline">Request editing</span>
            </a>
          </div>
        </div>
      </StickyHeader>
      <div className="max-w-3xl mx-auto pl-8 pr-12 space-y-4">
        <h1 className="text-3xl font-accent truncate" title={data.title}>
          {data.title}
        </h1>
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-base-500">
          <span className="whitespace-nowrap">
            by <span className="text-primary">@{data.creator.display_name}</span>
          </span>
          <span className="whitespace-nowrap">
            &middot; Last edited <DateTime datetime={data.updated_at} format="relative" />
          </span>
        </div>
        {markdown ? (
          <Markdown source={markdown} />
        ) : (
          <p className="text-base-500 italic">This document has no content yet.</p>
        )}
      </div>
    </div>
  )
}
