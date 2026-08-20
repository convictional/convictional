import { useState } from "react"

import { useCurrentUser } from "~/react/shared/hooks/useCurrentUser"
import { ErrorState } from "~/react/ui/ErrorState"
import { LoadingState } from "~/react/ui/LoadingState"
import { StickyHeader } from "~/react/ui/StickyHeader"

import { InviteForm } from "./components/InviteForm"
import { Tabs, type ActiveTab } from "./components/Tabs"
import { UserRow } from "./components/UserRow"
import { useOrganizationUsersState } from "./useOrganizationUsersState"

// The "Team Members" admin surface. Identity (the "(you)" label and hiding
// actions on yourself) comes from useCurrentUser() rather than props, so the
// mount div carries no data-props.
export function OrganizationUsers() {
  const { users, loading, error, upsertUser } = useOrganizationUsersState()
  const { user: currentUser, error: currentUserError } = useCurrentUser()
  const [activeTab, setActiveTab] = useState<ActiveTab>("active")

  // Don't render rows until we know who the current user is. Otherwise a cold-load
  // race (the member list resolving before /api/users/me) would briefly show
  // self-actions and a missing "(you)" label on the admin's own row. If identity
  // fails to load entirely, fall through and render read-only (currentUserId null).
  const currentUserResolved = currentUser != null || currentUserError != null
  if (loading || !currentUserResolved) return <LoadingState />
  if (error || !users) return <ErrorState message="Could not load team members." />

  const currentUserId = currentUser?.id ?? null
  const visible = users.filter(u => (activeTab === "active" ? u.active : !u.active))
  const emptyMessage = activeTab === "deleted" ? "No members have been deactivated." : "No active members."

  return (
    <div id="org-users-list">
      <StickyHeader>
        <div className="flex items-center gap-2 p-2">
          <h1 className="text-lg font-accent px-1">Team Members</h1>
        </div>
      </StickyHeader>
      <div className="px-2 space-y-8">
        <section className="space-y-2">
          <h2 className="text-sm font-semibold text-base-content/60 px-1">Invite a teammate</h2>
          <div className="rounded-2xl border border-base-300 bg-base-50 p-4">
            <InviteForm onInvited={upsertUser} />
          </div>
        </section>
        <section className="space-y-3">
          <Tabs activeTab={activeTab} onTabChange={setActiveTab} />
          {visible.length === 0 ? (
            <div className="rounded-2xl border border-base-300 bg-base-50 px-4 py-8 text-center text-sm text-base-content/60">
              {emptyMessage}
            </div>
          ) : (
            <div className="rounded-2xl border border-base-300 overflow-hidden">
              {visible.map(user => (
                <UserRow key={user.id} user={user} currentUserId={currentUserId} onUpdated={upsertUser} />
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  )
}
