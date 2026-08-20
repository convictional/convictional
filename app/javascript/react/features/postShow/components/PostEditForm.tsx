import { useRef, useState } from "react"

import { RichTextComposer, type RichTextComposerHandle } from "~/react/composites/editor/RichTextComposer"
import { apiFetch } from "~/react/shared/apiFetch"
import { attachmentUploadUrl } from "~/react/shared/attachmentUrls"
import { useOrganizationMembers } from "~/react/shared/hooks/useOrganizationMembers"
import type { Group, Post } from "~/react/shared/types"
import { Dropdown } from "~/react/ui/Dropdown"
import { showFlash } from "~/shared/flash"

interface PostEditFormProps {
  post: Post
  // The post body markdown (the original comment's content), edited separately
  // from the post since the body lives on the original comment.
  initialContent: string
  // Returns the updated post plus the saved body content (PATCH returns only the
  // post, so the caller reflects the new body from the editor).
  onSave: (post: Post, content: string) => void
  onCancel: () => void
}

function GroupSelect({
  groups,
  value,
  onChange,
}: {
  groups: Group[]
  value: Group | null
  onChange: (group: Group | null) => void
}) {
  return (
    <Dropdown
      placement="bottom-start"
      className="dropdown-card w-56 z-50"
      trigger={
        <button type="button" className="cursor-pointer flex items-center gap-1">
          <span className={`text-sm ${value ? "text-primary" : "text-base-content/40"}`}>
            {value ? `@${value.name}` : "No group"}
          </span>
        </button>
      }
    >
      {({ close }) => (
        <ul className="p-2 max-h-60 overflow-y-auto grid gap-1">
          <li>
            <button
              type="button"
              onClick={() => {
                onChange(null)
                close()
              }}
              className="dropdown-item p-1 w-full text-left"
            >
              <span className="text-xs font-semibold text-base-content/60">No group</span>
            </button>
          </li>
          {groups.map(group => (
            <li key={group.id}>
              <button
                type="button"
                onClick={() => {
                  onChange(group)
                  close()
                }}
                className="dropdown-item p-1 w-full text-left"
              >
                <span className="text-xs font-semibold truncate">{group.name}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </Dropdown>
  )
}

// Edit-in-place for the post body: title + group + rich-text content, saved in a
// single PATCH /api/posts/{id}. Org groups come from the shared
// organizationMembers store (no new server surface).
export function PostEditForm({ post, initialContent, onSave, onCancel }: PostEditFormProps) {
  const [title, setTitle] = useState(post.title)
  const [group, setGroup] = useState<Group | null>(post.group)
  const { groups } = useOrganizationMembers()
  const [saving, setSaving] = useState(false)
  const editorRef = useRef<RichTextComposerHandle | null>(null)

  async function handleSave() {
    const trimmedTitle = title.trim()
    if (!trimmedTitle) {
      showFlash("Title can't be blank.")
      return
    }
    const content = editorRef.current?.getContent() ?? ""
    if (editorRef.current?.isEmpty()) {
      showFlash("Post content can't be blank.")
      return
    }
    const body: Record<string, unknown> = {
      title: trimmedTitle,
      content,
      attachment_claim_id: editorRef.current?.attachmentClaimId,
    }
    if (group) body.group_id = group.id
    else if (post.group) body.clear_group_id = true

    setSaving(true)
    try {
      const updated = await apiFetch<Post>(`/api/posts/${post.id}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      })
      onSave(updated, content)
    } catch {
      showFlash("Couldn't save the post.")
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-2">
      <div className="pt-5 px-8">
        <input
          type="text"
          value={title}
          onChange={e => setTitle(e.target.value)}
          placeholder="Title"
          aria-label="Post title"
          className="input w-full bg-transparent border-0 !rounded-none text-xl font-accent focus:outline-none px-0 placeholder:text-base-400"
          autoFocus
        />
        <GroupSelect groups={groups} value={group} onChange={setGroup} />
      </div>
      <div className="px-8">
        <RichTextComposer ref={editorRef} initialContent={initialContent} uploadUrl={attachmentUploadUrl()} />
      </div>
      <div className="px-8 py-3 flex items-center justify-end gap-2 border-t border-base-300">
        <button type="button" className="btn btn-ghost" onClick={onCancel}>
          Cancel
        </button>
        <button type="button" className="btn btn-primary" disabled={saving} onClick={handleSave}>
          Save changes
        </button>
      </div>
    </div>
  )
}
