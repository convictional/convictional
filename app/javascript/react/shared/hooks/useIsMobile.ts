// Source of truth lives server-side in `RequestContext.is_mobile`
// (User-Agent sniffing) and is published as `data-is-mobile` on <html> by the
// server layouts (application.html.jinja and the SPA shell spa.html.jinja). UA
// is fixed for the document's lifetime, so this is a plain read — no
// subscription needed.
export function useIsMobile(): boolean {
  return document.documentElement.dataset.isMobile === "true"
}
