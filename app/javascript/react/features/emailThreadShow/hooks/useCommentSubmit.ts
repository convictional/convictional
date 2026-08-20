import { useCallback, useState } from "react"

import { apiFetch } from "~/react/shared/apiFetch"
import type { EmailThreadComment } from "~/react/shared/types"
import { isBlankMarkdown } from "~/richText/schema"

interface UseCommentSubmitOptions {
  threadId: string
  onSuccess?: (comment: EmailThreadComment) => void
}

interface UseCommentSubmitResult {
  // Posts a comment under the given attachment claim id (owned and rotated by the
  // composer). Resolves to the created comment on success or null on failure;
  // unfurlLinks defaults to true, pass false when the composer's link preview was
  // dismissed so the posted comment gets no card. Pass replyToId to quote-reply
  // to another comment in this thread.
  send: (
    markdown: string,
    claimId: string,
    unfurlLinks?: boolean,
    replyToId?: string | null
  ) => Promise<EmailThreadComment | null>
  sending: boolean
}

export function useCommentSubmit({ threadId, onSuccess }: UseCommentSubmitOptions): UseCommentSubmitResult {
  const [sending, setSending] = useState(false)

  const send = useCallback(
    async (markdown: string, claimId: string, unfurlLinks: boolean = true, replyToId: string | null = null) => {
      const trimmed = markdown.trimEnd()
      if (isBlankMarkdown(markdown) || sending) return null
      setSending(true)
      try {
        const comment = await apiFetch<EmailThreadComment>(`/api/email_threads/${threadId}/comments`, {
          method: "POST",
          body: JSON.stringify({
            content: trimmed,
            attachment_claim_id: claimId,
            unfurl_links: unfurlLinks,
            ...(replyToId ? { reply_to_id: replyToId } : {}),
          }),
        })
        onSuccess?.(comment)
        return comment
      } catch {
        // The composer surfaces the failure (onSubmit resolves null → keeps the
        // draft and shows its error), so the hook doesn't track error state.
        return null
      } finally {
        setSending(false)
      }
    },
    [sending, threadId, onSuccess]
  )

  return { send, sending }
}
