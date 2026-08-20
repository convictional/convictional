import type { Emphasis, PhrasingContent, Strong, Text } from "mdast"
import type { Extension as FromMarkdownExtension } from "mdast-util-from-markdown"
import { Node as ProseMirrorNode } from "prosemirror-model"
import { Extension, ProseMirrorUnified } from "prosemirror-unified"
import { Processor } from "unified"
import type { Node as UnistNode } from "unist"

type MarkType = "strong" | "emphasis"

// Only strong/emphasis collide on asterisk delimiters; delete/inlineCode/link have unique
// delimiters and can't produce the ***** run-on the normalizer heals.
const MARK_TYPES: MarkType[] = ["strong", "emphasis"]

function isParentNode(node: UnistNode): node is UnistNode & { children: UnistNode[] } {
  return "children" in node && Array.isArray((node as { children?: unknown }).children)
}

// Collapses strong(strong(X)) -> strong(X) and emphasis(emphasis(X)) -> emphasis(X),
// the duplicate marks parsed from *****text*****.
function collapseNestedMarks(node: UnistNode): void {
  if (!isParentNode(node)) return

  for (const child of node.children) {
    collapseNestedMarks(child)
  }

  if (node.type === "strong" || node.type === "emphasis") {
    const markNode = node as Strong | Emphasis
    let changed = true
    while (changed) {
      changed = false
      const newChildren: PhrasingContent[] = []
      for (const child of markNode.children) {
        if (child.type === node.type && "children" in child) {
          newChildren.push(...(child as Strong | Emphasis).children)
          changed = true
        } else {
          newChildren.push(child)
        }
      }
      markNode.children = newChildren
    }
  }
}

// True if the node is the mark type or a single-child wrapper containing it.
function containsMark(node: UnistNode, markType: MarkType): boolean {
  if (node.type === markType) return true
  if (!isParentNode(node)) return false
  if (node.children.length === 1) {
    return containsMark(node.children[0], markType)
  }
  return false
}

// Returns the node's children with the mark stripped — either by unwrapping the mark node itself
// or by reconstructing a wrapper (e.g. emphasis around strong) without the inner mark.
function extractMark(node: UnistNode, markType: MarkType): UnistNode[] {
  if (node.type === markType && isParentNode(node)) {
    return node.children
  }
  if (!isParentNode(node)) return [node]
  if (node.children.length === 1) {
    const extracted = extractMark(node.children[0], markType)
    return [Object.assign({}, node, { children: extracted })]
  }
  return [node]
}

// Merges adjacent siblings sharing a mark wrapper into one:
// [strong(A), emphasis(strong(B)), strong(C)] -> [strong(A, emphasis(B), C)].
function factorCommonMarks(node: UnistNode): void {
  if (!isParentNode(node)) return

  for (const child of node.children) {
    factorCommonMarks(child)
  }

  for (const markType of MARK_TYPES) {
    let i = 0
    while (i < node.children.length) {
      if (containsMark(node.children[i], markType)) {
        let runEnd = i + 1
        while (runEnd < node.children.length && containsMark(node.children[runEnd], markType)) {
          runEnd++
        }

        if (runEnd - i >= 2) {
          const extractedChildren: UnistNode[] = []
          for (let j = i; j < runEnd; j++) {
            extractedChildren.push(...extractMark(node.children[j], markType))
          }

          const wrapper: Strong | Emphasis = {
            type: markType,
            children: extractedChildren as PhrasingContent[],
          }

          factorCommonMarks(wrapper)

          node.children.splice(i, runEnd - i, wrapper)
        }
      }
      i++
    }
  }
}

export function normalizeMarkTree(tree: UnistNode): void {
  collapseNestedMarks(tree)
  factorCommonMarks(tree)
}

const collapseNestedMarksTransform: FromMarkdownExtension = {
  transforms: [
    tree => {
      collapseNestedMarks(tree)
    },
  ],
}

// Parse-time half of mark normalization. The serialize half lives in serializeWithNormalization
// because prosemirror-unified's stringify doesn't run plugins.
export class MarkNormalizationExtension extends Extension {
  public unifiedInitializationHook(
    processor: Processor<UnistNode, UnistNode, UnistNode, UnistNode, string>
  ): Processor<UnistNode, UnistNode, UnistNode, UnistNode, string> {
    const data = processor.data()
    data.fromMarkdownExtensions ??= []
    data.fromMarkdownExtensions.push(collapseNestedMarksTransform)

    return processor
  }
}

