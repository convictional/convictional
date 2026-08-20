import type { Element, Root } from "hast"
import { visit } from "unist-util-visit"

// User-authored content sometimes embeds an image by an `http://` URL (e.g.
// pasted from an old CMS export). On our HTTPS pages that is mixed content:
// modern browsers already auto-upgrade a mixed-content <img> to https and block
// it if that fails, so an http-only host never renders regardless. What the
// browser's auto-upgrade doesn't do is keep our report-only `img-src ... https:`
// CSP quiet — the http src still trips a violation report. (An enforcing CSP
// could upgrade via `upgrade-insecure-requests`, but ours ships Report-Only in
// prod; see app/middleware/security.py.) Rewriting the scheme here matches the
// request the browser would make anyway and silences the report. It can't break
// a working image: on any current browser a passive http image on an https page
// was never loading over http to begin with.
const HTTP_PREFIX = /^http:\/\//i

export function rehypeUpgradeImageProtocol() {
  return (tree: Root) => {
    visit(tree, "element", (node: Element) => {
      if (node.tagName !== "img" || !node.properties) return
      const src = node.properties.src
      if (typeof src === "string" && HTTP_PREFIX.test(src)) {
        node.properties.src = src.replace(HTTP_PREFIX, "https://")
      }
    })
  }
}
