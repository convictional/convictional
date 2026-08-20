// A URL is safe to hand to an href/src only if it uses http(s); this rejects
// javascript:, data:, and other schemes that could execute in a link context.
export const isSafeUrl = (url: string) => /^https?:\/\//.test(url)

// Favicon for a domain via Google's public favicon service. Works even when the
// origin blocked our scraper (Google already holds the icon), and returns a generic
// globe for unknown domains — so a branded fallback card renders for any link.
export const faviconUrl = (domain: string) =>
  `https://www.google.com/s2/favicons?domain=${encodeURIComponent(domain)}&sz=64`

// Server routes the React inbox links to directly. The SPA shell has no props to
// carry the url_for() values the deleted Jinja template used to serialize, so the
// client builds them; this is their single registry.
// gmailAuthUrl mirrors integrations_gmail_auth in integrations/google/router.py —
// its return_to is a real Query param, so callers stamp the URL to return to.
export const gmailAuthUrl = (returnTo: string) => `/integrations/gmail/auth?return_to=${encodeURIComponent(returnTo)}`

// Mirrors integrations_google_calendar_login in integrations/google/router.py.
// That handler doesn't bind return_to as a Query param (it reads a remembered
// location instead), so the return_to here is inert and stays constant.
export const calendarAuthUrl = "/integrations/google_calendar/login?return_to=/"

// Split "/path?a=1#h" into the parts TanStack's <Link>/navigate want separately:
// route matching keys off the pathname, while the query and hash pass through so
// they survive a client transition instead of forcing a full-document load.
export function splitHref(href: string): { pathname: string; search: Record<string, string>; hash: string } {
  const hashIndex = href.indexOf("#")
  const hash = hashIndex >= 0 ? href.slice(hashIndex) : ""
  const withoutHash = hashIndex >= 0 ? href.slice(0, hashIndex) : href
  const queryIndex = withoutHash.indexOf("?")
  const pathname = queryIndex >= 0 ? withoutHash.slice(0, queryIndex) : withoutHash
  const search = Object.fromEntries(new URLSearchParams(queryIndex >= 0 ? withoutHash.slice(queryIndex + 1) : ""))
  return { pathname, search, hash }
}
