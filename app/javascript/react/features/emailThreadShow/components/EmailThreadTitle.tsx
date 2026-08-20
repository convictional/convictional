import { Link } from "@tanstack/react-router"

import { MailboxStateBadge } from "~/react/composites/MailboxStateBadge"
import type { EmailThreadDetail, EmailThreadMailboxEntry } from "~/react/shared/types"

interface EmailThreadTitleProps {
  thread: EmailThreadDetail
  mailboxEntry: EmailThreadMailboxEntry
  // Live subject string (from useDraftSubjectListener). Falls back to the thread
  // title when no draft is in flight.
  subject: string
}

// The thread heading lives in the content area below the sticky toolbar: the
// subject with the shared-with-me badge flowing after it. The "shared with"
// collaborators and "assigned to" picker live in the sticky toolbar itself.
export function EmailThreadTitle({ thread, mailboxEntry, subject }: EmailThreadTitleProps) {
  const displaySubject = subject || thread.title || "No subject"
  return (
    <div className="px-2 pt-2 pb-4 flex items-start justify-between gap-2">
      {/* The shared/assigned badge flows as a suffix after the title, wrapping
          with it rather than sitting on its own line. */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 min-w-0">
        <h1 className="text-xl text-pretty font-accent wrap-anywhere line-clamp-3">{displaySubject}</h1>
        {mailboxEntry.is_shared && <MailboxStateBadge variant="shared" />}
      </div>
      {mailboxEntry.is_shared && thread.own_thread_id && (
        <Link
          to="/email_threads/$emailThreadId"
          params={{ emailThreadId: thread.own_thread_id }}
          className="btn btn-sm btn-ghost pr-1 flex-shrink-0"
        >
          View my copy
          <span className="material-symbols-outlined text-sm -mt-0.5">arrow_forward</span>
        </Link>
      )}
    </div>
  )
}
