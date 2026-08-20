// The helpers in this file mutate pasted HTML via DOMParser and return innerHTML. They are
// NOT HTML sanitizers: the output must be schema-parsed downstream (via ProseMirror's parseDOM
// rules on the richText schema) before it can safely be rendered. Do not reuse these functions
// in any context that assigns the result to a live DOM's innerHTML / v-html / dangerouslySetInnerHTML.
import { toggleMark } from "prosemirror-commands"
import { DOMSerializer, Fragment, Slice, Node as PMNode, ResolvedPos } from "prosemirror-model"
import { Plugin, PluginKey, EditorState, Transaction } from "prosemirror-state"
import { EditorView } from "prosemirror-view"

import { ALLOWED_LINK_PROTOCOLS, findUrlMatches } from "~/shared/links"

import { parse, schema } from "../schema"
import { getCommentMarkIds } from "../schema/commentMark"

// Pattern to detect markdown-like content. Ordered as block-level (line-anchored) branches
// first, then inline branches. The block branches cover headings, blockquotes, thematic breaks
// (---, ***, ___), unordered lists (-, *, + — this also catches task lists like "- [ ]"),
// ordered lists, fenced code, and the GFM table header+delimiter pair (which requires BOTH a
// header row AND a delimiter row so a single sentence like "| pipe demo |" isn't misread as a
// table). The inline branches cover bold, italic, strikethrough, inline code, and link/image
// syntax.
//
// Every inline branch is bounded ({1,200}) and excludes newlines so the regex stays linear on
// hostile input (e.g. a multi-MB run of "[([(" with no closing bracket). Without the bound,
// `[^\]]+`-style branches backtrack O(n^2) and freeze the tab — which is why detection used to
// be length-capped. The bound removes that risk, so the cap is gone and large markdown pastes
// (plans / LLM output) are detected in full. See MARKDOWN_PATTERNS coverage tests in
// tests/javascript/richText/plugins/clipboard.test.ts.
const MARKDOWN_PATTERNS =
  /^#{1,6}\s|^\s*>\s|^\s*([-*_])(?:[ \t]*\1){2,}[ \t]*$|^\s*[-*+]\s|^\s*\d+\.\s|```|^\|.+\|\s*\n\s*\|[\s\-:|]+\||\*\*[^*\n]{1,200}\*\*|\*[^*\n]{1,200}\*|~~[^~\n]{1,200}~~|`[^`\n]{1,200}`|!?\[[^\]\n]{1,200}\]\([^)\n]{1,200}\)/m

const BLOCK_TAGS = ["div", "p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr", "pre", "blockquote"]

