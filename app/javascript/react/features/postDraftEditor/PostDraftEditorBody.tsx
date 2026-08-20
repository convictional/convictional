import { useRef } from "react"

import { CommentSystem } from "~/react/composites/editor/components/comments/CommentSystem"
import { EditorFeatureOverlays } from "~/react/composites/editor/components/EditorFeatureOverlays"
import { ZenEditorLayout } from "~/react/composites/editor/components/ZenEditorLayout"
import { CommentStoreProvider } from "~/react/composites/editor/features/comments/CommentStoreContext"
import { useCommentThreads } from "~/react/composites/editor/features/comments/commentThreads"
import { CommentThreadsProvider } from "~/react/composites/editor/features/comments/CommentThreadsContext"
import { useClearActiveCommentWhenGone } from "~/react/composites/editor/features/comments/useClearActiveCommentWhenGone"
import { useComments } from "~/react/composites/editor/features/comments/useComments"
import { useCollaboration } from "~/react/composites/editor/features/useCollaboration"
import { useCommonFeatures } from "~/react/composites/editor/features/useCommonFeatures"
import { useViewRef } from "~/react/composites/editor/features/useViewRef"
import { useChannelsClient } from "~/react/shared/hooks/useChannelsClient"
import { useCurrentUser } from "~/react/shared/hooks/useCurrentUser"
import { ChannelEventResource, ChannelStream } from "~/types/channels"

import { postDraftCommentsPath, postDraftCommentUIStore } from "./store"

export interface PostDraftEditorBodyProps {
  postId: string
  initialTitle: string
  currentUser: { id: string; displayName: string; picture?: string | null }
  uploadUrl: string | null
  initialContent: string | null
  hasKlipy: boolean
}

export function PostDraftEditorBody({
  postId,
  initialTitle,
  currentUser,
  uploadUrl,
  initialContent,
  hasKlipy,
}: PostDraftEditorBodyProps) {
  const klipyApiKey = useCurrentUser().clientConfig?.klipy_api_key ?? null
  const containerRef = useRef<HTMLDivElement>(null)
  const channelsClient = useChannelsClient()
  // Post-draft mentions are org-wide (no collaborator split), matching the
  // previous /workspaces/collaborators/available behaviour for body and comments.
  const commonFeatures = useCommonFeatures({ uploadUrl })
  const { viewRef, plugin: viewRefPlugin } = useViewRef()

  const collaboration = useCollaboration({
    channelsClient,
    stream: ChannelStream.POST_DRAFT,
    params: { post_id: postId },
    currentUser,
    initialContent,
  })
  const comments = useComments({
    containerRef,
    currentUser,
    mentionableUsers: commonFeatures.mentionableUsers,
  })
  const commentThreads = useCommentThreads({
    commentsPath: postDraftCommentsPath,
    resourceId: postId,
    channel: { stream: ChannelStream.POST_DRAFT_COMMENTS, params: { post_id: postId } },
    commentResource: ChannelEventResource.POST_DRAFT_COMMENT,
    uiStore: postDraftCommentUIStore,
  })
  useClearActiveCommentWhenGone(commentThreads.threads, postDraftCommentUIStore)

  if (!collaboration.ready) return null

  return (
    <CommentStoreProvider value={postDraftCommentUIStore}>
      <CommentThreadsProvider value={commentThreads}>
        <ZenEditorLayout
          containerRef={containerRef}
          features={[collaboration, ...commonFeatures.features, comments, { plugins: [viewRefPlugin] }]}
          docSynced={collaboration.docSynced}
          attachments={commonFeatures.attachments}
          viewRef={viewRef}
          toolbar={{ hasKlipy, klipyApiKey, portalId: "draft-toolbar-target" }}
          syncStatus={{
            status: collaboration.status,
            docSynced: collaboration.docSynced,
            portalId: "draft-sync-status-target",
          }}
          title={{
            saveUrl: `/api/posts/${postId}/draft`,
            initialTitle,
            placeholder: "Post title",
            autoSelectTitle: "Untitled draft",
          }}
        >
          <EditorFeatureOverlays bundle={commonFeatures} />
          <CommentSystem {...comments.state} />
        </ZenEditorLayout>
      </CommentThreadsProvider>
    </CommentStoreProvider>
  )
}
