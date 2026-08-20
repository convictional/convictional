interface MailboxViewCoverageNoticeProps {
  considered: number | null
  eligible: number | null
}

// Tells the user when their inbox is larger than the slice generation organized, so the missing
// older items read as an explicit, bounded limit rather than a silent drop.
export function MailboxViewCoverageNotice({ considered, eligible }: MailboxViewCoverageNoticeProps) {
  if (considered === null || eligible === null || eligible <= considered) return null
  return (
    <div className="px-4 py-2 text-center text-xs text-base-500">
      Organizing your {considered} most recent conversations of {eligible}. Older items aren&apos;t included yet.
    </div>
  )
}
