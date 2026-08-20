import { useCurrentUser } from "~/react/shared/hooks/useCurrentUser"
import { DateTime, type DateTimeFormat } from "~/react/ui/DateTime"

interface UserDateTimeProps {
  datetime: string
  format?: DateTimeFormat
  className?: string
}

// Renders ui/DateTime with the current user's configured timezone sourced from
// the currentUser store, so timestamps match the tz the server rendered against
// rather than the browser's. ui/DateTime stays a pure, tz-agnostic formatter
// (it can't read app state); this composite injects the domain context.
export function UserDateTime({ datetime, format, className }: UserDateTimeProps) {
  const { user } = useCurrentUser()
  return <DateTime datetime={datetime} format={format} className={className} timezone={user?.time_zone ?? null} />
}
