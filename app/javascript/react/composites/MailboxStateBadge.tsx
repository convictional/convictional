type MailboxStateBadgeVariant = "assigned" | "shared"

interface MailboxStateBadgeProps {
  variant: MailboxStateBadgeVariant
  className?: string
}

const VARIANT_LABEL: Record<MailboxStateBadgeVariant, string> = {
  assigned: "Assigned to me",
  shared: "Shared with me",
}

// Keep the blue identity of the originals but drop the high-contrast outline:
// "Assigned to me" is a solid fill (no redundant same-color border), "Shared with
// me" is a light tint softened by a faint border instead of the loud one.
const VARIANT_STYLE: Record<MailboxStateBadgeVariant, string> = {
  assigned: "bg-primary text-white",
  shared: "bg-info text-info-content border border-info-content/25",
}

export function MailboxStateBadge({ variant, className }: MailboxStateBadgeProps) {
  return (
    <span
      className={`inline-flex shrink-0 items-center whitespace-nowrap rounded-sm px-1.5 py-0.5 text-xs ${VARIANT_STYLE[variant]}${
        className ? ` ${className}` : ""
      }`}
    >
      {VARIANT_LABEL[variant]}
    </span>
  )
}
