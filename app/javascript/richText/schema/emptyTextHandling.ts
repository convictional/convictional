import type { Code, InlineCode, Text } from "mdast"
import type { Extension as FromMarkdownExtension } from "mdast-util-from-markdown"
import { Node, Schema } from "prosemirror-model"
import { CodeBlockExtension } from "prosemirror-remark"
import { Extension } from "prosemirror-unified"
import { Processor } from "unified"
import type { Node as UnistNode } from "unist"
import { visit, SKIP } from "unist-util-visit"

// Mark empty code blocks to handle them without creating empty text nodes
const handleEmptyCodeBlocks: FromMarkdownExtension = {
  transforms: [
    tree => {
      visit(tree, "code", (node: Code) => {
        if (node.value === "") {
          node.data = node.data || {}
          ;(node.data as Record<string, boolean>).isEmpty = true
        }
      })
    },
  ],
}

// Remove empty inline code nodes
const handleEmptyInlineCode: FromMarkdownExtension = {
  transforms: [
    tree => {
      visit(tree, "inlineCode", (node: InlineCode, index, parent) => {
        if (node.value === "" && parent && typeof index === "number") {
          parent.children.splice(index, 1)
          return [SKIP, index]
        }
      })
    },
  ],
}

// Remove empty text nodes (ProseMirror doesn't allow them)
const removeEmptyTextNodes: FromMarkdownExtension = {
  transforms: [
    tree => {
      visit(tree, "text", (node: Text, index, parent) => {
        if (node.value === "" && parent && typeof index === "number") {
          parent.children.splice(index, 1)
          return [SKIP, index]
        }
      })
    },
  ],
}

// Overrides CodeBlockExtension to create empty code blocks without text children,
// avoiding ProseMirror's "Empty text nodes are not allowed" error
export class EmptyContentSafeCodeBlockExtension extends CodeBlockExtension {
  override proseMirrorNodeSpec() {
    const baseSpec = super.proseMirrorNodeSpec()
    return {
      ...baseSpec,
      attrs: {
        params: { default: null },
      },
    }
  }

  override proseMirrorNodeToUnistNodes(pmNode: Node, convertedChildren: Text[]): Code[] {
    return [
      {
        type: this.unistNodeName(),
        lang: pmNode.attrs.params || null,
        meta: null,
        value: convertedChildren.map(child => child.value).join(""),
      },
    ]
  }

  override unistNodeToProseMirrorNodes(node: Code, proseMirrorSchema: Schema<string, string>): Node[] {
    const nodeType = proseMirrorSchema.nodes[this.proseMirrorNodeName()!]
    const isEmpty = !node.value || (node.data as Record<string, boolean>)?.isEmpty
    const attrs = node.lang ? { params: node.lang } : {}

    if (isEmpty) {
      return [nodeType.create(attrs)]
    }

    return [nodeType.create(attrs, proseMirrorSchema.text(node.value))]
  }
}

// Adds transforms to remove empty text nodes before ProseMirror conversion
export class EmptyTextNodeSafeExtension extends Extension {
  public unifiedInitializationHook(
    processor: Processor<UnistNode, UnistNode, UnistNode, UnistNode, string>
  ): Processor<UnistNode, UnistNode, UnistNode, UnistNode, string> {
    const data = processor.data()
    data.fromMarkdownExtensions ??= []

    // Order matters: handle specific node types first, then general text cleanup
    data.fromMarkdownExtensions.push(handleEmptyCodeBlocks)
    data.fromMarkdownExtensions.push(handleEmptyInlineCode)
    data.fromMarkdownExtensions.push(removeEmptyTextNodes)

    return processor as unknown as Processor<UnistNode, UnistNode, UnistNode, UnistNode, string>
  }
}
