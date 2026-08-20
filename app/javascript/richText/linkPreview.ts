// Mirrors the server-side extract_links_from_text (app/presenters/links.py) so
// the compose-time preview predicts the unfurl performed at submit. The markdown
// destination allows one level of balanced parens and backslash-escaped parens
// (the editor serializes hrefs with \( \) — see urlFormatting.ts), so a URL like
// .../Scheme_(programming_language) survives instead of truncating at the first ")".
const URL_PATTERN = /(?:\[[^\]]+\]\(((?:[^()\s\\]|\\[()]|\([^()]*\))+)\))|(https?:\/\/[^\s<>]+)/
const IMAGE_PATTERN = /!\[[^\]]*\]\([^)]+\)/g
const IMAGE_EXTENSION = /\.(jpe?g|png|gif|webp|svg|ico|bmp)(\?.*)?$/i
const TRAILING_PUNCT = /[.,;:!?]+$/

function trimBareUrl(url: string): string {
  // Strip trailing sentence punctuation, then drop a trailing ")" that has no
  // matching "(" — a URL wrapped in prose parens like "(https://example.com)" —
  // while keeping balanced parens that belong to the URL itself.
  let trimmed = url.replace(TRAILING_PUNCT, "")
  const count = (s: string, c: string) => s.split(c).length - 1
  while (trimmed.endsWith(")") && count(trimmed, ")") > count(trimmed, "(")) {
    trimmed = trimmed.slice(0, -1).replace(TRAILING_PUNCT, "")
  }
  return trimmed
}

function findPreviewUrl(content: string): string | null {
  const contentWithoutImages = content.replace(IMAGE_PATTERN, "")
  const match = contentWithoutImages.match(URL_PATTERN)
  if (!match) return null
  // Markdown destinations are explicitly delimited; only bare URLs need trimming.
  const url = match[1] !== undefined ? match[1].replace(/\\\(/g, "(").replace(/\\\)/g, ")") : trimBareUrl(match[2])
  if (IMAGE_EXTENSION.test(url)) return null
  return url
}

export { findPreviewUrl }
