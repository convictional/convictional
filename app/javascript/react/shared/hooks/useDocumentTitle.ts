import { useEffect } from "react"

// Client-side parity with the server's format_page_title filter
// (app/helpers/strings.py): "<title> - Convictional", with an environment
// prefix in non-production. The prefix ("[STAGING] ", "<dev label> | ", or "")
// is computed server-side by page_title_prefix() and stamped into the SPA shell
// as a meta tag, so the client doesn't re-derive the environment.
function readTitlePrefix(): string {
  return document.querySelector<HTMLMetaElement>('meta[name="page-title-prefix"]')?.content ?? ""
}

export function formatPageTitle(title: string): string {
  return `${readTitlePrefix()}${title} - Convictional`
}

export function useDocumentTitle(title: string): void {
  useEffect(() => {
    document.title = formatPageTitle(title)
  }, [title])
}