// Distinguishes HTML that carries meaningful formatting or structure from plain text in minimal
// wrappers (e.g. VS Code clipboard output ships cosmetic styles like font-weight:normal that must
// NOT skip the markdown re-parse path). Tables and images are included because extractTextFromHtml
// discards their structure — routing them through the markdown re-parse would flatten a pasted
// spreadsheet or drop an image, so they must short-circuit to the structural DOM parse instead.
const RICH_HTML_PATTERN =
  /<(strong|b|em|i|h[1-6]|ul|ol|a|code|blockquote|pre|table|thead|tbody|tr|td|th|img)[\s>]|font-weight\s*:\s*(bold(er)?|[5-9]\d{2})|font-style\s*:\s*italic|text-decoration\s*:[^;"']*\b(line-through|underline)\b/i

const BLOCK_TAGNAMES = new Set([
  "P",
  "UL",
  "OL",
  "H1",
  "H2",
  "H3",
  "H4",
  "H5",
  "H6",
  "TABLE",
  "BLOCKQUOTE",
  "PRE",
  "DIV",
  "HR",
])

// Derived from BLOCK_TAGNAMES so the prefilter stays in sync if a tag is added.
const INTER_BLOCK_BR_PATTERN = new RegExp(
  `(?:</(?:${[...BLOCK_TAGNAMES].map(t => t.toLowerCase()).join("|")})>\\s*<br|<br[^>]*>\\s*<(?:${[...BLOCK_TAGNAMES]
    .map(t => t.toLowerCase())
    .join("|")})\\b)`,
  "i"
)

const clipboardPluginKey = new PluginKey("clipboard")

const clipboardPlugin = new Plugin({
  key: clipboardPluginKey,
  props: {
    clipboardTextParser: (text: string, $context: ResolvedPos, plain: boolean, _view: EditorView) => {
      if (plain || $context.parent.type.name === "code_block" || !text.trim()) {
        return new Slice(Fragment.from(schema.text(text)), $context.depth, $context.depth)
      }

      try {
        const doc = parse(text)
        const linkifiedContent = linkify(doc.content)

        // Unwrap a single paragraph so we don't insert a new block when pasting inline content.
        if (linkifiedContent.childCount === 1 && linkifiedContent.firstChild?.type.name === "paragraph") {
          const paragraphContent = linkifiedContent.firstChild.content
          return new Slice(paragraphContent, $context.depth, $context.depth)
        }

        return new Slice(linkifiedContent, $context.depth, $context.depth)
      } catch {
        const parsed = schema.text(text)
        const linkified = linkify(Fragment.from(parsed))
        return new Slice(linkified, $context.depth, $context.depth)
      }
    },

    transformPastedHTML: (html: string, _view: EditorView): string => {
      // DOM-level cleanup runs here; comment-mark deduplication runs later in transformPasted
      // (it needs the parsed Slice to compare commentIds against the destination doc).
      html = applyDomCleanups(html)

      // Rich HTML carries formatting that re-parsing as markdown would lose; skip the markdown path.
      if (RICH_HTML_PATTERN.test(html)) {
        return html
      }

      // VS Code and similar editors put raw markdown into text/html, so detect and re-parse it.
      const text = extractTextFromHtml(html)
      if (text && looksLikeMarkdown(text)) {
        try {
          return serializeToHtml(parse(text))
        } catch {
          return html
        }
      }

      return html
    },

    transformPasted: (slice: Slice, view: EditorView, _plain: boolean): Slice => {
      // Strip comment marks whose id already exists in this doc so a same-document cut+paste
      // can preserve its mark (cut removes the mark from the doc, so the pasted copy survives
      // this filter), while same-document copy+paste (which would create a duplicate) is stripped.
      //
      // Cross-document paste (text with a comment from doc A pasted into doc B) is intentionally
      // left to the deferred cleanup in useCommentMarks.cleanupOrphanMarks: the pasted mark id is
      // unknown to doc B, so it survives this filter, briefly broadcasts via Yjs, and is then
      // stripped once doc B's threads load (loadedFor === resourceId) and don't include the id.
      // We can't strip it here without coupling this richText-layer plugin to the comment store.
      const existingIds = getCommentMarkIds(view.state.doc)
      if (existingIds.size === 0) return slice

      const commentType = view.state.schema.marks.comment
      if (!commentType) return slice

      function stripCollidingFromFragment(fragment: Fragment): Fragment {
        const children: PMNode[] = []
        fragment.forEach(child => {
          const filteredMarks = child.marks.filter(
            m => m.type !== commentType || !existingIds.has(m.attrs.commentId as string)
          )
          const newChild = child.isText
            ? child.mark(filteredMarks)
            : child.copy(stripCollidingFromFragment(child.content)).mark(filteredMarks)
          children.push(newChild)
        })
        return Fragment.from(children)
      }

      return new Slice(stripCollidingFromFragment(slice.content), slice.openStart, slice.openEnd)
    },

    handlePaste: (view: EditorView, _event: ClipboardEvent, slice: Slice): boolean => {
      if (handleLinkPaste(view.state, view.dispatch, slice)) {
        return true
      }
      const { $from, $to } = view.state.selection
      if (
        $from.depth > 1 &&
        $from.node($from.depth - 1).type === schema.nodes.blockquote &&
        $to.depth > 1 &&
        $to.node($to.depth - 1).type === schema.nodes.blockquote
      ) {
        const tr = view.state.tr.replaceSelection(slice).scrollIntoView()
        view.dispatch(tr)
        return true
      }

      return false
    },
  },
})

function linkify(fragment: Fragment): Fragment {
  const linkified: PMNode[] = []

  fragment.forEach(child => {
    if (!child.isText) {
      linkified.push(child.copy(linkify(child.content)))
      return
    }

    let pos = 0

    for (const { start, end, href } of findUrlMatches(child.text as string)) {
      if (start > pos) {
        linkified.push(child.cut(pos, start))
      }

      linkified.push(child.cut(start, end).mark(schema.marks.link.create({ href }).addToSet(child.marks)))
      pos = end
    }

    if (pos < (child.text?.length || 0)) {
      linkified.push(child.cut(pos))
    }
  })

  return Fragment.fromArray(linkified)
}

function extractTextFromHtml(html: string): string {
  const doc = new DOMParser().parseFromString(html, "text/html")
  const body = doc.body

  // Inject newlines around block boundaries so textContent preserves structure.
  body.querySelectorAll("br").forEach(br => {
    br.replaceWith("\n")
  })
  BLOCK_TAGS.forEach(tag => {
    body.querySelectorAll(tag).forEach(el => {
      el.prepend("\n")
      el.append("\n")
    })
  })

  const text = body.textContent || ""
  return text.replace(/\n{3,}/g, "\n\n").trim()
}

function looksLikeMarkdown(text: string): boolean {
  return MARKDOWN_PATTERNS.test(text)
}

function serializeToHtml(doc: PMNode): string {
  const serializer = DOMSerializer.fromSchema(schema)
  const fragment = serializer.serializeFragment(doc.content)
  const container = document.createElement("div")
  container.appendChild(fragment)
  return container.innerHTML
}

function handleLinkPaste(state: EditorState, dispatch?: (tr: Transaction) => void, slice?: Slice): boolean {
  if (!slice || state.selection.empty) {
    return false
  }

  const textContent = slice.content.textBetween(0, slice.content.size)
  const trimmed = textContent.trim()
  const matches = findUrlMatches(trimmed)

  if (matches.length === 1 && matches[0].start === 0 && matches[0].end === trimmed.length) {
    return toggleMark(schema.marks.link, { href: matches[0].href })(state, dispatch) || false
  }

  return false
}

function applyDomCleanups(html: string): string {
  const hasDocsWrapper = html.includes("docs-internal-guid-")
  const hasRedirect = html.includes("google.com/url?")
  const hasCheckbox = html.includes('role="checkbox"') || html.includes("role='checkbox'")
  // Run for every list paste — Word, Google Docs, and other CMSes all emit invalid nesting.
  // The reattach is a no-op on valid content.
  const hasNestedList = html.includes("<ul") || html.includes("<ol")
  const hasInterBlockBr = INTER_BLOCK_BR_PATTERN.test(html)
  if (!hasDocsWrapper && !hasRedirect && !hasCheckbox && !hasNestedList && !hasInterBlockBr) return html

  const doc = new DOMParser().parseFromString(html, "text/html")

  if (hasDocsWrapper) {
    const wrapper = doc.querySelector('b[id^="docs-internal-guid-"]')
    if (wrapper) wrapper.replaceWith(...wrapper.childNodes)
  }

  if (hasRedirect) {
    doc.querySelectorAll("a[href]").forEach(anchor => unwrapGoogleRedirectOnAnchor(anchor))
  }

  if (hasInterBlockBr) stripInterBlockSeparatorBrs(doc.body)

  // Must run before rewriteGoogleDocsCheckboxOnLi — nested checklists arrive with the same
  // invalid structure, and fixing it first lets the checkbox rewrite walk a valid tree.
  reattachNestedListsToPrecedingLi(doc.body)

  if (hasCheckbox) {
    doc.querySelectorAll('li[role="checkbox"]').forEach(li => rewriteGoogleDocsCheckboxOnLi(li, doc))
  }

  return doc.body.innerHTML
}

function unwrapGoogleRedirectOnAnchor(anchor: Element): void {
  const href = anchor.getAttribute("href")
  if (!href) return
  let url: URL
  try {
    url = new URL(href)
  } catch {
    return
  }
  if (
    url.hostname !== "www.google.com" ||
    url.pathname !== "/url" ||
    url.searchParams.get("sa") !== "D" ||
    url.searchParams.get("source") !== "editors"
  ) {
    return
  }
  const realUrl = url.searchParams.get("q")
  if (!realUrl) return
  try {
    const dest = new URL(realUrl)
    if (!ALLOWED_LINK_PROTOCOLS.has(dest.protocol)) return
    // Strip userinfo to block https://trusted.com@evil.com/ payloads that look like the trusted host.
    dest.username = ""
    dest.password = ""
    anchor.setAttribute("href", dest.href)
  } catch {
    // Malformed destination URL — leave original href.
  }
}

// Google Docs emits checklists as <li role="checkbox" aria-checked> with a decorative PNG <img>.
// Rewrite to <li><input type="checkbox" [checked]>...</li> so TaskListItemExtension.parseDOM matches.
function rewriteGoogleDocsCheckboxOnLi(li: Element, doc: Document): void {
  const isChecked = li.getAttribute("aria-checked") === "true"
  li.querySelectorAll(":scope > img").forEach(img => img.remove())
  const checkbox = doc.createElement("input")
  checkbox.type = "checkbox"
  if (isChecked) {
    checkbox.checked = true
    checkbox.setAttribute("checked", "")
  }
  li.insertBefore(checkbox, li.firstChild)
}

// Replace block-adjacent <br>s with empty paragraphs. Google Docs/Word emit these as visible
// blank lines between blocks (`</p><br><p>`); without intervention ProseMirror absorbs them as
// `paragraph(hard_break)`, which renders with extra spacing and corrupts on re-edit (see
// dropBlockTrailingHardBreaks in schema/markNormalization.ts). The adjacent-text guard preserves
// Shift+Enter line breaks inside paragraphs like `<div>foo<br><p>bar</p></div>`.
function stripInterBlockSeparatorBrs(root: Element): void {
  const ownerDocument = root.ownerDocument
  const brs = Array.from(root.querySelectorAll("br"))
  for (const br of brs) {
    if (hasAdjacentNonWhitespaceText(br)) continue
    const prev = br.previousElementSibling
    const next = br.nextElementSibling
    if ((prev && BLOCK_TAGNAMES.has(prev.tagName)) || (next && BLOCK_TAGNAMES.has(next.tagName))) {
      br.replaceWith(ownerDocument.createElement("p"))
    }
  }
}

function hasAdjacentNonWhitespaceText(el: Element): boolean {
  for (const sibling of [el.previousSibling, el.nextSibling]) {
    if (sibling && sibling.nodeType === Node.TEXT_NODE && (sibling.textContent ?? "").trim().length > 0) {
      return true
    }
  }
  return false
}

// Google Docs emits nested lists as invalid HTML — `<ul><li>A</li><ul><li>nested</li></ul></ul>` —
// where the inner list is a sibling of <li> rather than its child. ProseMirror expects the W3C
// form, so without this fix nested items flatten to siblings. Reverse iteration handles arbitrary
// nesting depth (innermost reattaches first).
function reattachNestedListsToPrecedingLi(root: Element): void {
  const lists = Array.from(root.querySelectorAll("ul, ol"))
  for (let i = lists.length - 1; i >= 0; i--) {
    const list = lists[i]
    const parent = list.parentElement
    if (!parent) continue
    const parentTag = parent.tagName
    if (parentTag !== "UL" && parentTag !== "OL") continue

    let prev: ChildNode | null = list.previousSibling
    while (prev && !(prev.nodeType === Node.ELEMENT_NODE && (prev as Element).tagName === "LI")) {
      prev = prev.previousSibling
    }
    if (!prev) continue
    ;(prev as Element).appendChild(list)
  }
}

export { clipboardPlugin, linkify, handleLinkPaste }
