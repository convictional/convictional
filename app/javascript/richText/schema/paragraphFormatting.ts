import { Paragraph } from "mdast"
import type { Extension as FromMarkdownExtension } from "mdast-util-from-markdown"
import { defaultHandlers, type Options as ToMarkdownExtension } from "mdast-util-to-markdown"
import { Extension } from "prosemirror-unified"
import { Processor } from "unified"
import type { Node as UnistNode } from "unist"
import { visit } from "unist-util-visit"

const breaksToEmptyParagraphs: FromMarkdownExtension = {
  transforms: [
    tree => {
      visit(tree, "html", (node, index, parent) => {
        if (node.value === "<br>" || node.value === "<br />") {
          const emptyParagraph: Paragraph = {
            type: "paragraph",
            children: [],
          }
          parent?.children.splice(index!, 1, emptyParagraph)
        }
      })
    },
  ],
}

const trimTrailingSpacesFromMarkdown: FromMarkdownExtension = {
  transforms: [
    tree => {
      visit(tree, "paragraph", (node: Paragraph) => {
        if (node.children.length > 0) {
          const lastChild = node.children[node.children.length - 1]
          if (lastChild.type === "text" && lastChild.value.endsWith(" ")) {
            lastChild.value = lastChild.value.replace(/\s+$/, "")
            // Remove the text node if it becomes empty after trimming
            // Empty text nodes are not allowed in ProseMirror
            if (lastChild.value === "") {
              node.children.pop()
            }
          }
        }
      })
    },
  ],
}

const paragraphToMarkdown: ToMarkdownExtension = {
  handlers: {
    paragraph(node, parent, state, info) {
      if (node.children.length === 0) {
        // A lone empty paragraph (a document that is a single empty paragraph) must
        // still emit <br /> — special-casing it to "" would drop a deliberate
        // one-blank-line doc to nothing. Blank-composer emptiness is handled by
        // isBlankMarkdown, not by collapsing here.
        return "<br />"
      }

      const result = defaultHandlers.paragraph(node, parent, state, info)
      return result.replace(/(\s|&#x20;)+$/, "")
    },
  },
}

export class ParagraphFormattingExtension extends Extension {
  public unifiedInitializationHook(
    processor: Processor<UnistNode, UnistNode, UnistNode, UnistNode, string>
  ): Processor<UnistNode, UnistNode, UnistNode, UnistNode, string> {
    const data = processor.data()
    data.fromMarkdownExtensions ??= []
    data.toMarkdownExtensions ??= []

    data.fromMarkdownExtensions.push(breaksToEmptyParagraphs)
    data.fromMarkdownExtensions.push(trimTrailingSpacesFromMarkdown)
    data.toMarkdownExtensions.push(paragraphToMarkdown)

    return processor as unknown as Processor<UnistNode, UnistNode, UnistNode, UnistNode, string>
  }
}
