import { Fragment, MarkSpec, Node } from "prosemirror-model"
import { MarkExtension } from "prosemirror-unified"
import type { Node as UnistNode } from "unist"

// The DOM shape of a comment highlight. The pending-comment decoration mirrors it
// so an unsaved highlight looks identical and CommentSystem's selectors match both.
export const COMMENT_HIGHLIGHT_CLASS = "inline-comment-highlight"
export const COMMENT_ID_ATTR = "data-comment-id"

const commentMarkSpec: MarkSpec = {
  attrs: {
    commentId: { default: "" },
  },
  excludes: "",
  inclusive: false,
  toDOM(mark) {
    return [
      "span",
      {
        class: COMMENT_HIGHLIGHT_CLASS,
        [COMMENT_ID_ATTR]: mark.attrs.commentId,
      },
    ]
  },
  parseDOM: [
    {
      tag: `span.${COMMENT_HIGHLIGHT_CLASS}[${COMMENT_ID_ATTR}]`,
      getAttrs(dom: HTMLElement) {
        return { commentId: dom.getAttribute(COMMENT_ID_ATTR) }
      },
    },
  ],
}

export class CommentMarkExtension extends MarkExtension<UnistNode> {
  override unistNodeName(): string {
    return "comment"
  }

  override proseMirrorMarkName(): string {
    return "comment"
  }

  override proseMirrorMarkSpec(): MarkSpec {
    return commentMarkSpec
  }

  override unistNodeToProseMirrorNodes(): Array<Node> {
    return []
  }

  override processConvertedUnistNode(convertedNode: UnistNode): UnistNode {
    return convertedNode
  }
}

export function stripCommentMarks(doc: Node): Node {
  const commentType = doc.type.schema.marks.comment
  if (!commentType) return doc

  function stripFromFragment(fragment: Fragment): Fragment {
    const children: Node[] = []
    fragment.forEach(child => {
      const marks = child.marks.filter(m => m.type !== commentType)
      const newChild = child.isText ? child.mark(marks) : child.copy(stripFromFragment(child.content)).mark(marks)
      children.push(newChild)
    })
    return Fragment.from(children)
  }

  return doc.copy(stripFromFragment(doc.content))
}

export function getCommentMarkIds(doc: Node): Set<string> {
  const ids = new Set<string>()
  const markType = doc.type.schema.marks.comment
  if (!markType) return ids
  doc.descendants(node => {
    for (const mark of node.marks) {
      if (mark.type === markType) ids.add(mark.attrs.commentId as string)
    }
  })
  return ids
}
