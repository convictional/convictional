import { EditorFeatureOverlays } from "~/react/composites/editor/components/EditorFeatureOverlays"
import { Toolbar } from "~/react/composites/editor/components/Toolbar"
import { Editor, EditorContent } from "~/react/composites/editor/Editor"
import { uploadFilesToView } from "~/react/composites/editor/features/useAttachments"
import { useCollaboration } from "~/react/composites/editor/features/useCollaboration"
import { useCommonFeatures } from "~/react/composites/editor/features/useCommonFeatures"
import { useViewRef } from "~/react/composites/editor/features/useViewRef"
import { Markdown } from "~/react/composites/markdown/Markdown"
import { SyncStatusContent } from "~/react/composites/SyncStatus"
import { attachmentUploadUrl } from "~/react/shared/attachmentUrls"
import { useChannelsClient } from "~/react/shared/hooks/useChannelsClient"
import { useCurrentUser } from "~/react/shared/hooks/useCurrentUser"
import { useDropzone } from "~/react/shared/hooks/useDropzone"
import { useWorkspaceCollaboratorIds } from "~/react/shared/hooks/useWorkspaceCollaboratorIds"
import { DropzoneOverlay } from "~/react/ui/DropzoneOverlay"
import { LoadingState } from "~/react/ui/LoadingState"
import { ChannelStream } from "~/types/channels"

const AGENDA_TOOLS = [
  "bold",
  "italic",
  "code",
  "heading",
  "quote",
  "bulletList",
  "orderedList",
  "link",
  "image",
] as const

interface AgendaEditorProps {
  meetingId: string
  initialContent: string | null
  workspaceId: string
}

export function AgendaEditor({ meetingId, initialContent, workspaceId }: AgendaEditorProps) {
  // The current user is only needed for the agenda editor's collaboration
  // identity, so a /users/me failure must not blank the whole page (title,
  // schedule, recurring nav, sharing, recording controls, attendees all stand
  // on their own). Degrade only the editor — see the branches below.
  const { user, error: userError } = useCurrentUser()

  if (user) {
    return (
      <AgendaEditorContent
        meetingId={meetingId}
        currentUser={{ id: user.id, displayName: user.display_name }}
        initialContent={initialContent}
        workspaceId={workspaceId}
      />
    )
  }
  // Only fall back to read-only once the user fetch has actually
  // failed — while it's still idle/loading, show the spinner so we
  // don't flash "editing unavailable" before the editor appears.
  if (userError) {
    return <AgendaUnavailable agenda={initialContent} />
  }
  return <LoadingState className="py-8" />
}

interface AgendaEditorContentProps extends AgendaEditorProps {
  currentUser: { id: string; displayName: string }
}

function AgendaEditorContent({ meetingId, currentUser, initialContent, workspaceId }: AgendaEditorContentProps) {
  const channelsClient = useChannelsClient()

  const collaboration = useCollaboration({
    channelsClient,
    stream: ChannelStream.MEETING_AGENDA,
    params: { meeting_id: meetingId },
    currentUser,
    initialContent,
  })
  // Agenda mentions keep the workspace collaborator split the old typeahead
  // endpoint provided: collaborators first, everyone else under "Invite".
  const collaboratorIds = useWorkspaceCollaboratorIds(workspaceId)
  const commonFeatures = useCommonFeatures({ collaboratorIds, uploadUrl: attachmentUploadUrl(workspaceId) })
  const { viewRef, plugin: viewRefPlugin } = useViewRef()
  const { isDragOver, ref: dropzoneRef } = useDropzone({
    onFiles: files => uploadFilesToView(viewRef.current, commonFeatures.attachments, files),
  })

  if (!collaboration.ready) return null

  return (
    <Editor
      features={[collaboration, ...commonFeatures.features, { plugins: [viewRefPlugin] }]}
      placeholder="Add your agenda"
      className="w-full focus:outline-hidden min-h-32 max-h-96 overflow-y-auto p-3"
      showDropCursor={false}
    >
      <div ref={dropzoneRef} className="relative border border-base-300 rounded-md bg-base-100 overflow-hidden">
        {isDragOver && <DropzoneOverlay />}
        <div className="border-b border-base-300 px-2 py-1 flex items-center justify-between gap-2">
          <Toolbar hasKlipy={false} klipyApiKey={null} tools={AGENDA_TOOLS} attachments={commonFeatures.attachments} />
          <SyncStatusContent status={collaboration.status} docSynced={collaboration.docSynced} />
        </div>
        <EditorContent />
      </div>
      <EditorFeatureOverlays bundle={commonFeatures} />
    </Editor>
  )
}

// Fallback when the current user couldn't be loaded: the collaborative editor
// needs an identity, so show the agenda read-only with a note rather than
// failing the whole page.
function AgendaUnavailable({ agenda }: { agenda: string | null }) {
  return (
    <div className="p-3 space-y-2">
      <p className="text-xs text-base-500">Live editing is unavailable right now. Refresh the page to try again.</p>
      {agenda ? (
        <Markdown source={agenda} className="!max-w-none" />
      ) : (
        <p className="text-base-500 italic">No agenda yet.</p>
      )}
    </div>
  )
}
