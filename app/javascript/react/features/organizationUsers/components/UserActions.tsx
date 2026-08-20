import { type ReactNode, useState } from "react"

import { confirm } from "~/react/composites/confirmationDialog/confirm"
import { apiFetch } from "~/react/shared/apiFetch"
import { Tooltip } from "~/react/ui/Tooltip"
import { showFlash } from "~/shared/flash"

import type { OrganizationUser } from "../types"

interface UserActionsProps {
  user: OrganizationUser
  currentUserId: string | null
  onUpdated: (user: OrganizationUser) => void
}

interface ActionButtonProps {
  label: string
  icon: string
  disabled: boolean
  onClick: () => void
}

function ActionButton({ label, icon, disabled, onClick }: ActionButtonProps) {
  return (
    <Tooltip content={label}>
      <button
        type="button"
        aria-label={label}
        disabled={disabled}
        onClick={onClick}
        className="cursor-pointer flex items-center text-base-content/60 hover:text-base-content disabled:opacity-50"
      >
        <span className="material-symbols-outlined text-lg">{icon}</span>
      </button>
    </Tooltip>
  )
}

// Promote/demote (PATCH {is_admin}) and deactivate/restore (PATCH {active}) for a member.
export function UserActions({ user, currentUserId, onUpdated }: UserActionsProps): ReactNode {
  const [submitting, setSubmitting] = useState(false)

  // Hide actions on your own row — and also whenever the current user is unknown
  // (identity failed to load): treating a null id as "not me" would offer
  // self-mutation the server rejects with 422. Safety lives here, at the leaf
  // that relies on it, not only in the parent's render gate.
  if (currentUserId == null || user.id === currentUserId) return null

  async function patch(body: { is_admin?: boolean; active?: boolean }, errorMessage: string) {
    setSubmitting(true)
    try {
      // The PATCH returns the updated member — apply it directly. Other sessions
      // reconcile via the ORGANIZATION_MEMBERS broadcast, so no refetch here.
      const updated = await apiFetch<OrganizationUser>(`/api/organization/users/${user.id}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      })
      onUpdated(updated)
    } catch {
      showFlash(errorMessage, "error")
    } finally {
      setSubmitting(false)
    }
  }

  if (!user.active) {
    return (
      <ActionButton
        label="Add user back to organization"
        icon="person_add"
        disabled={submitting}
        onClick={() => void patch({ active: true }, "Could not restore the member. Please try again.")}
      />
    )
  }

  async function deactivate() {
    const ok = await confirm({
      message: `Remove ${user.display_name} (${user.email}) from the organization?`,
    })
    if (!ok) return
    await patch({ active: false }, "Could not deactivate the member. Please try again.")
  }

  return (
    <>
      <ActionButton
        label={user.is_admin ? "Remove admin privileges" : "Make this user an admin"}
        icon={user.is_admin ? "remove_moderator" : "add_moderator"}
        disabled={submitting}
        onClick={() =>
          void patch({ is_admin: !user.is_admin }, "Could not update admin privileges. Please try again.")
        }
      />
      <ActionButton
        label="Remove user from organization"
        icon="delete"
        disabled={submitting}
        onClick={() => void deactivate()}
      />
    </>
  )
}
