// The attachment upload endpoint accepts an optional workspace scope: pass a
// workspaceId to scope ownership to that workspace (chat, meeting agenda, post
// comments, email thread comments), or omit it for org-wide uploads (post body).
export function attachmentUploadUrl(workspaceId?: string): string {
  return workspaceId ? `/api/workspaces/${workspaceId}/attachments` : "/api/workspaces/attachments"
}
