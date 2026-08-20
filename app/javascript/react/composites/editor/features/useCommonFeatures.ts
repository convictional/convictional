import type { MentionUser } from "~/react/shared/hooks/useMentionableUsers"
import { useMentionableUsers } from "~/react/shared/hooks/useMentionableUsers"
import type { EditorFeature } from "../types"
import { useAttachments, type AttachmentsFeature } from "./useAttachments"
import { useEmojis, type EmojiFeature } from "./useEmojis"
import { useLinkTooltip } from "./useLinkTooltip"
import { useMentions, type MentionFeature } from "./useMentions"

interface UseCommonFeaturesOptions {
  // Scope mentions to workspace collaborators (flags them in the dropdown).
  // Omit for org-wide mentions.
  collaboratorIds?: Set<string>
  // Off for editors with no mentions (e.g. the feedback widget). The link
  // tooltip has no such switch — every editor using this bundle wants it.
  mentionsEnabled?: boolean
  // Attachment upload endpoint. Null/omitted yields a no-op attachments feature
  // (empty plugins) so the bundle stays uniform even where uploads aren't wired.
  uploadUrl?: string | null
  // Scope uploads to a caller-owned claim id. Omit to let useAttachments mint its
  // own; pass one when the caller rotates it to reset the attachment scope (e.g.
  // clearing a composer after submit).
  claimId?: string
}

export interface CommonFeatureBundle {
  // Spread into the caller's own Editor `features` array.
  features: EditorFeature[]
  // For callers that also feed the same candidates into useComments.
  mentionableUsers: MentionUser[]
  emoji: EmojiFeature
  mentions: MentionFeature
  mentionsEnabled: boolean
  // Exposed for callers that need the claim id (form submit) or the upload
  // handle (dropzone / imperative uploadFiles).
  attachments: AttachmentsFeature
}

// Bundles the emoji / mention / link-tooltip / attachments setup that every
// rich-text editor repeats. The feature hooks are called unconditionally (rules
// of hooks); the `mentionsEnabled` flag only decides whether mentions land in
// `features` and get rendered by <EditorFeatureOverlays>. Attachments carry no
// bundled UI — callers place their own AttachmentList / dropzone overlay.
export function useCommonFeatures({
  collaboratorIds,
  mentionsEnabled = true,
  uploadUrl = null,
  claimId,
}: UseCommonFeaturesOptions = {}): CommonFeatureBundle {
  const mentionableUsers = useMentionableUsers({ collaboratorIds, enabled: mentionsEnabled })
  const emoji = useEmojis()
  const mentions = useMentions({ users: mentionableUsers, enabled: mentionsEnabled })
  const linkTooltip = useLinkTooltip()
  const attachments = useAttachments({ uploadUrl, claimId })

  const features: EditorFeature[] = [...(mentionsEnabled ? [mentions] : []), emoji, linkTooltip, attachments]

  return { features, mentionableUsers, emoji, mentions, mentionsEnabled, attachments }
}
