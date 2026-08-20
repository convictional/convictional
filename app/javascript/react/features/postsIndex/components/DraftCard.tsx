import { Link } from "@tanstack/react-router"

import { AvatarGroup } from "~/react/composites/AvatarGroup"
import { MailboxStateBadge } from "~/react/composites/MailboxStateBadge"
import type { PostDraft } from "~/react/features/postsIndex/types"
import { DateTime } from "~/react/ui/DateTime"

// Draft card: title, an optional "Shared with me" badge (derived from creator vs
// the current user, not a server flag), last-edited datetime, and collaborator
// avatars. Links to the draft editor; `returnTo` is the index URL stamped onto
// the editor's back link.
export function DraftCard({
  draft,
  currentUserId,
  returnTo,
}: {
  draft: PostDraft
  currentUserId: string | null
  returnTo: string
}) {
  const isShared = currentUserId !== null && draft.creator.id !== currentUserId

  return (
    <li className="hover:bg-base-50 transition">
      <Link to="/posts/$postId/edit" params={{ postId: draft.id }} search={{ return_to: returnTo }}>
        <div className="px-2 py-2 space-y-0.5">
          <h2 className="font-accent text-lg line-clamp-2">{draft.title}</h2>
          <p className="text-xs text-base-500">
            {isShared && (
              <>
                <MailboxStateBadge variant="shared" /> by{" "}
                <span className="text-primary">@{draft.creator.display_name}</span> &middot;{" "}
              </>
            )}
            Last edited <DateTime datetime={draft.updated_at} format="relative" />
          </p>
          <div className="flex items-center gap-3 text-xs text-base-500">
            <AvatarGroup users={draft.collaborators} layout="stack" size="small" max={3} withHoverCard />
          </div>
        </div>
      </Link>
    </li>
  )
}
