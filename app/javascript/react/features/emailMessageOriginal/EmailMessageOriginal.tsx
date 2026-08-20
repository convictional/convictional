import { getRouteApi, Link } from "@tanstack/react-router"
import { useEffect, useState } from "react"

import { apiFetch } from "~/react/shared/apiFetch"
import { useDocumentTitle } from "~/react/shared/hooks/useDocumentTitle"
import type { EmailMessage } from "~/react/shared/types"
import { DateTime } from "~/react/ui/DateTime"
import { ErrorState } from "~/react/ui/ErrorState"
import { LoadingState } from "~/react/ui/LoadingState"
import { StickyHeader } from "~/react/ui/StickyHeader"

// The route id carries the pathless shell parent prefix (shellRoute has id "shell").
const routeApi = getRouteApi("/shell/email_threads/$emailThreadId/email_messages/$emailMessageId")

export function EmailMessageOriginal() {
  const { emailThreadId: threadId, emailMessageId: messageId } = routeApi.useParams()
  const [message, setMessage] = useState<EmailMessage | null>(null)
  const [loadFailed, setLoadFailed] = useState(false)

  useDocumentTitle("Original message")

  useEffect(() => {
    let cancelled = false
    setMessage(null)
    setLoadFailed(false)
    apiFetch<EmailMessage>(`/api/email_threads/${threadId}/email_messages/${messageId}`)
      .then(response => {
        if (!cancelled) setMessage(response)
      })
      .catch(() => {
        if (!cancelled) setLoadFailed(true)
      })
    return () => {
      cancelled = true
    }
  }, [threadId, messageId])

  if (loadFailed) return <ErrorState message="Could not load this message." />
  if (!message) return <LoadingState className="py-8" />

  const messageDate = message.received_at ?? message.sent_at

  return (
    <div className="w-full max-w-4xl mx-auto min-w-0">
      <StickyHeader>
        <div className="p-4 border-b border-neutral">
          <h1 className="text-xl text-pretty font-accent">Original Message</h1>
        </div>
        <div className="flex items-center justify-between gap-2 p-2">
          <Link
            className="btn btn-square"
            to="/email_threads/$emailThreadId"
            params={{ emailThreadId: threadId }}
            aria-label="Back to thread"
          >
            <span className="material-symbols-outlined text-lg">arrow_back</span>
          </Link>
        </div>
      </StickyHeader>
      <div className="pb-24 grid gap-4">
        <div className="grid gap-4 px-2">
          <section className="bg-base-100 rounded-lg p-4 border border-base-300">
            <h2 className="text-lg font-semibold mb-3">Message Information</h2>
            <div className="grid grid-cols-[130px_1fr] gap-2 text-sm">
              <span className="font-medium text-base-content/70">External Thread ID</span>
              <span className="font-mono text-xs break-all">{message.external_thread_id}</span>
              <span className="font-medium text-base-content/70">Message ID</span>
              <span className="font-mono text-xs break-all">{message.message_id}</span>
              <span className="font-medium text-base-content/70">Subject</span>
              <span>{message.subject || "(no subject)"}</span>
              <span className="font-medium text-base-content/70">From</span>
              <span>{message.raw_sender || "(unknown)"}</span>
              <span className="font-medium text-base-content/70">To</span>
              <span>{message.to.join(", ") || "(none)"}</span>
              {message.cc.length > 0 && (
                <>
                  <span className="font-medium text-base-content/70">Cc</span>
                  <span>{message.cc.join(", ")}</span>
                </>
              )}
              {message.bcc.length > 0 && (
                <>
                  <span className="font-medium text-base-content/70">Bcc</span>
                  <span>{message.bcc.join(", ")}</span>
                </>
              )}
              <span className="font-medium text-base-content/70">Date</span>
              <span>{messageDate ? <DateTime datetime={messageDate} format="datetime_iso_8601" /> : "(unknown)"}</span>
            </div>
          </section>

          {message.headers.length > 0 && (
            <section className="bg-base-100 rounded-lg p-4 border border-base-300">
              <h2 className="text-lg font-semibold mb-3">Headers</h2>
              <div className="overflow-x-auto">
                <table className="table table-sm w-full">
                  <thead>
                    <tr>
                      <th className="w-1/4">Header</th>
                      <th>Value</th>
                    </tr>
                  </thead>
                  <tbody>
                    {message.headers.map((header, i) => (
                      <tr key={i}>
                        <td className="font-mono text-xs font-medium">{header.name}</td>
                        <td className="font-mono text-xs max-w-md overflow-x-auto">{header.value}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          {message.raw_data && (
            <section className="bg-base-100 rounded-lg p-4 border border-base-300">
              <h2 className="text-lg font-semibold mb-3">Raw Message Data</h2>
              <div className="bg-base-200 rounded p-4 overflow-auto max-h-96">
                <pre className="text-xs font-mono whitespace-pre-wrap break-all">
                  {JSON.stringify(message.raw_data, null, 2)}
                </pre>
              </div>
            </section>
          )}

          {message.body_plain && (
            <section className="bg-base-100 rounded-lg p-4 border border-base-300">
              <h2 className="text-lg font-semibold mb-3">Plain Text Body</h2>
              <div className="bg-base-200 rounded p-4 overflow-auto max-h-96">
                <pre className="text-sm whitespace-pre-wrap break-all">{message.body_plain}</pre>
              </div>
            </section>
          )}

          {message.body_html && (
            <section className="bg-base-100 rounded-lg p-4 border border-base-300">
              <h2 className="text-lg font-semibold mb-3">HTML Body</h2>
              <div className="bg-base-200 rounded p-4 overflow-auto max-h-96">
                <pre className="text-xs font-mono whitespace-pre-wrap break-all">{message.body_html}</pre>
              </div>
            </section>
          )}
        </div>
      </div>
    </div>
  )
}
