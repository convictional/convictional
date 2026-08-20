import type { RefObject } from "react"

import { pendingCommentPlugin } from "~/react/composites/editor/features/comments/pendingCommentDecoration"
import type { EditorFeature } from "~/react/composites/editor/types"
import type { MentionUser } from "~/react/shared/hooks/useMentionableUsers"

export interface CommentSystemProps {
  containerRef: RefObject<HTMLDivElement | null>
  currentUser: { id: string; displayName: string; picture?: string | null }
  mentionableUsers: MentionUser[]
}

export interface CommentFeature extends EditorFeature {
  state: CommentSystemProps
}

export function useComments(options: CommentSystemProps): CommentFeature {
  return { plugins: [pendingCommentPlugin], state: options }
}
