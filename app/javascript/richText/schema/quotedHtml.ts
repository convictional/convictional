import { toHtml } from "hast-util-to-html"
import { directiveFromMarkdown, directiveToMarkdown } from "mdast-util-directive"
import { toHast } from "mdast-util-to-hast"
import { directive } from "micromark-extension-directive"
import { Node, NodeSpec, Schema } from "prosemirror-model"
import { NodeExtension } from "prosemirror-unified"
import { Processor } from "unified"
import { Node as UnistNode } from "unist"
import { visit } from "unist-util-visit"
export interface QuotedHtmlDirective extends UnistNode {
  type: "containerDirective"
  name: "quoted_html"
  children?: UnistNode[]
  attributes?: {
    collapsed?: string
  }
}

function extractHtmlContent(node: QuotedHtmlDirective): string {
  if (!node.children) return ""

  // Convert each MDAST child to HAST, then to HTML
  return node.children
    .map(child => {
      const hast = toHast(child, { allowDangerousHtml: true })
      return hast ? toHtml(hast, { allowDangerousHtml: true }) : ""
    })
    .join("")
}

function quotedHtmlDirectivePlugin() {
  return (tree: UnistNode) => {
    visit(tree, (node: UnistNode) => {
      if (node.type === "containerDirective" && "name" in node && node.name === "quoted_html") {
        const data = node.data || (node.data = {})
        const directiveNode = node as QuotedHtmlDirective

        ;(data as Record<string, unknown>).hName = "div"

        const htmlContent = extractHtmlContent(directiveNode)

        const hProperties: Record<string, unknown> = {
          "data-quoted-html": "true",
          "data-html-content": htmlContent,
        }

        // Extract collapsed attribute if it exists
        const collapsed = directiveNode.attributes?.collapsed

        if (collapsed === "true") {
          hProperties["data-collapsed"] = "true"
        }

        ;(data as Record<string, unknown>).hProperties = hProperties
      }
    })
  }
}

export class QuotedHtmlExtension extends NodeExtension<QuotedHtmlDirective> {
  proseMirrorNodeName(): string | null {
    return "quoted_html"
  }

  proseMirrorNodeSpec(): NodeSpec | null {
    return {
      group: "block",
      atom: true,

      attrs: {
        htmlContent: { default: "" },
        collapsed: { default: false },
      },

      selectable: true,
      draggable: true,

      toDOM: node => {
        if (node.attrs.collapsed) {
          // Create outer Alpine container
          const alpineContainer = document.createElement("div")
          alpineContainer.setAttribute("x-data", "{ collapsed: true }")
          alpineContainer.setAttribute("data-collapsed", "true")

          // Create toggle badge
          const toggleBadge = document.createElement("div")
          toggleBadge.className =
            "inline-flex items-center px-2 py-1 text-xs bg-base-100 text-base-600 rounded-full cursor-pointer mb-2"
          toggleBadge.setAttribute("x-on:click", "collapsed = !collapsed")
          toggleBadge.textContent = "..."

          alpineContainer.appendChild(toggleBadge)

          // Create content wrapper that shows/hides
          const contentWrapper = document.createElement("div")
          contentWrapper.setAttribute("x-show", "!collapsed")
          contentWrapper.setAttribute("x-transition", "")

          // Create the actual email content div
          const emailContentDiv = document.createElement("div")
          emailContentDiv.className = "border-l-4 border-base-300 pl-4 py-2 bg-base-50 rounded-r-md"
          emailContentDiv.setAttribute(
            "x-email-content",
            JSON.stringify({ content: node.attrs.htmlContent, isMobile: false })
          )

          contentWrapper.appendChild(emailContentDiv)
          alpineContainer.appendChild(contentWrapper)

          return alpineContainer
        } else {
          // Non-collapsed version - just the email content div
          const wrapper = document.createElement("div")
          wrapper.className = "border-l-4 border-base-300 pl-4 py-2 my-4 bg-base-50 rounded-r-md"
          wrapper.setAttribute("x-email-content", JSON.stringify({ content: node.attrs.htmlContent, isMobile: false }))
          return wrapper
        }
      },

      parseDOM: [
        {
          tag: "div[data-html-content]",
          getAttrs: dom => {
            const element = dom as HTMLElement
            const htmlContent = element.getAttribute("data-html-content") || ""
            const collapsed = element.hasAttribute("data-collapsed")

            return {
              htmlContent,
              collapsed,
            }
          },
        },
      ],
    }
  }

  proseMirrorNodeToUnistNodes(node: Node): QuotedHtmlDirective[] {
    const directive: QuotedHtmlDirective = {
      type: "containerDirective",
      name: "quoted_html",
      children: [
        {
          type: "html",
          value: node.attrs.htmlContent,
        } as UnistNode,
      ],
    }

    if (node.attrs.collapsed) {
      directive.attributes = { collapsed: "true" }
    }

    return [directive]
  }

  unistNodeName(): "containerDirective" {
    return "containerDirective"
  }

  unistNodeToProseMirrorNodes(node: QuotedHtmlDirective, schema: Schema<string, string>): Node[] {
    const htmlContent = extractHtmlContent(node)
    const collapsed = node.attributes?.collapsed === "true"

    return [
      schema.nodes.quoted_html.create({
        htmlContent,
        collapsed,
      }),
    ]
  }

  unistToProseMirrorTest(node: UnistNode): boolean {
    return node.type === "containerDirective" && "name" in node && node.name === "quoted_html"
  }

  unifiedInitializationHook(
    processor: Processor<UnistNode, UnistNode, UnistNode, UnistNode, string>
  ): Processor<UnistNode, UnistNode, UnistNode, UnistNode, string> {
    return processor
      .use(function remarkDirective() {
        // This is a fix for overzealous directive parsing in remark-directive.
        // TextDirective parsing greedily consumes single colons and causes parsing issues.
        // This is particularly bad with the email forward header "To: ..."
        // https://github.com/remarkjs/remark-directive/issues/19
        const data = this.data()
        const { flow } = directive()

        data.toMarkdownExtensions ??= []
        data.fromMarkdownExtensions ??= []
        data.micromarkExtensions ??= []

        data.micromarkExtensions.push({ flow })
        data.fromMarkdownExtensions.push(directiveFromMarkdown())
        data.toMarkdownExtensions.push(directiveToMarkdown())
      })
      .use(quotedHtmlDirectivePlugin)
  }
}
