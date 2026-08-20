import { getRouteApi, useNavigate } from "@tanstack/react-router"
import { useCallback, useEffect, useRef, useState } from "react"

import { ApiError, apiFetch } from "~/react/shared/apiFetch"
import { useCurrentUser } from "~/react/shared/hooks/useCurrentUser"
import { useDocumentTitle } from "~/react/shared/hooks/useDocumentTitle"
import { useWorkspaceVisitRecording } from "~/react/shared/hooks/useVisitRecording"
import { postBackNavigation, postNavigationSearch } from "~/react/shared/postNavigation"
import { ErrorState } from "~/react/ui/ErrorState"
import { LoadingState } from "~/react/ui/LoadingState"
import { showFlash } from "~/shared/flash"

import { PostDraftEditorBody } from "./PostDraftEditorBody"
import { PostDraftEditorHeader } from "./PostDraftEditorHeader"
import type { PostDraftMetadata } from "./types"

// The route id carries the pathless shell parent prefix (shellRoute has id
// "shell"), so the typed accessor is addressed as "/shell/posts/$postId/edit".
const routeApi = getRouteApi("/shell/posts/$postId/edit")

export function PostDraftEditor() {
  const { postId } = routeApi.useParams()
  const { return_to: returnTo, mailbox_entry_id: mailboxEntryId } = routeApi.useSearch()
  const navigate = useNavigate()
  const { user, clientConfig } = useCurrentUser()

  const containerRef = useRef<HTMLDivElement>(null)
  const [metadata, setMetadata] = useState<PostDraftMetadata | null>(null)
  const [loadFailed, setLoadFailed] = useState(false)
  const [savingTitle, setSavingTitle] = useState(false)
  const [titleEverChanged, setTitleEverChanged] = useState(false)
  const [publishing, setPublishing] = useState(false)
  // Synchronous in-flight guard: state updates are async, so two ⌘↵ presses (or a
  // click + ⌘↵) firing before the next render would both pass a `publishing`-state
  // check and POST twice. A ref flips immediately.
  const publishingRef = useRef(false)

  useDocumentTitle(metadata?.title ?? "Draft")

  useEffect(() => {
    // Reset per-post view state: this is a long-lived client route, so navigating
    // between drafts must not surface the previous draft or leave a stale error.
    setMetadata(null)
    setLoadFailed(false)
    const controller = new AbortController()
    let stale = false
    const draftUrl = mailboxEntryId
      ? `/api/posts/${postId}/draft?mailbox_entry_id=${encodeURIComponent(mailboxEntryId)}`
      : `/api/posts/${postId}/draft`
    ;(async () => {
      try {
        const data = await apiFetch<PostDraftMetadata>(draftUrl, { signal: controller.signal })
        if (!stale) setMetadata(data)
      } catch (err) {
        if (stale || (err instanceof DOMException && err.name === "AbortError")) return
        // The draft endpoint 404s for BOTH a published post and a
        // nonexistent/inaccessible one. A published post lives at the show page,
        // so confirm via the show endpoint — its exact inverse: it 200s published
        // posts and 404s drafts — and redirect there; a genuine 404 falls through
        // to the error state. This positive-signal check is what keeps the
        // show⇄edit redirect pair from ping-ponging on a nonexistent post now that
        // both are SPA routes (show sends any 404 here). replace() keeps the
        // editor URL out of history.
        if (err instanceof ApiError && err.status === 404) {
          try {
            await apiFetch(`/api/posts/${postId}`, { signal: controller.signal })
          } catch {
            if (!stale) setLoadFailed(true)
            return
          }
          if (stale) return
          void navigate({
            to: "/posts/$postId",
            params: { postId },
            search: postNavigationSearch(returnTo, mailboxEntryId),
            replace: true,
          })
          return
        }
        if (!stale) setLoadFailed(true)
      }
    })()
    return () => {
      stale = true
      controller.abort()
    }
  }, [postId, mailboxEntryId, returnTo, navigate])

  // Record the workspace visit once, when the draft metadata loads.
  const recordVisit = useWorkspaceVisitRecording(metadata?.workspace_id ?? null)
  const trackedVisitRef = useRef(false)
  useEffect(() => {
    if (!metadata || trackedVisitRef.current) return
    trackedVisitRef.current = true
    recordVisit()
  }, [metadata, recordVisit])

  // TitleInput dispatches bubbling "unsaved"/"saved" events when a debounced
  // PATCH starts/completes — same bridge the documents editor uses to drive its
  // header save indicator without coupling the header to TitleInput's internals.
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

  const publish = useCallback(async () => {
    if (publishingRef.current) return
    publishingRef.current = true
    setPublishing(true)
    try {
      await apiFetch(`/api/posts/${postId}/publish`, { method: "POST" })
      void navigate({ to: "/posts/$postId", params: { postId } })
    } catch (error) {
      publishingRef.current = false
      setPublishing(false)
      // Publish 422s carry a user-facing reason (missing title / empty content).
      const detail = error instanceof ApiError ? (error.body?.detail as string | undefined) : undefined
      showFlash(detail ?? "Couldn't publish this post. Please try again.")
    }
  }, [postId, navigate])

  // ⌘↵ / Ctrl↵ publishes from anywhere in the editor. Blur first so the editor's
  // pending title/content saves flush before we read the document for publishing.
  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
        event.preventDefault()
        ;(document.activeElement as HTMLElement | null)?.blur()
        void publish()
      }
    }
    el.addEventListener("keydown", onKeyDown)
    return () => el.removeEventListener("keydown", onKeyDown)
  }, [publish])

  const back = postBackNavigation(returnTo, mailboxEntryId)
  const currentUser = user ? { id: user.id, displayName: user.display_name, picture: user.picture } : null

  return (
    <div ref={containerRef} className="max-w-4xl w-full mx-auto relative">
      <PostDraftEditorHeader
        postId={postId}
        back={back}
        metadata={metadata}
        onMetadataChange={setMetadata}
        savingTitle={savingTitle}
        titleEverChanged={titleEverChanged}
        publishing={publishing}
        onPublish={publish}
      />
      {/* id="post-draft" anchors useCommentPositioning's sticky-header lookup
          (it matches "#document-editor, #post-draft"); without it draft comment
          cards don't clamp below the header on scroll. */}
      <div id="post-draft" className="pl-8 pr-12 space-y-2 relative">
        {metadata && currentUser ? (
          <PostDraftEditorBody
            postId={postId}
            initialTitle={metadata.title}
            currentUser={currentUser}
            uploadUrl={metadata.upload_url}
            initialContent={null}
            hasKlipy={!!clientConfig?.klipy_api_key}
          />
        ) : loadFailed ? (
          <ErrorState message="Could not load this draft." />
        ) : (
          <LoadingState className="py-8" />
        )}
      </div>
    </div>
  )
}
