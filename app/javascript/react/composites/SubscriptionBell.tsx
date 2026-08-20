// One toggle, two server-side surfaces: `Notifier` (email/push) and
// `SyncMailboxJob` (inbox) both resolve through `SubscriberResolver`, so
// RELEVANT_ONLY silences both.

import { useEffect, useState } from "react"
import { createPortal } from "react-dom"

import { ApiError, apiFetch } from "~/react/shared/apiFetch"
import type { SubscriptionLevel } from "~/react/shared/types"
import { Dropdown } from "~/react/ui/Dropdown"

export interface SubscriptionState {
  wants_all: boolean
  is_explicit: boolean
}

export interface SubscriptionOptionCopy {
  label?: string
  hint?: string
}

export interface SubscriptionBellProps {
  workspaceId: string
  // Optional one-line note rendered above the menu options. Useful for
  // context like "Sent to everyone." on broadcast posts; the user can still
  // adjust follow-up notifications via the menu below.
  subtitle?: string
  // Per-option copy overrides. Defaults are intentionally generic so most
  // surfaces only override `default.hint` (e.g. "Use your post settings").
  options?: {
    all?: SubscriptionOptionCopy
    relevant?: SubscriptionOptionCopy
    default?: SubscriptionOptionCopy
  }
  // URL to the page where group/global notification settings are managed.
  // When provided, renders a small footer link below the menu options.
  manageUrl?: string
  // Trigger button size. Defaults to "md" to match the existing post header.
  // Use "sm" alongside other btn-sm action buttons (e.g. the chat header).
  size?: "sm" | "md"
  // When set, the bell renders into the given DOM node via createPortal. Used
  // by host islands (e.g. DocumentEditor) that want to embed the bell without
  // a separate mount, but need the bell to live in a server-rendered slot.
  portalTarget?: HTMLElement | null
}

interface Copy {
  label: string
  hint: string
}

const DEFAULT_COPY: { all: Copy; relevant: Copy; default: Copy } = {
  all: { label: "All", hint: "Every comment and update" },
  relevant: { label: "Relevant to me", hint: "@mentions only" },
  default: { label: "Default", hint: "Use your settings" },
}

function copyFor(key: keyof typeof DEFAULT_COPY, override?: SubscriptionOptionCopy): Copy {
  return {
    label: override?.label ?? DEFAULT_COPY[key].label,
    hint: override?.hint ?? DEFAULT_COPY[key].hint,
  }
}

export function SubscriptionBell({
  workspaceId,
  subtitle,
  options,
  manageUrl,
  size = "md",
  portalTarget,
}: SubscriptionBellProps) {
  const [state, setState] = useState<SubscriptionState | null>(null)

  useEffect(() => {
    let cancelled = false
    apiFetch<SubscriptionState>(`/api/workspaces/${workspaceId}/subscription`)
      .then(data => {
        if (!cancelled) setState(data)
      })
      .catch(() => {
        if (!cancelled) setState({ wants_all: false, is_explicit: false })
      })
    return () => {
      cancelled = true
    }
  }, [workspaceId])

  const trigger = (
    <button
      type="button"
      aria-label="Subscription preferences"
      title="Notifications"
      className={`btn btn-square cursor-pointer${size === "sm" ? " btn-sm" : ""}`}
    >
      <span className="material-symbols-outlined text-lg">
        {state?.wants_all ? "notifications" : "notifications_off"}
      </span>
    </button>
  )

  const content = (
    <Dropdown trigger={trigger} placement="bottom-end" className="dropdown-card p-2 w-72 z-50" initialFocus={-1}>
      {state ? (
        <Menu
          workspaceId={workspaceId}
          state={state}
          onChange={setState}
          subtitle={subtitle}
          options={options}
          manageUrl={manageUrl}
        />
      ) : (
        <div className="flex justify-center py-4">
          <span className="loading loading-spinner loading-xs" />
        </div>
      )}
    </Dropdown>
  )

  return portalTarget ? createPortal(content, portalTarget) : content
}

interface MenuProps {
  workspaceId: string
  state: SubscriptionState
  onChange: (state: SubscriptionState) => void
  subtitle?: string
  options?: SubscriptionBellProps["options"]
  manageUrl?: string
}

function Menu({ workspaceId, state, onChange, subtitle, options, manageUrl }: MenuProps) {
  const all = copyFor("all", options?.all)
  const relevant = copyFor("relevant", options?.relevant)
  const fallback = copyFor("default", options?.default)

  const isFollowing = state.is_explicit && state.wants_all
  const isOnlyRelevant = state.is_explicit && !state.wants_all
  const isDefault = !state.is_explicit

  async function setLevel(level: SubscriptionLevel) {
    const previous = state
    onChange({ wants_all: level === "all", is_explicit: true })
    try {
      const next = await apiFetch<SubscriptionState>(`/api/workspaces/${workspaceId}/subscription`, {
        method: "PATCH",
        body: JSON.stringify({ level }),
      })
      onChange(next)
    } catch (err) {
      onChange(previous)
      if (!(err instanceof ApiError)) throw err
    }
  }

  async function clearOverride() {
    const previous = state
    onChange({ wants_all: false, is_explicit: false })
    try {
      await apiFetch(`/api/workspaces/${workspaceId}/subscription`, { method: "DELETE" })
      const next = await apiFetch<SubscriptionState>(`/api/workspaces/${workspaceId}/subscription`)
      onChange(next)
    } catch (err) {
      onChange(previous)
      if (!(err instanceof ApiError)) throw err
    }
  }

  return (
    <div className="space-y-1">
      {subtitle && <div className="px-2 pt-0.5 pb-2 text-xs opacity-50">{subtitle}</div>}
      <ul>
        <Option label={fallback.label} hint={fallback.hint} checked={isDefault} onClick={clearOverride} />
        <Option
          label={relevant.label}
          hint={relevant.hint}
          checked={isOnlyRelevant}
          onClick={() => setLevel("relevant_only")}
        />
        <Option label={all.label} hint={all.hint} checked={isFollowing} onClick={() => setLevel("all")} />
      </ul>
      {manageUrl && (
        <a href={manageUrl} className="block px-2 pt-2 text-xs opacity-50 hover:opacity-75 border-t border-base-400">
          Manage notification settings
        </a>
      )}
    </div>
  )
}

interface OptionProps {
  label: string
  hint: string
  checked: boolean
  onClick: () => void
}

function Option({ label, hint, checked, onClick }: OptionProps) {
  return (
    <li>
      <button
        type="button"
        data-dropdown-item
        onClick={onClick}
        className="w-full text-left flex items-center gap-2 px-2 py-1.5 hover:bg-base-200 rounded-md cursor-pointer"
      >
        <span
          className={`material-symbols-outlined text-xl shrink-0 w-5 text-center ${checked ? "text-primary" : "opacity-30"}`}
        >
          {checked ? "radio_button_checked" : "radio_button_unchecked"}
        </span>
        <div className="flex flex-col text-left">
          <span className="text-sm font-semibold">{label}</span>
          <span className="text-pretty text-xs opacity-50">{hint}</span>
        </div>
      </button>
    </li>
  )
}
