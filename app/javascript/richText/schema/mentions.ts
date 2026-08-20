import { Literal } from "mdast"
import type { Extension as FromMarkdownExtension } from "mdast-util-from-markdown"
import type { Options as ToMarkdownExtension } from "mdast-util-to-markdown"
import { codes } from "micromark-util-symbol"
import type { Code, Extension, State } from "micromark-util-types"
import { Node, NodeSpec, Schema } from "prosemirror-model"
import { NodeExtension } from "prosemirror-unified"
import { Processor } from "unified"
import { Node as UnistNode } from "unist"

export interface Mention extends Literal {
  type: "mention"
}

//
// Micromark Mention Extension
//
//

const mention: Extension = {
  text: {
    [codes.atSign]: {
      name: "mention",
      tokenize: (effects, ok, nok): State => {
        return start
        // ┌───▶mention◀────┐
        // │                │
        // @[Display Name123]
        // │││             ││
        // ││└▶mentionName◀┘│
        // │└─▶mentionOpen  │
        // │   mentionClose◀┘
        // └──▶mentionMarker

        function start(code: Code) {
          effects.enter("mention")
          effects.enter("mentionMarker")
          effects.consume(code)
          effects.exit("mentionMarker")
          return open
        }

        function open(code: Code) {
          if (code != codes.leftSquareBracket) return nok(code)
          effects.enter("mentionOpen")
          effects.consume(code)
          effects.exit("mentionOpen")
          effects.enter("mentionName")
          effects.enter("chunkString", { contentType: "string" })
          return name
        }

        function name(code: Code) {
          if (
            code == codes.eof ||
            code == codes.carriageReturn ||
            code == codes.lineFeed ||
            code == codes.carriageReturnLineFeed
          ) {
            return nok(code)
          }

          if (code == codes.rightSquareBracket) {
            effects.exit("chunkString")
            effects.exit("mentionName")
            effects.enter("mentionClose")
            effects.consume(code)
            effects.exit("mentionClose")
            effects.exit("mention")
            return ok
          }

          effects.consume(code)
          return name
        }
      },
    },
  },
}

//
// Convert micromark tokens to mdast nodes
//
//

const mentionFromMarkdown: FromMarkdownExtension = {
  enter: {
    mentionName(token) {
      this.enter(
        {
          type: "mention",
          value: "",
        },
        token
      )
      this.buffer()
    },
  },
  exit: {
    mentionName(token) {
      const data = this.resume()
      const node = this.stack[this.stack.length - 1]
      if (node.type !== "mention") {
        return
      }
      this.exit(token)
      node.value = data
    },
  },
}

//
// Convert mdast nodes to micromark tokens
//
//

const mentionToMarkdown: ToMarkdownExtension = {
  handlers: {
    mention(node) {
      return "@[" + node.value + "]"
    },
  },
}

export class MentionExtension extends NodeExtension<Mention> {
  proseMirrorNodeName(): string | null {
    return "mention"
  }

  proseMirrorNodeSpec(): NodeSpec | null {
    return {
      group: "inline",
      inline: true,
      atom: true,

      attrs: {
        name: { default: "" },
      },

      selectable: true,
      draggable: false,

      toDOM: node => {
        return [
          "span",
          {
            class: "prosemirror-mention-node",
          },
          "@" + node.attrs.name,
        ]
      },

      parseDOM: [
        {
          // match tag with following CSS Selector
          tag: "span[data-mention-name]",

          getAttrs: dom => {
            const name = dom.getAttribute("data-mention-name")
            return {
              name: name,
            }
          },
        },
      ],
    }
  }

  proseMirrorNodeToUnistNodes(node: Node): Mention[] {
    return [
      {
        type: "mention",
        value: node.attrs.name,
      },
    ]
  }

  unistNodeName(): "mention" {
    return "mention"
  }

  unistNodeToProseMirrorNodes(node: Mention, schema: Schema<string, string>, children: Node[]): Node[] {
    return [
      schema.nodes.mention.create(
        {
          name: node.value,
        },
        children
      ),
    ]
  }

  unifiedInitializationHook(
    processor: Processor<UnistNode, UnistNode, UnistNode, UnistNode, string>
  ): Processor<UnistNode, UnistNode, UnistNode, UnistNode, string> {
    const data = processor.data()
    data.fromMarkdownExtensions ??= []
    data.toMarkdownExtensions ??= []
    data.micromarkExtensions ??= []

    data.fromMarkdownExtensions.push(mentionFromMarkdown)
    data.toMarkdownExtensions.push(mentionToMarkdown)
    data.micromarkExtensions.push(mention)

    return processor
  }
}