// prosemirror-unified marks these `private readonly` and offers no pre-stringify hook. Access
// through a typed interface, checked at runtime so a pmu upgrade fails loudly.
type PmuSerializeInternals = {
  proseMirrorToUnistConverter: { convert: (doc: ProseMirrorNode) => UnistNode }
  unified: { stringify: (tree: UnistNode) => string }
}

function getSerializeInternals(pmu: ProseMirrorUnified): PmuSerializeInternals {
  const internals = pmu as unknown as PmuSerializeInternals
  if (
    typeof internals.proseMirrorToUnistConverter?.convert !== "function" ||
    typeof internals.unified?.stringify !== "function"
  ) {
    throw new Error(
      "prosemirror-unified internals changed; mark-normalization serialize path is broken. " +
        "See app/javascript/richText/schema/markNormalization.ts; if pmu has since added a " +
        "pre-stringify hook, refactor serializeWithNormalization to use it."
    )
  }
  return internals
}

// Drops a trailing hard_break from paragraph/tableCell/heading. The break is invisible in HTML
// but breaks round-trip: serialize emits `text\<NL>`, which re-parses as a literal backslash and
// re-serializes as `text\\<NL>` (visible `\` in output). Inline breaks mid-content are preserved.
export function dropBlockTrailingHardBreaks(tree: UnistNode): void {
  if (!isParentNode(tree)) return
  for (const child of tree.children) {
    dropBlockTrailingHardBreaks(child)
  }
  if (tree.type !== "paragraph" && tree.type !== "tableCell" && tree.type !== "heading") return
  while (tree.children.length > 0 && tree.children[tree.children.length - 1].type === "break") {
    tree.children.pop()
  }
}

// Text-bearing blocks whose leading whitespace sits at the start of a rendered line.
// A leading space run here is stripped by CommonMark (indentation) and by the email
// sanitizer's ^[ \t]+ / (?<=\n)[ \t]+ rules, so it must be carried as NBSP to survive.
const LINE_START_BLOCKS = new Set(["paragraph", "heading", "tableCell"])

// An h1/h2 containing a break node force-selects a setext underline in
// mdast-util-to-markdown (formatHeadingAsSetext → literalWithBreak), and that setext
// re-parses to an empty document — silent data loss for "heading + Shift+Enter". ATX
// headings can't hold a real newline and an inline <br> corrupts on parse
// (breaksToEmptyParagraphs), so we flatten an in-heading break to a space: the heading
// stays ATX, round-trips losslessly, and no content is lost. The visible <br> is an
// accepted fidelity loss (in-heading breaks are rare) — see cases.json hard_break_heading.
export function flattenHeadingBreaks(tree: UnistNode): void {
  if (!isParentNode(tree)) return
  for (const child of tree.children) {
    flattenHeadingBreaks(child)
  }
  if (tree.type !== "heading") return
  tree.children = tree.children.map(child => (child.type === "break" ? ({ type: "text", value: " " } as Text) : child))
}

// Converts a leading run of ordinary spaces (U+0020) at the start of a rendered line to
// NBSP (U+00A0), the contract's canonical carrier for leading whitespace. NBSP passes
// through both markdown parsers and the email sanitizer untouched, whereas literal
// leading spaces are escaped to &#x20; (which diverges across the server renderers) or
// stripped. Interior runs are left literal (pre-wrap preserves them); only leading
// position needs NBSP. Tabs keep their existing &#x9; escaping.
export function convertLeadingSpacesToNbsp(tree: UnistNode): void {
  if (!isParentNode(tree)) return
  for (const child of tree.children) {
    convertLeadingSpacesToNbsp(child)
  }
  if (!LINE_START_BLOCKS.has(tree.type)) return
  tree.children.forEach((child, index) => {
    const atLineStart = index === 0 || tree.children[index - 1].type === "break"
    if (!atLineStart || child.type !== "text") return
    const textNode = child as unknown as { value: string }
    textNode.value = textNode.value.replace(/^ +/, spaces => String.fromCharCode(0xa0).repeat(spaces.length))
  })
}

export function serializeWithNormalization(pmu: ProseMirrorUnified, doc: ProseMirrorNode): string {
  const { proseMirrorToUnistConverter, unified } = getSerializeInternals(pmu)
  const unist = proseMirrorToUnistConverter.convert(doc)
  normalizeMarkTree(unist)
  dropBlockTrailingHardBreaks(unist)
  flattenHeadingBreaks(unist)
  convertLeadingSpacesToNbsp(unist)
  return unified.stringify(unist)
}
