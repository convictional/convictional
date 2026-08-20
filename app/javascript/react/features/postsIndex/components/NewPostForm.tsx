import { useNavigate } from "@tanstack/react-router"
import type React from "react"
import { useCallback, useEffect, useRef, useState } from "react"

import { LinkPreviewCard } from "~/react/composites/chat/LinkPreviewCard"
import { GifPicker, type KlipyGif } from "~/react/composites/editor/components/GifPicker"
import { RichTextComposer, type RichTextComposerHandle } from "~/react/composites/editor/RichTextComposer"
import { SearchablePicker } from "~/react/composites/SearchablePicker"
import type { PostDraft } from "~/react/features/postsIndex/types"
import { apiFetch } from "~/react/shared/apiFetch"
import { attachmentUploadUrl } from "~/react/shared/attachmentUrls"
import { useCurrentUser } from "~/react/shared/hooks/useCurrentUser"
import { useDropzone } from "~/react/shared/hooks/useDropzone"
import { useLinkPreviewUnfurl } from "~/react/shared/hooks/useLinkPreviewUnfurl"
import type { Group, Post } from "~/react/shared/types"
import { DropzoneOverlay } from "~/react/ui/DropzoneOverlay"
import { FLOATING_PORTAL_ROOT_ID } from "~/react/ui/floatingPortalRoot"
import { isBlankMarkdown } from "~/richText/schema"
import { showFlash } from "~/shared/flash"

// The post-body composer scopes uploads org-wide (no workspace). Mentions come
// from the shared organizationMembers store via RichTextComposer.
const UPLOAD_URL = attachmentUploadUrl()

interface NewPostFormProps {
  canAnnounce: boolean
  orgGroups: Group[]
  onCreated: (post: Post) => void
}

interface GroupSelection {
  group: Group | null
  isAnnouncement: boolean
}

function GroupAnnouncementDropdown({
  selection,
  orgGroups,
  canAnnounce,
  onChange,
}: {
  selection: GroupSelection
  orgGroups: Group[]
  canAnnounce: boolean
  onChange: (selection: GroupSelection) => void
}) {
  const label = selection.isAnnouncement ? "Announcement" : selection.group ? selection.group.name : "Everyone"

  const trigger = (
    <button type="button" className="btn join-item">
      <span className="material-symbols-outlined text-base">{selection.isAnnouncement ? "campaign" : "group"}</span>
      <span>{label}</span>
      <span className="material-symbols-outlined text-sm">keyboard_arrow_down</span>
    </button>
  )

  return (
    <SearchablePicker
      trigger={trigger}
      title="Audience"
      ariaLabel="Audience options"
      items={orgGroups}
      getKey={g => g.id}
      getSearchText={g => g.name}
      searchPlaceholder="Search groups…"
      renderHeader={close => (
        <div className="px-2">
          <button
            type="button"
            onClick={() => {
              onChange({ group: null, isAnnouncement: false })
              close()
            }}
            className="dropdown-item w-full text-left text-sm"
          >
            Everyone
          </button>
        </div>
      )}
      renderItem={(group, close) => (
        <button
          type="button"
          onClick={() => {
            onChange({ group, isAnnouncement: false })
            close()
          }}
          className="dropdown-item w-full text-left text-sm"
        >
          {group.name}
        </button>
      )}
      renderFooter={close =>
        canAnnounce ? (
          <div className="px-2">
            <button
              type="button"
              onClick={() => {
                onChange({ group: null, isAnnouncement: true })
                close()
              }}
              className="dropdown-item w-full text-left text-sm"
            >
              <div>Announcement</div>
              <div className="text-xs opacity-50">Everyone, even if unsubscribed</div>
            </button>
          </div>
        ) : null
      }
    />
  )
}

