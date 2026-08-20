import { useState } from "react"

import { ResourceBadge } from "~/react/composites/ResourceBadge"
import { EmptyStateSurface } from "~/react/ui/EmptyStateSurface"
import { showFlash } from "~/shared/flash"

// The first-user state for the chat index (no groups, no teammates): a segmented switch between
// creating a group and inviting the team, on the shared empty-state surface. Also shown in compose
// mode, where a solo user has no one to add. Self-retires once a group or teammate exists.

const SUGGESTED_GROUPS = ["General", "Leadership", "Engineering", "Sales"]

interface ChatFirstRunProps {
  onCreateGroup: (name: string) => Promise<void>
  onInvite: (email: string) => Promise<void>
}

// One-tap starter chips with a "name your own" reveal. Tapping a chip creates + opens that group.
function GroupChips({ onCreate }: { onCreate: (name: string) => Promise<void> }) {
  const [naming, setNaming] = useState(false)
  const [name, setName] = useState("")
  const [pendingName, setPendingName] = useState<string | null>(null)
  const busy = pendingName !== null

  const create = async (groupName: string) => {
    const trimmed = groupName.trim()
    if (!trimmed || busy) return
    setPendingName(trimmed)
    try {
      await onCreate(trimmed)
    } catch {
      showFlash("Couldn't create the group. Please try again.")
      setPendingName(null)
    }
  }

  if (naming) {
    return (
      <form
        className="flex w-full items-stretch gap-2"
        onSubmit={e => {
          e.preventDefault()
          create(name)
        }}
      >
        <input
          type="text"
          value={name}
          onChange={e => setName(e.target.value)}
          placeholder="Group name"
          aria-label="Group name"
          className="input min-w-0 flex-1 bg-base-200"
          autoFocus
          required
        />
        <button type="submit" className="btn btn-primary h-auto" disabled={busy || !name.trim()}>
          {busy ? <span className="loading loading-spinner loading-sm" /> : "Create"}
        </button>
      </form>
    )
  }

  return (
    <div className="flex flex-wrap justify-center gap-2">
      {SUGGESTED_GROUPS.map(group => (
        <button
          key={group}
          type="button"
          onClick={() => create(group)}
          disabled={busy}
          className="group inline-flex cursor-pointer items-center gap-1.5 rounded-full border border-base-300 bg-base-100 px-3 py-1.5 text-sm font-medium text-base-700 shadow-xs transition-colors hover:border-primary hover:bg-primary/10 hover:text-primary disabled:cursor-not-allowed disabled:opacity-50"
        >
          {pendingName === group ? (
            <span className="loading loading-spinner loading-xs" />
          ) : (
            <span className="material-symbols-outlined text-base text-base-content/40 group-hover:text-primary">
              add
            </span>
          )}
          {group}
        </button>
      ))}
      <button
        type="button"
        onClick={() => setNaming(true)}
        disabled={busy}
        className="inline-flex cursor-pointer items-center rounded-full border border-base-300 bg-base-100 px-3 py-1.5 text-sm font-medium text-base-700 shadow-xs transition-colors hover:border-primary hover:bg-primary/10 hover:text-primary disabled:opacity-50"
      >
        Name your own&hellip;
      </button>
    </div>
  )
}

// Email + Invite. The hook owns success/error flashes.
function InviteForm({ onInvite }: { onInvite: (email: string) => Promise<void> }) {
  const [email, setEmail] = useState("")
  const [submitting, setSubmitting] = useState(false)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    const trimmed = email.trim()
    if (!trimmed || submitting) return
    setSubmitting(true)
    try {
      await onInvite(trimmed)
      setEmail("")
    } catch {
      // flash already surfaced by the hook
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form className="flex w-full items-stretch gap-2" onSubmit={submit}>
      <input
        type="email"
        value={email}
        onChange={e => setEmail(e.target.value)}
        placeholder="name@company.com"
        aria-label="Teammate email"
        className="input flex-1 bg-base-200"
        required
      />
      <button type="submit" className="btn btn-primary h-auto" disabled={submitting || !email.trim()}>
        {submitting ? <span className="loading loading-spinner loading-sm" /> : "Invite"}
      </button>
    </form>
  )
}

export function ChatFirstRun({ onCreateGroup, onInvite }: ChatFirstRunProps) {
  const [tab, setTab] = useState<"group" | "invite">("group")
  const seg = (active: boolean) =>
    `cursor-pointer rounded-lg px-3.5 py-1.5 font-medium transition-colors ${
      active ? "bg-base-100 text-base-content shadow-sm" : "text-base-content/50"
    }`

  return (
    <EmptyStateSurface className="flex flex-col items-center px-6 pt-10 pb-8 text-center">
      <div className="mb-4 rounded-2xl border border-base-300 bg-base-50 p-1 shadow-sm">
        <ResourceBadge contentType="group" size="medium" />
      </div>
      <h2 className="font-accent text-lg text-base-content text-balance">Get your team started</h2>

      <div className="mt-4 inline-flex rounded-xl border border-base-300 bg-base-200 p-0.5 text-sm">
        <button type="button" className={seg(tab === "group")} onClick={() => setTab("group")}>
          Create a group
        </button>
        <button type="button" className={seg(tab === "invite")} onClick={() => setTab("invite")}>
          Invite people
        </button>
      </div>

      <div className="mt-5 w-full max-w-sm">
        {tab === "group" ? <GroupChips onCreate={onCreateGroup} /> : <InviteForm onInvite={onInvite} />}
      </div>
    </EmptyStateSurface>
  )
}
