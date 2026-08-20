import { useState } from "react"

import { delegateLogoutToNativeShell } from "~/nativeShell"

import { useActiveRoute } from "~/react/shared/hooks/useActiveRoute"
import { useTheme } from "~/react/shared/hooks/useTheme"
import { NavLink } from "~/react/shared/NavLink"
import { feedbackDialogStore } from "~/react/shared/stores/feedbackDialog"
import { getCSRFToken } from "~/shared/csrf"
import { MOBILE_MORE_NAV_ITEMS, type NavItem } from "./items"

// The demoted bottom-tab destinations plus Meetings, rendered from one list so
// their row styling can't drift apart.
const PRIMARY_LINKS: Pick<NavItem, "href" | "icon" | "label" | "match" | "clientRouted">[] = [
  ...MOBILE_MORE_NAV_ITEMS,
  {
    href: "/meetings/upcoming",
    icon: "calendar_today",
    label: "Meetings",
    match: pathname => pathname.startsWith("/meetings"),
  },
]

interface MobileMoreMenuProps {
  isAdmin: boolean
  isSuperuser: boolean
  organizationName: string | null
  /** Called when the user picks an item — parent should dismiss the sheet. */
  onItemClick: () => void
}

export function MobileMoreMenu({ isAdmin, isSuperuser, organizationName, onItemClick }: MobileMoreMenuProps) {
  const pathname = useActiveRoute()

  return (
    <div className="px-4 pb-4 space-y-3 max-h-[60vh] overflow-y-auto">
      <div className="space-y-1">
        {PRIMARY_LINKS.map(item => {
          const isActive = item.match(pathname)
          return (
            <NavLink
              key={item.href}
              href={item.href}
              clientRouted={item.clientRouted}
              onClick={onItemClick}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-xl transition-colors ${
                isActive ? "bg-primary/10 text-primary font-medium" : "text-base-content active:bg-base-300"
              }`}
            >
              <span
                className="material-symbols-outlined text-xl"
                style={{ fontVariationSettings: isActive ? "'FILL' 1" : "'FILL' 0" }}
              >
                {item.icon}
              </span>
              {item.label}
            </NavLink>
          )
        })}
      </div>

      <div className="h-px bg-base-300" />

      {/* Organization */}
      <div className="space-y-1">
        {organizationName && <p className="text-xs text-base-content/50 px-3 pb-1">{organizationName}</p>}
        {isAdmin && (
          <>
            <NavLink href="/organization/edit" onClick={onItemClick} className="more-menu-item">
              <span className="material-symbols-outlined text-xl text-base-content/60">settings</span>
              Organization Settings
            </NavLink>
            <NavLink href="/organization/users" onClick={onItemClick} className="more-menu-item">
              <span className="material-symbols-outlined text-xl text-base-content/60">group</span>
              Team Members
            </NavLink>
          </>
        )}
        <NavLink href="/groups" onClick={onItemClick} className="more-menu-item">
          <span className="material-symbols-outlined text-xl text-base-content/60">workspaces</span>
          Groups
        </NavLink>
      </div>
      <div className="h-px bg-base-300" />

      {/* Superuser */}
      {isSuperuser && (
        <>
          <div className="space-y-1">
            <p className="text-xs text-base-content/50 px-3 pb-1">Superuser</p>
            <NavLink href="/background_jobs/" onClick={onItemClick} className="more-menu-item">
              <span className="material-symbols-outlined text-xl text-base-content/60">pending_actions</span>
              Background jobs
            </NavLink>
          </div>
          <div className="h-px bg-base-300" />
        </>
      )}

      {/* Theme */}
      <MobileThemePicker />

      <div className="h-px bg-base-300" />

      {/* Help */}
      <div className="space-y-1">
        <a
          href="https://guides.convictional.com"
          target="_blank"
          rel="noopener noreferrer"
          onClick={onItemClick}
          className="more-menu-item"
        >
          <span className="material-symbols-outlined text-xl text-base-content/60">menu_book</span>
          Guides
        </a>
        <MobileFeedbackLink onClose={onItemClick} />
      </div>

      <div className="h-px bg-base-300" />

      {/* Account */}
      <div className="space-y-1">
        <NavLink href="/scheduled_research" onClick={onItemClick} className="more-menu-item">
          <span className="material-symbols-outlined text-xl text-base-content/60">event_repeat</span>
          Scheduled research
        </NavLink>
        <NavLink href="/notifications" onClick={onItemClick} className="more-menu-item">
          <span className="material-symbols-outlined text-xl text-base-content/60">notifications</span>
          Notifications
        </NavLink>
        <NavLink href="/profile/edit" onClick={onItemClick} className="more-menu-item">
          <span className="material-symbols-outlined text-xl text-base-content/60">person</span>
          Settings
        </NavLink>
        <MobileLogoutForm />
      </div>
    </div>
  )
}

function MobileThemePicker() {
  const { setting, setTheme } = useTheme()
  const options: Array<{ value: "system" | "light" | "dark"; label: string; icon: string }> = [
    { value: "system", label: "System", icon: "devices" },
    { value: "light", label: "Light", icon: "light_mode" },
    { value: "dark", label: "Dark", icon: "dark_mode" },
  ]
  return (
    <div className="space-y-1">
      <p className="text-xs text-base-content/50 px-3 pb-1">Theme</p>
      <div className="flex gap-1 px-1">
        {options.map(opt => (
          <button
            key={opt.value}
            type="button"
            onClick={() => setTheme(opt.value)}
            className={`flex-1 flex items-center justify-center gap-1.5 px-3 py-2 rounded-xl text-sm cursor-pointer transition-colors ${
              setting === opt.value ? "bg-primary/10 text-primary font-medium" : "text-base-content active:bg-base-300"
            }`}
          >
            <span className="material-symbols-outlined text-base">{opt.icon}</span>
            {opt.label}
          </button>
        ))}
      </div>
    </div>
  )
}

function MobileFeedbackLink({ onClose }: { onClose: () => void }) {
  return (
    <button
      type="button"
      onClick={() => {
        onClose()
        feedbackDialogStore.getState().open()
      }}
      className="more-menu-item"
    >
      <span className="material-symbols-outlined text-xl text-base-content/60">feedback</span>
      Share feedback
    </button>
  )
}

function MobileLogoutForm() {
  const [token] = useState(() => getCSRFToken() ?? "")

  return (
    <form action="/logout" method="post" onSubmitCapture={delegateLogoutToNativeShell}>
      <input type="hidden" name="csrf_token" value={token} />
      <button type="submit" className="w-full more-menu-item cursor-pointer">
        <span className="material-symbols-outlined text-xl text-base-content/60">logout</span>
        Logout
      </button>
    </form>
  )
}
