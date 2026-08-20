// Removes the single markdown link whose destination matches an already-previewed
// attachment URL, so a file attachment isn't rendered twice: once as an inline
// [filename](url) anchor in the body and once as the LinkPreviewCard below it.
// Applied at render time only for resource_kind === "file" previews — the raw
// content (link intact) is still what the edit flow loads into the editor.
//
// Mirrors MARKDOWN_LINK_PATTERN / _unescape_parens in app/presenters/links.py:
// the destination tolerates one level of balanced parens and backslash-escaped
// parens (the editor serializes hrefs with \( \) — see urlFormatting.ts), and the
// leading (?<!!) lookbehind keeps image markdown ![alt](url) from matching.
//
// Known limitation (accepted): the strip runs on the raw markdown with no AST
// awareness, so a link written literally inside a code span (`[x](url)`) would
// also be stripped, and a bare-URL paste that resolves to a file won't be. Neither
// arises from the normal attachment-upload flow.
function unescapeParens(url: string): string {
  return url.replace(/\\\(/g, "(").replace(/\\\)/g, ")")
}

// Captures a single optional space on each side of the link so the removal can be
// tidied locally (see below) instead of running whitespace passes over the whole
// body, which would mangle hard line breaks, code blocks, and prose spacing that
// have nothing to do with the removed link. Safe to reuse across renders: replace()
// resets a global regex's lastIndex on every call.
const markdownLink = /(?<!!)( ?)\[([^\]]+)\]\(((?:[^()\s\\]|\\[()]|\([^()]*\))+)\)( ?)/g

// Structural shape common to the chat `LinkPreview` and the post/email
// `PostCommentLinkPreview` — the only fields this strip needs.
type PreviewedAttachment = { url: string; resource_kind?: string | null }

export function stripPreviewedAttachmentLink(
  content: string,
  linkPreview: PreviewedAttachment | null | undefined
): string {
  if (linkPreview?.resource_kind !== "file") return content

  // Drop the link and, at the removal site only, either collapse its two flanking
  // spaces to one (link between prose) or consume the single flanking space (link at
  // an edge or before punctuation). The rest of the body is left untouched.
  const stripped = content.replace(markdownLink, (match, lead, _text, destination: string, trail) =>
    unescapeParens(destination) === linkPreview.url ? (lead && trail ? " " : "") : match
  )

  if (stripped === content) return content

  // An attachment-only body collapses to empty.
  return stripped.trim() === "" ? "" : stripped
}
