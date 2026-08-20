export function detectLinkHref(text: string): string {
  const hasScheme = /^https?:\/\/\S+$/.test(text)
  if (hasScheme) {
    return text
  }
  const looksLikeDomain = /^[^\s]+\.[a-z]{2,}\S*$/i.test(text)
  if (looksLikeDomain) {
    return `https://${text}`
  }
  return "https://example.com"
}

export function isValidHref(href: string): boolean {
  const trimmed = href.trim()
  return trimmed.length > 0 && /^https?:\/\//i.test(trimmed)
}
