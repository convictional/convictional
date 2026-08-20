import { useRef } from "react"

import { CommentSystem } from "~/react/composites/editor/components/comments/CommentSystem"
import { EditorFeatureOverlays } from "~/react/composites/editor/components/EditorFeatureOverlays"
import { ZenEditorLayout } from "~/react/composites/editor/components/ZenEditorLayout"
import { collapsibleHeadingsPlugin } from "~/react/composites/editor/features/collapsibleHeadings"
import { CommentStoreProvider } from "~/react/composites/editor/features/comments/CommentStoreContext"
import { useCommentThreads } from "~/react/composites/editor/features/comments/commentThreads"
import { CommentThreadsProvider } from "~/react/composites/editor/features/comments/CommentThreadsContext"
import { DecisionsProvider } from "~/react/composites/editor/features/comments/DecisionsContext"
import { useClearActiveCommentWhenGone } from "~/react/composites/editor/features/comments/useClearActiveCommentWhenGone"
import { useComments } from "~/react/composites/editor/features/comments/useComments"
import { useCollaboration } from "~/react/composites/editor/features/useCollaboration"
import { useCommonFeatures } from "~/react/composites/editor/features/useCommonFeatures"
import { useViewRef } from "~/react/composites/editor/features/useViewRef"
import { useChannelsClient } from "~/react/shared/hooks/useChannelsClient"
import { useCurrentUser } from "~/react/shared/hooks/useCurrentUser"
import { useDecisions } from "~/react/shared/hooks/useDecisions"
import { ChannelEventResource, ChannelStream } from "~/types/channels"

import { documentCommentsPath, documentCommentUIStore } from "./store"

export interface DocumentEditorBodyProps {
  documentId: string
  initialTitle: string
  workspaceId: string
  currentUser: { id: string; displayName: string; picture?: string | null }
  // The document show response always carries a resolved upload URL (the
  // bundle's uploadUrl still accepts null for editors that have none).
  uploadUrl: string
  hasKlipy: boolean
}

export function DocumentEditorBody({
  documentId,
  initialTitle,
  workspaceId,
  currentUser,
  uploadUrl,
  hasKlipy,
}: DocumentEditorBodyProps) {
  const klipyApiKey = useCurrentUser().clientConfig?.klipy_api_key ?? null
  const containerRef = useRef<HTMLDivElement>(null)
  const channelsClient = useChannelsClient()
  // Document mentions are org-wide (no collaborator split), matching the
  // previous /workspaces/collaborators/available behaviour for body and comments.
  const commonFeatures = useCommonFeatures({ uploadUrl })
  const { viewRef, plugin: viewRefPlugin } = useViewRef()

  const collaboration = useCollaboration({
    channelsClient,
    stream: ChannelStream.DOCUMENT,
    params: { document_id: documentId },
    currentUser,
    // Content always arrives over Yjs; documents are never seeded from a prop.
    initialContent: null,
  })
  const comments = useComments({
    containerRef,
    currentUser,
    mentionableUsers: commonFeatures.mentionableUsers,
  })
  const commentThreads = useCommentThreads({
    commentsPath: documentCommentsPath,
    resourceId: documentId,
    channel: { stream: ChannelStream.DOCUMENT_COMMENTS, params: { document_id: documentId } },
    commentResource: ChannelEventResource.DOCUMENT_COMMENT,
    uiStore: documentCommentUIStore,
  })
  useClearActiveCommentWhenGone(commentThreads.threads, documentCommentUIStore)
  // Decisions ride the workspace_events topic (independent of the comment
  // channel above); the marker on each comment is fed from decisionsByGid.
  const { decisionsByGid, toggleDecision } = useDecisions({
    workspaceId,
  })

  if (!collaboration.ready) return null

  return (
    <CommentStoreProvider value={documentCommentUIStore}>
      <CommentThreadsProvider value={commentThreads}>
        <DecisionsProvider value={{ decisionsByGid, onToggleDecision: toggleDecision }}>
          <ZenEditorLayout
            containerRef={containerRef}
            features={[
              collaboration,
              ...commonFeatures.features,
              comments,
              { plugins: [viewRefPlugin] },
              { plugins: [collapsibleHeadingsPlugin] },
            ]}
            docSynced={collaboration.docSynced}
            attachments={commonFeatures.attachments}
            viewRef={viewRef}
            toolbar={{
              hasKlipy,
              klipyApiKey,
              enableTableInsert: true,
              portalId: "document-toolbar-target",
              grouped: true,
            }}
            syncStatus={{
              status: collaboration.status,
              docSynced: collaboration.docSynced,
              portalId: "document-sync-status-target",
            }}
            title={{
              saveUrl: `/api/documents/${documentId}`,
              initialTitle,
              placeholder: "Document title",
              autoSelectTitle: "Untitled document",
            }}
          >
            <EditorFeatureOverlays bundle={commonFeatures} />
            <CommentSystem {...comments.state} />
          </ZenEditorLayout>
        </DecisionsProvider>
      </CommentThreadsProvider>
    </CommentStoreProvider>
  )
}
