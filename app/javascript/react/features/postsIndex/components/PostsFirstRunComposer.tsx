import { useNavigate } from "@tanstack/react-router"
import { useEffect, useRef, useState } from "react"

import { LinkPreviewCard } from "~/react/composites/chat/LinkPreviewCard"
import { RichTextComposer, type RichTextComposerHandle } from "~/react/composites/editor/RichTextComposer"
import { ResourceBadge } from "~/react/composites/ResourceBadge"
import { SearchablePicker } from "~/react/composites/SearchablePicker"
import type { PostDraft } from "~/react/features/postsIndex/types"
import { apiFetch } from "~/react/shared/apiFetch"
import { attachmentUploadUrl } from "~/react/shared/attachmentUrls"
import { useLinkPreviewUnfurl } from "~/react/shared/hooks/useLinkPreviewUnfurl"
import type { Group, Post } from "~/react/shared/types"
import { EmptyStateSurface } from "~/react/ui/EmptyStateSurface"
import { isBlankMarkdown } from "~/richText/schema"
import { showFlash } from "~/shared/flash"

const UPLOAD_URL = attachmentUploadUrl()

interface PostsFirstRunComposerProps {
  canAnnounce: boolean
  orgGroups: Group[]
  onCreated: (post: Post) => void
}

interface GroupSelection {
  group: Group | null
  isAnnouncement: boolean
}

