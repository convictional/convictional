// Shared DOM-rewriting helpers for email body HTML.
//
// `processEmailQuotesInHtml` wraps the first `.quote_container` and every
// following sibling in a native `<details>` so the reader can collapse
// previously-quoted content. `wrapEmojiInHtml` wraps emoji glyphs in a `.emoji`
// span so they survive the dark-mode CSS filter that inverts the iframe body.
//
// Used by the React `QuotedHtmlNodeView`
// (app/javascript/react/composites/editor/QuotedHtmlNodeView.ts) and
// `EmailMessageBody` so both render identical iframe contents.

// Matches single emoji (with optional ZWJ sequences and variation selector) or regional-indicator flag pairs.
const EMOJI_RE =
  /(\p{Extended_Pictographic}[\u{1F3FB}-\u{1F3FF}]?(?:\p{Extended_Pictographic}[\u{1F3FB}-\u{1F3FF}]?)*️?|\p{Regional_Indicator}{2})/gu

export function wrapEmojiInHtml(htmlContent: string): string {
  const parser = new DOMParser()
  const doc = parser.parseFromString(htmlContent, "text/html")

  const walker = doc.createTreeWalker(doc.body, NodeFilter.SHOW_TEXT, {
    acceptNode: node => {
      const parentTag = node.parentElement?.tagName
      if (parentTag === "SCRIPT" || parentTag === "STYLE") return NodeFilter.FILTER_REJECT
      return NodeFilter.FILTER_ACCEPT
    },
  })

  const textNodes: Text[] = []
  let current: Node | null = walker.nextNode()
  while (current) {
    textNodes.push(current as Text)
    current = walker.nextNode()
  }

  for (const textNode of textNodes) {
    const text = textNode.nodeValue ?? ""
    EMOJI_RE.lastIndex = 0
    if (!EMOJI_RE.test(text)) continue
    EMOJI_RE.lastIndex = 0

    const fragment = doc.createDocumentFragment()
    let lastIndex = 0
    let match: RegExpExecArray | null
    while ((match = EMOJI_RE.exec(text)) !== null) {
      if (match.index > lastIndex) {
        fragment.appendChild(doc.createTextNode(text.slice(lastIndex, match.index)))
      }
      const span = doc.createElement("span")
      span.className = "emoji"
      span.textContent = match[0]
      fragment.appendChild(span)
      lastIndex = match.index + match[0].length
    }
    if (lastIndex < text.length) {
      fragment.appendChild(doc.createTextNode(text.slice(lastIndex)))
    }
    textNode.parentNode?.replaceChild(fragment, textNode)
  }

  return doc.body.innerHTML
}

export function processEmailQuotesInHtml(htmlContent: string): string {
  const parser = new DOMParser()
  const doc = parser.parseFromString(htmlContent, "text/html")

  // The first .quote_container marks the start of the collapsible region.
  // It and every subsequent sibling moves inside <details>, so trailing
  // signatures or stray text after the quote collapse together with it.
  const quoteContainer = doc.querySelector<HTMLElement>(".quote_container")
  if (!quoteContainer) return doc.body.innerHTML

  const parent = quoteContainer.parentNode
  if (!parent) return doc.body.innerHTML

  const details = doc.createElement("details")
  details.className = "email-quote-collapse-container"

  const summary = doc.createElement("summary")
  summary.className = "email-quote-toggle"
  summary.textContent = "..."
  summary.setAttribute("aria-label", "Show previous message")

  const wrapper = doc.createElement("div")
  wrapper.className = "email-quote-content"

  parent.insertBefore(details, quoteContainer)

  const siblings: Node[] = []
  let cursor: Node | null = quoteContainer
  while (cursor) {
    siblings.push(cursor)
    cursor = cursor.nextSibling
  }
  for (const sibling of siblings) {
    wrapper.appendChild(sibling)
  }

  details.appendChild(summary)
  details.appendChild(wrapper)

  return doc.body.innerHTML
}
