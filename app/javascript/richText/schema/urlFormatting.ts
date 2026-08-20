import { Link, Text } from "mdast"
import { type Options as ToMarkdownExtension, type State, type Info, type SafeConfig } from "mdast-util-to-markdown"
import { Extension } from "prosemirror-unified"
import { Processor } from "unified"
import type { Node as UnistNode, Parent } from "unist"

// Regex to check if entire string is a URL (matches http:// or https:// URLs)
const IS_ENTIRE_STRING_URL_PATTERN = /^https?:\/\/\S+$/

// Regex to find URLs anywhere within text
const CONTAINS_URL_PATTERN = /(https?:\/\/[^\s)>]+)/g

/**
 * Check if the link text is a URL
 */
function isLinkTextUrl(node: Link): boolean {
  if (node.children.length !== 1) return false
  const child = node.children[0]
  if (child.type !== "text") return false
  return IS_ENTIRE_STRING_URL_PATTERN.test(child.value)
}

/**
 * Custom link handler that doesn't escape underscores when the link text is a URL
 */
function linkHandler(node: Link, _parent: Parent | undefined, state: State, info: Info): string {
  const tracker = state.createTracker(info)
  const exit = state.enter("link")
  const subexit = state.enter("label")

  let value = tracker.move("[")

  // If the link text is a URL, serialize it directly without escaping
  if (isLinkTextUrl(node)) {
    const textNode = node.children[0] as { type: "text"; value: string }
    value += tracker.move(textNode.value)
  } else {
    // Use default phrasing serialization for non-URL text
    value += tracker.move(
      state.containerPhrasing(node, {
        before: value,
        after: "](",
        ...tracker.current(),
      })
    )
  }

  value += tracker.move("](")
  subexit()

  // Serialize the URL (href)
  const destinationSubexit = state.enter("destinationRaw")

  // For the href part, we need to handle special characters carefully
  // Parentheses need to be escaped in markdown URLs, but underscores and ampersands should not be
  const urlForHref = node.url
    .replace(/\(/g, "\\(") // Escape opening parentheses
    .replace(/\)/g, "\\)") // Escape closing parentheses

  value += tracker.move(urlForHref)
  destinationSubexit()

  // Handle title if present
  if (node.title) {
    const quote = state.options.quote || '"'
    const suffix = quote === '"' ? "Quote" : "Apostrophe"
    const titleSubexit = state.enter(`title${suffix}`)
    value += tracker.move(" " + quote)
    value += tracker.move(
      state.safe(node.title, {
        before: value,
        after: quote,
        ...tracker.current(),
      })
    )
    value += tracker.move(quote)
    titleSubexit()
  }

  value += tracker.move(")")
  exit()

  return value
}

/**
 * Custom text handler that doesn't escape underscores or ampersands within URLs
 */
function textHandler(node: Text, _parent: Parent | undefined, state: State, info: SafeConfig): string {
  const text = node.value

  // Check if the text contains URLs
  if (!text.match(CONTAINS_URL_PATTERN)) {
    // No URLs, use default safe serialization
    return state.safe(text, info)
  }

  // First, let state.safe() do its normal escaping
  let escapedText = state.safe(text, info)

  // Then, post-process to remove backslash escapes from within URLs
  escapedText = escapedText.replace(CONTAINS_URL_PATTERN, url => {
    // Remove backslash escapes from underscores and ampersands within this URL
    return url.replace(/\\_/g, "_").replace(/\\&/g, "&")
  })

  return escapedText
}

const urlFormattingToMarkdown: ToMarkdownExtension = {
  handlers: {
    link: linkHandler,
    text: textHandler,
  },
}

export class UrlFormattingExtension extends Extension {
  public unifiedInitializationHook(
    processor: Processor<UnistNode, UnistNode, UnistNode, UnistNode, string>
  ): Processor<UnistNode, UnistNode, UnistNode, UnistNode, string> {
    const data = processor.data()
    data.toMarkdownExtensions ??= []
    data.toMarkdownExtensions.push(urlFormattingToMarkdown)

    return processor as unknown as Processor<UnistNode, UnistNode, UnistNode, UnistNode, string>
  }
}
