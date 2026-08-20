// Shared presentational atoms for member surfaces (ProfileCard, the org-users
// admin cards/rows), so the admin-shield badge and group pill render identically
// everywhere rather than drifting per copy.

export function AdminBadge() {
  return (
    <div className="inline-flex items-center gap-1 text-xs text-base-content/50">
      <span className="material-symbols-outlined text-sm">shield</span>
      <span>Admin</span>
    </div>
  )
}

export function GroupPill({ name }: { name: string }) {
  return (
    <span className="inline-flex items-center gap-1 text-xs text-base-content/50 bg-base-300 rounded-full px-2 py-0.5">
      <span className="material-symbols-outlined text-xs">group</span>
      {name}
    </span>
  )
}
