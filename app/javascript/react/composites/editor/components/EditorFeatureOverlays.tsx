import type { CommonFeatureBundle } from "../features/useCommonFeatures"
import { EmojiSuggester } from "./EmojiSuggester"
import { LinkTooltip } from "./LinkTooltip"
import { MentionSuggester } from "./MentionSuggester"

// Renders the emoji/mention/link-tooltip UI for a useCommonFeatures() bundle.
// Must be a child of <Editor> — LinkTooltip reads ProseMirror context. Mentions
// are omitted when the hook was called with mentionsEnabled:false.
export function EditorFeatureOverlays({ bundle }: { bundle: CommonFeatureBundle }) {
  return (
    <>
      {bundle.mentionsEnabled && <MentionSuggester {...bundle.mentions.state} />}
      <EmojiSuggester {...bundle.emoji.state} />
      <LinkTooltip />
    </>
  )
}
