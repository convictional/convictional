import { markdownToSegments } from "./segments"

interface ToPlainTextOptions {
  maxLength?: number
  collapse?: boolean
}

export function markdownToPlainText(source: string, options?: ToPlainTextOptions): string {
  if (!source) return ""

  if (options?.maxLength !== undefined && options.maxLength <= 0) return ""

  const collapse = options?.collapse ?? true

  let text = markdownToSegments(source)
    .map(segment => segment.value)
    .join("")

  if (collapse) {
    text = text.replace(/\s+/g, " ").trim()
  }

  if (options?.maxLength !== undefined && text.length > options.maxLength) {
    return text.slice(0, options.maxLength - 1).trimEnd() + "…"
  }
  return text
}