// The new-post composer: collapse/expand, title + document editor
// (RichTextComposer), GIF (Klipy-gated), group / announcement picker, live link
// preview (with dismiss → unfurl_links=false at submit), "Create sharable
// draft" + "Post".
export function NewPostForm({ canAnnounce, orgGroups, onCreated }: NewPostFormProps) {
  const navigate = useNavigate()
  const { clientConfig } = useCurrentUser()
  const klipyApiKey = clientConfig?.klipy_api_key ?? null

  const [expanded, setExpanded] = useState(false)
  const [title, setTitle] = useState("")
  const [selection, setSelection] = useState<GroupSelection>({ group: null, isAnnouncement: false })
  const [submitting, setSubmitting] = useState(false)
  // Remounting the editor after a successful post clears its content.
  const [editorKey, setEditorKey] = useState(0)
  const [draftContent, setDraftContent] = useState("")
  const editorRef = useRef<RichTextComposerHandle | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const editorAreaRef = useRef<HTMLDivElement>(null)

  // Dismissal remembers the last dismissed URL for the page session, so it
  // survives across posts (the page never reloads). Only one URL is remembered:
  // dismissing a second URL un-dismisses the first.
  const { composePreview, dismissComposePreview, isUrlDismissed } = useLinkPreviewUnfurl(draftContent)

  // Each time a preview arrives, fill the title only if it's blank. The
  // functional update keeps `title` out of the deps so user edits (including
  // clearing it) never retrigger a fill — only a new preview does. Capped at
  // the server's title limit (PostCreateRequest max_length=1000) so an
  // oversized og:title can't auto-fill a value the create endpoint rejects.
  useEffect(() => {
    const previewTitle = composePreview?.title
    if (!previewTitle) return
    setTitle(t => (t.trim() ? t : previewTitle.slice(0, 1000)))
  }, [composePreview])

  const showPicker = orgGroups.length > 0 || canAnnounce

  // The editor is a single line tall, but its wrapper reserves a roomy compose
  // area. Clicking that surrounding whitespace expands and focuses the editor so
  // the user can start typing without aiming at the placeholder. Only a click on
  // the bare wrapper counts — clicks on the editable place the caret themselves,
  // and clicks on the editor's inline UI (link tooltip, suggesters) manage their
  // own focus, so refocusing would steal it.
  function handleEditorAreaClick(e: React.MouseEvent) {
    setExpanded(true)
    if (e.target === editorAreaRef.current) editorRef.current?.focus()
  }

  // Emptiness is judged on the serialized content, not the editor's plain text —
  // a GIF-only body (an image node with no text) is real content and must not be
  // treated as empty (otherwise collapsing here would unmount the editor and drop
  // the just-inserted GIF, and handlePost would reject it as blank).
  const editorIsBlank = () => isBlankMarkdown(editorRef.current?.getContent() ?? "")

  const collapseIfEmpty = useCallback(() => {
    if (!title.trim() && editorIsBlank()) setExpanded(false)
  }, [title])

  // Collapse the empty composer when the user clicks away. The group/announcement
  // dropdown and GIF picker render in a floating portal *outside* containerRef, so
  // their clicks must be treated as inside the composer — otherwise picking a
  // group before typing would collapse the composer out from under the user.
  useEffect(() => {
    function handleDocumentClick(e: MouseEvent) {
      const target = e.target as Node
      if (containerRef.current?.contains(target)) return
      if (document.getElementById(FLOATING_PORTAL_ROOT_ID)?.contains(target)) return
      collapseIfEmpty()
    }
    document.addEventListener("click", handleDocumentClick)
    return () => document.removeEventListener("click", handleDocumentClick)
  }, [collapseIfEmpty])

  const handleSelectGif = useCallback((gif: KlipyGif) => {
    editorRef.current?.insertImage(gif.content_url, gif.title)
  }, [])

  // A drop anywhere on the composer card uploads into the editor. Expand first
  // so the (possibly collapsed) editor is visible as the upload lands.
  const { isDragOver, ref: dropzoneRef } = useDropzone({
    onFiles: files => {
      setExpanded(true)
      editorRef.current?.uploadFiles(files)
    },
  })
  // Stable so React doesn't detach/reattach the ref on every render.
  const setContainerRef = useCallback(
    (node: HTMLDivElement | null) => {
      containerRef.current = node
      dropzoneRef(node)
    },
    [dropzoneRef]
  )

  function buildBody(): { title: string; content: string; group_id?: string; is_announcement: boolean } {
    const content = editorRef.current?.getContent() ?? ""
    const body: { title: string; content: string; group_id?: string; is_announcement: boolean } = {
      title: title.trim(),
      content,
      is_announcement: selection.isAnnouncement,
    }
    if (selection.group) body.group_id = selection.group.id
    return body
  }

  function reset() {
    // Drop any pending debounced serialize first: the editor remount's
    // destroy() would otherwise flush stale markdown back into draftContent
    // after we clear it, resurrecting the link preview.
    editorRef.current?.cancelPendingChange()
    setDraftContent("")
    setTitle("")
    setSelection({ group: null, isAnnouncement: false })
    setExpanded(false)
    setEditorKey(k => k + 1)
  }

  async function handlePost() {
    if (submitting) return
    if (!title.trim()) {
      showFlash("Post title can't be blank.")
      return
    }
    if (editorIsBlank()) {
      showFlash("Post content can't be blank.")
      return
    }
    setSubmitting(true)
    try {
      // Judge dismissal against the freshly-serialized content, not the
      // hook's debounced flag — a Post click landing inside the onChange
      // debounce window could otherwise carry a stale verdict.
      const body = buildBody()
      const post = await apiFetch<Post>("/api/posts", {
        method: "POST",
        body: JSON.stringify({
          ...body,
          unfurl_links: !isUrlDismissed(body.content),
          attachment_claim_id: editorRef.current?.attachmentClaimId,
        }),
      })
      onCreated(post)
      reset()
      showFlash("Post has been created", "success")
    } catch {
      // Keep the content so the user can retry without retyping.
      showFlash("Couldn't create the post.")
    } finally {
      setSubmitting(false)
    }
  }

  async function handleCreateDraft() {
    if (submitting) return
    setSubmitting(true)
    try {
      // Drafts are blank-tolerant — no title/content validation.
      const draft = await apiFetch<PostDraft>("/api/posts/drafts", {
        method: "POST",
        body: JSON.stringify(buildBody()),
      })
      void navigate({ to: "/posts/$postId/edit", params: { postId: draft.id } })
    } catch {
      showFlash("Couldn't create the draft.")
      setSubmitting(false)
    }
  }

  return (
    <div className="max-w-4xl w-full mx-auto">
      <div ref={setContainerRef} className="bg-base-50 rounded-xl border border-base-300 shadow-xs relative">
        {isDragOver && <DropzoneOverlay compact={!expanded} />}
        {expanded && (
          <div className="absolute left-3 -top-3 dropdown-card rounded-lg inline-flex items-center px-2 py-1 shadow-sm">
            <span className="text-xs text-base-600/70 font-semibold">New Post</span>
          </div>
        )}
        <div
          className={`grid transition-[grid-template-rows] duration-200 ease-out ${
            expanded ? "grid-rows-[1fr]" : "grid-rows-[0fr]"
          }`}
        >
          <div className="overflow-hidden">
            <div className="p-4 pb-0">
              <input
                value={title}
                onChange={e => setTitle(e.target.value)}
                placeholder="Post title"
                aria-label="Post title"
                className="input w-full bg-transparent border-0 !rounded-none text-xl font-semibold focus:outline-none px-0 placeholder:text-base-400"
              />
            </div>
          </div>
        </div>
        {/* The editor is always mounted (collapsed just shrinks the area) so the
            collapsed placeholder is the editor's own placeholder, keeping its
            typography consistent. autoFocus is off so it doesn't grab focus on
            page load; clicking the area expands and focuses it. */}
        <div
          ref={editorAreaRef}
          className={expanded ? "px-4 min-h-40" : "px-4 py-0 min-h-0"}
          onClick={handleEditorAreaClick}
        >
          <RichTextComposer
            key={editorKey}
            ref={editorRef}
            initialContent=""
            uploadUrl={UPLOAD_URL}
            placeholder="Share your thoughts..."
            className="max-h-96 overflow-y-auto w-full focus:outline-hidden px-0 py-2 bg-transparent"
            autoFocus={false}
            onChange={setDraftContent}
            showDropCursor={false}
          />
        </div>
        {/* Inside containerRef (so dismissing doesn't count as an outside click
            and collapse the composer) but outside editorAreaRef (so card clicks
            don't run the editor-focus handler). */}
        {composePreview && (
          <div className="px-4 pb-2">
            <div className="relative max-w-lg">
              <LinkPreviewCard linkPreview={composePreview} onDismiss={dismissComposePreview} />
            </div>
          </div>
        )}
        <div
          className={`grid transition-[grid-template-rows] duration-200 ease-out ${
            expanded ? "grid-rows-[1fr]" : "grid-rows-[0fr]"
          }`}
        >
          <div className="overflow-hidden">
            <div className={`p-3 flex items-center justify-between ${expanded ? "border-t border-base-300" : ""}`}>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={handleCreateDraft}
                  disabled={submitting}
                  className="text-sm text-primary cursor-pointer pl-1"
                >
                  Create sharable draft
                </button>
              </div>
              <div className="flex items-center gap-2">
                {klipyApiKey && (
                  <GifPicker
                    klipyApiKey={klipyApiKey}
                    onSelectGif={handleSelectGif}
                    buttonClassName="btn-ghost btn-xs"
                  />
                )}
                <div className="join">
                  {showPicker && (
                    <GroupAnnouncementDropdown
                      selection={selection}
                      orgGroups={orgGroups}
                      canAnnounce={canAnnounce}
                      onChange={setSelection}
                    />
                  )}
                  <button
                    type="button"
                    onClick={handlePost}
                    disabled={submitting}
                    className="btn btn-primary join-item"
                  >
                    Post
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
