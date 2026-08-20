// The "request access" affordance shown when an API denies access (403). Shared
// by the read-only document show page, the editor, and the email thread show
// page, which all turn a denied resource into this CTA rather than a dead-end
// error. `resourceLabel` fills the noun in the copy ("document" by default,
// "thread" for email). Pair with accessDeniedUrl (shared/apiFetch.ts) to pull
// the request-access URL out of the 403.
export function RequestDocumentAccess({
  requestAccessUrl,
  resourceLabel = "document",
}: {
  requestAccessUrl: string
  resourceLabel?: string
}) {
  return (
    <div className="px-4 py-12 text-center space-y-3">
      <p className="text-sm font-semibold text-base-content">You don&apos;t have access to this {resourceLabel}</p>
      <p className="text-sm text-base-content/60">Ask a collaborator for access to view or edit it.</p>
      <a href={requestAccessUrl} className="btn btn-primary" data-testid="request-document-access">
        <span className="material-symbols-outlined text-lg">person_add</span>
        Request access
      </a>
    </div>
  )
}