// Pill-triggered audience picker (the new rounded button style). Same behavior as the production
// composer's dropdown; kept local so the production NewPostForm is untouched.
function AudiencePill({
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
    <button type="button" className="btn rounded-full">
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

// The welcome-post builder (admins only). New teams adopting Convictional are usually leaving a
// sprawl of tools; the biggest adoption blocker is telling the team "where does X go now?". The
// builder lets the admin name the tools they're migrating off, then writes the pinned welcome
// announcement's "where things go now" map in those exact terms. The null path ("None of these")
// falls back to a generic map and fresh-start framing for teams that aren't migrating.
const WELCOME_TITLE = "Welcome to our new home base"

interface MapItem {
  label: string
  rest: string
}

interface MigrationTool {
  id: string
  chip: string
  item: MapItem
}

const MIGRATION_TOOLS: MigrationTool[] = [
  {
    id: "slack",
    chip: "Slack",
    item: { label: "Slack threads:", rest: "Chat for quick back and forth, Posts for anything worth keeping." },
  },
  {
    id: "notion",
    chip: "Notion",
    item: { label: "Notion pages:", rest: "Docs. Specs, notes, and anything we build on." },
  },
  {
    id: "gdocs",
    chip: "Google Docs",
    item: { label: "Google Docs:", rest: "Docs. Drafts and knowledge live here now." },
  },
  {
    id: "gmail",
    chip: "Gmail",
    item: { label: "Email and handoffs:", rest: "Inbox. Your mail and messages in one queue." },
  },
  {
    id: "linear",
    chip: "Linear",
    item: { label: "Plans and goals:", rest: "Goals. Every update ties back to the goal it moves." },
  },
]

const GENERIC_MAP: MapItem[] = [
  { label: "Announcements and updates:", rest: "Posts, like this one." },
  { label: "Day to day conversation:", rest: "Chat." },
  { label: "Specs, notes, knowledge:", rest: "Docs." },
  { label: "Email and handoffs:", rest: "Inbox." },
  { label: "What we're driving toward:", rest: "Goals." },
]

function buildWelcomeMarkdown(map: MapItem[], migrating: boolean): string {
  const intro = migrating
    ? "Hey team. We're moving our work into Convictional. This is where we'll talk, decide, and keep what matters, all in one place instead of scattered across a dozen tabs."
    : "Hey team. Convictional is our home base now: one place to talk, decide, and keep what matters, instead of it scattered across a dozen tabs."
  const closing = migrating
    ? "We'll keep our old tools around while we settle in, but let's make this the default. Ask me anything, right here."
    : "Let's make this the place our work happens. Ask me anything, right here."
  const mapLines = map.map(m => `- **${m.label}** ${m.rest}`).join("\n")
  const steps = [
    "1. Connect Gmail and your calendar from the inbox so nothing is missing.",
    '2. Open the doc titled "You should read this" to see how docs work.',
    "3. Say hi in the comments below so I know you're in.",
  ].join("\n")
  return [intro, "**Where things go now**", mapLines, "**Your first ten minutes**", steps, closing].join("\n\n")
}

function ChipTick({ on }: { on: boolean }) {
  return (
    <span
      className={`flex h-4 w-4 items-center justify-center rounded-full border ${on ? "border-primary bg-primary text-white" : "border-base-400"}`}
    >
      {on && <span className="material-symbols-outlined text-[11px] leading-none">check</span>}
    </span>
  )
}

function WelcomeBuilder({ onApply }: { onApply: (markdown: string) => void }) {
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [none, setNone] = useState(false)

  const migrating = selected.size > 0
  const map = migrating ? MIGRATION_TOOLS.filter(t => selected.has(t.id)).map(t => t.item) : GENERIC_MAP

  // Tool chips and the null chip are mutually exclusive: picking a tool clears "None",
  // and picking "None" clears the tools.
  function toggleTool(id: string) {
    setNone(false)
    setSelected(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function toggleNone() {
    setNone(value => !value)
    setSelected(new Set())
  }

  const chipClass = (on: boolean) =>
    `inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-sm font-medium shadow-xs ${
      on ? "border-primary bg-primary/10 text-primary" : "border-base-300 bg-base-100 text-base-700"
    }`

  return (
    <EmptyStateSurface className="mt-4 p-4">
      <h2 className="font-accent text-lg text-base-content">Welcome your team</h2>
      <p className="mt-0.5 text-sm text-base-content/60 text-pretty">
        Publish a pinned announcement that greets everyone and shows where work goes now. Tell us what you&rsquo;re
        moving off of and we&rsquo;ll write the map in tools they already know. Not coming from these? That&rsquo;s
        fine too.
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        {MIGRATION_TOOLS.map(tool => {
          const on = selected.has(tool.id)
          return (
            <button key={tool.id} type="button" onClick={() => toggleTool(tool.id)} className={chipClass(on)}>
              <ChipTick on={on} />
              {tool.chip}
            </button>
          )
        })}
        <button type="button" onClick={toggleNone} className={chipClass(none)}>
          <ChipTick on={none} />
          None of these
        </button>
      </div>
      <div className="mt-4 flex justify-end">
        <button
          type="button"
          onClick={() => onApply(buildWelcomeMarkdown(map, migrating))}
          className="btn btn-primary rounded-full"
        >
          <span className="material-symbols-outlined text-base">campaign</span>
          Use in a welcome post
        </button>
      </div>
    </EmptyStateSurface>
  )
}

// The first-run composer: the production NewPostForm reframed as a single welcoming panel that
// teaches what posts are for and puts the composer at its center. Shown only when the org has no
// posts yet (see PostsIndex), and deliberately a separate component so NewPostForm stays untouched.
export function PostsFirstRunComposer({ canAnnounce, orgGroups, onCreated }: PostsFirstRunComposerProps) {
  const navigate = useNavigate()
  const [title, setTitle] = useState("")
  const [selection, setSelection] = useState<GroupSelection>({ group: null, isAnnouncement: false })
  const [submitting, setSubmitting] = useState(false)
  const [editorKey, setEditorKey] = useState(0)
  const [draftContent, setDraftContent] = useState("")
  const [initialContent, setInitialContent] = useState("")
  // Set when the composer was filled from the welcome builder; drives the auto-pin on publish.
  const [pinAfterCreate, setPinAfterCreate] = useState(false)
  const editorRef = useRef<RichTextComposerHandle | null>(null)
  const composerRef = useRef<HTMLDivElement | null>(null)

  const { composePreview, dismissComposePreview, isUrlDismissed } = useLinkPreviewUnfurl(draftContent)

  // Fill the title from a link preview only while it's blank (matches NewPostForm).
  useEffect(() => {
    const previewTitle = composePreview?.title
    if (!previewTitle) return
    setTitle(t => (t.trim() ? t : previewTitle.slice(0, 1000)))
  }, [composePreview])

  const showPicker = orgGroups.length > 0 || canAnnounce
  const editorIsBlank = () => isBlankMarkdown(editorRef.current?.getContent() ?? "")

  function buildBody(): { title: string; content: string; group_id?: string; is_announcement: boolean } {
    const body = {
      title: title.trim(),
      content: editorRef.current?.getContent() ?? "",
      is_announcement: selection.isAnnouncement,
    } as { title: string; content: string; group_id?: string; is_announcement: boolean }
    if (selection.group) body.group_id = selection.group.id
    return body
  }

  function reset() {
    editorRef.current?.cancelPendingChange()
    setDraftContent("")
    setInitialContent("")
    setTitle("")
    setSelection({ group: null, isAnnouncement: false })
    setPinAfterCreate(false)
    setEditorKey(k => k + 1)
  }

  // Load the generated welcome post into the composer: fill the title and body, preset the audience
  // to Announcement, and remember to pin it on publish. Remounts the editor (bumped key) so it parses
  // the new markdown, matching reset()'s remount-to-refresh pattern.
  function applyWelcome(markdown: string) {
    editorRef.current?.cancelPendingChange()
    setTitle(WELCOME_TITLE)
    setSelection({ group: null, isAnnouncement: true })
    setInitialContent(markdown)
    setDraftContent(markdown)
    setPinAfterCreate(true)
    setEditorKey(k => k + 1)
    composerRef.current?.scrollIntoView({ behavior: "smooth", block: "start" })
  }

  async function handlePost() {
    if (submitting) return
    if (!title.trim()) return showFlash("Post title can't be blank.")
    if (editorIsBlank()) return showFlash("Post content can't be blank.")
    setSubmitting(true)
    try {
      const body = buildBody()
      const post = await apiFetch<Post>("/api/posts", {
        method: "POST",
        body: JSON.stringify({
          ...body,
          unfurl_links: !isUrlDismissed(body.content),
          attachment_claim_id: editorRef.current?.attachmentClaimId,
        }),
      })
      // A welcome post is meant to be pinned; pin it after create. Non-fatal if it fails —
      // the post still exists and can be pinned from its menu.
      if (pinAfterCreate) {
        try {
          await apiFetch(`/api/posts/${post.id}/pin`, { method: "PATCH", body: JSON.stringify({ pinned: true }) })
        } catch {
          showFlash("Post created, but couldn't pin it. You can pin it from the post menu.")
        }
      }
      const wasWelcome = pinAfterCreate
      onCreated(post)
      reset()
      showFlash(wasWelcome ? "Welcome post published and pinned" : "Post has been created", "success")
    } catch {
      showFlash("Couldn't create the post.")
    } finally {
      setSubmitting(false)
    }
  }

  async function handleCreateDraft() {
    if (submitting) return
    setSubmitting(true)
    try {
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
    <div className="mx-auto max-w-3xl">
      {/* The open composer leads; the teaching (or welcome builder) sits beneath it. */}
      <div ref={composerRef} className="w-full rounded-2xl border border-base-300 bg-base-50 shadow-xs">
        <div className="px-4 pt-4">
          <input
            value={title}
            onChange={e => setTitle(e.target.value)}
            placeholder="Post title"
            aria-label="Post title"
            className="w-full border-0 bg-transparent px-0 text-xl font-accent placeholder:text-base-500 focus:outline-none"
            autoFocus
          />
        </div>
        <div className="px-4">
          <RichTextComposer
            key={editorKey}
            ref={editorRef}
            initialContent={initialContent}
            uploadUrl={UPLOAD_URL}
            placeholder="Share your thoughts..."
            className="max-h-96 min-h-24 w-full overflow-y-auto bg-transparent px-0 pt-1 pb-2 focus:outline-hidden"
            autoFocus={false}
            onChange={setDraftContent}
            showDropCursor={false}
          />
        </div>
        {composePreview && (
          <div className="px-4 pb-2">
            <div className="relative max-w-lg">
              <LinkPreviewCard linkPreview={composePreview} onDismiss={dismissComposePreview} />
            </div>
          </div>
        )}
        <div className="mt-2 flex items-center justify-between border-t border-base-300 p-3">
          <button
            type="button"
            onClick={handleCreateDraft}
            disabled={submitting}
            className="cursor-pointer pl-1 text-sm text-primary"
          >
            Create sharable draft
          </button>
          <div className="flex items-center gap-2">
            {showPicker && (
              <AudiencePill
                selection={selection}
                orgGroups={orgGroups}
                canAnnounce={canAnnounce}
                onChange={setSelection}
              />
            )}
            <button type="button" onClick={handlePost} disabled={submitting} className="btn btn-primary rounded-full">
              Post
            </button>
          </div>
        </div>
      </div>

      {/* Admins (canAnnounce) get the welcome-post builder; everyone else gets the plain teaching prompt. */}
      {canAnnounce ? (
        <WelcomeBuilder onApply={applyWelcome} />
      ) : (
        <EmptyStateSurface className="mt-4 flex items-start gap-3 p-4">
          <ResourceBadge contentType="post" size="small" />
          <div>
            <h2 className="font-accent text-lg text-base-content">Start your team&rsquo;s record</h2>
            <p className="mt-0.5 text-sm text-base-content/60 text-pretty">
              Permanent, searchable, and decidable. Write your first post.
            </p>
            <p className="mt-2 text-xs text-base-content/50">
              Want people to weigh in?{" "}
              <a href="/organization/users" className="font-semibold text-primary hover:underline">
                Invite your team
              </a>
            </p>
          </div>
        </EmptyStateSurface>
      )}
    </div>
  )
}
