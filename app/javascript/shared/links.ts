import { find as findLinks } from "linkifyjs"

// Link protocols we treat as safe; callers reject anything else (javascript:, data:, file:, ftp:, etc.).
export const ALLOWED_LINK_PROTOCOLS = new Set(["http:", "https:"])

export function findUrlMatches(text: string): { start: number; end: number; href: string }[] {
  return findLinks(text, "url", { defaultProtocol: "https" }).filter(match => {
    try {
      return ALLOWED_LINK_PROTOCOLS.has(new URL(match.href).protocol)
    } catch {
      return false
    }
  })
}
