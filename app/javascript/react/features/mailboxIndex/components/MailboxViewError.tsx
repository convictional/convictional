import { EmptyState } from "~/react/ui/EmptyState"

interface MailboxViewErrorProps {
  message: string
}

export function MailboxViewError({ message }: MailboxViewErrorProps) {
  return <EmptyState title="Unable to organize emails" text={message} />
}
