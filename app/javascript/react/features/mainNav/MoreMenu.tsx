import { type RefObject, useRef, useState } from "react"

import { delegateLogoutToNativeShell } from "~/nativeShell"

import { useHotkeyInstall } from "~/react/shared/hooks/useHotkeyInstall"
import { useTheme } from "~/react/shared/hooks/useTheme"
import { NavLink } from "~/react/shared/NavLink"
import { feedbackDialogStore } from "~/react/shared/stores/feedbackDialog"
import { Dropdown } from "~/react/ui/Dropdown"
import { getCSRFToken } from "~/shared/csrf"

interface MoreMenuProps {
  isAdmin: boolean
  isSuperuser: boolean
  organizationName: string | null
}

export function MoreMenu({ isAdmin, isSuperuser, organizationName }: MoreMenuProps) {
  // The Tooltip wrapper would wrap the trigger in a <span> and intercept the
  // ref needed by floating-ui's positioning, so the trigger lives bare. The
  // aria-label "More options" carries the screen-reader copy.
  return (
    <Dropdown
      placement="bottom-end"
      ariaLabel="More options menu"
      trigger={
        <button
          type="button"
          className="cursor-pointer hover:bg-base-200 rounded-lg flex items-center justify-center px-1.5 py-1"
          aria-label="More options"
        >
          <span className="material-symbols-outlined text-lg">more_vert</span>
        </button>
      }
    >
      {({ close }) => (
        <MoreMenuContent
          isAdmin={isAdmin}
          isSuperuser={isSuperuser}
          organizationName={organizationName}
          onItemClick={close}
        />
      )}
    </Dropdown>
  )
}

interface MoreMenuContentProps extends MoreMenuProps {
  onItemClick: () => void
}

function MoreMenuContent({ isAdmin, isSuperuser, organizationName, onItemClick }: MoreMenuContentProps) {
  const ref = useRef<HTMLDivElement>(null)
  // Install any data-hotkey elements when the menu opens (and uninstall on close).
  useHotkeyInstall(ref as RefObject<HTMLElement | null>)

  return (
    <div ref={ref} className="grid gap-2">
      <div className="p-2 bg-base-200 border-b border-neutral rounded-t-xl">
        {organizationName && <p className="text-xs text-base-600/70 truncate ml-1">{organizationName}</p>}
        <ul className="bg-base-200 pt-2">
          {isAdmin && (
            <>
              <li>
                <NavLink href="/organization/edit" className="dropdown-item py-1" onClick={onItemClick}>
                  Organization Settings
                </NavLink>
              </li>
              <li>
                <NavLink href="/organization/users" className="dropdown-item py-1" onClick={onItemClick}>
                  Team Members
                </NavLink>
              </li>
            </>
          )}
          <li>
            <NavLink href="/groups" className="dropdown-item py-1" onClick={onItemClick}>
              Groups
            </NavLink>
          </li>
        </ul>
      </div>
      {isSuperuser && (
        <ul className="border-b border-neutral p-2 pt-0">
          <li className="text-xs pb-2 ml-1 text-base-600/70">Superuser</li>
          <li>
            <NavLink href="/background_jobs/" className="dropdown-item py-1" onClick={onItemClick}>
              Background jobs
            </NavLink>
          </li>
        </ul>
      )}
      <ThemePicker />
      <ul className="px-2 pt-0">
        <li className="text-xs pb-2 ml-1 text-base-600/70">Help</li>
        <li>
          <a
            href="https://guides.convictional.com"
            target="_blank"
            rel="noopener noreferrer"
            className="dropdown-item py-1"
            onClick={onItemClick}
          >
            Guides
          </a>
        </li>
        <li>
          <FeedbackLink onItemClick={onItemClick} />
        </li>
      </ul>
      <ul className="p-2 border-t border-neutral">
        <li className="text-xs pb-2 ml-1 text-base-600/70">My Account</li>
        <li>
          <NavLink
            href="/scheduled_research"
            className="dropdown-item flex items-center gap-2 py-1 px-1"
            onClick={onItemClick}
          >
            <span className="material-symbols-outlined text-base text-base-500">event_repeat</span>
            Scheduled research
          </NavLink>
        </li>
        <li>
          <NavLink
            href="/notifications"
            className="dropdown-item flex items-center gap-2 py-1 px-1"
            onClick={onItemClick}
          >
            <span className="material-symbols-outlined text-base text-base-500">notifications</span>
            Notifications
          </NavLink>
        </li>
        <li>
          <NavLink
            href="/profile/edit"
            className="dropdown-item flex items-center gap-2 py-1 px-1"
            onClick={onItemClick}
          >
            <span className="material-symbols-outlined text-base text-base-500">settings</span>
            Settings
          </NavLink>
        </li>
        <li>
          <LogoutForm />
        </li>
      </ul>
    </div>
  )
}

function ThemePicker() {
  const { setting, setTheme } = useTheme()
  const options: Array<{ value: "system" | "light" | "dark"; label: string }> = [
    { value: "system", label: "System" },
    { value: "light", label: "Light" },
    { value: "dark", label: "Dark" },
  ]
  return (
    <div className="border-b border-neutral p-2 pt-0">
      <p className="text-xs pb-2 ml-1 text-base-600/70">Theme</p>
      <div className="flex items-center">
        {options.map(opt => (
          <button
            key={opt.value}
            type="button"
            className={`dropdown-item py-1 ${setting === opt.value ? "text-primary" : ""}`}
            onClick={() => setTheme(opt.value)}
          >
            {opt.label}
          </button>
        ))}
      </div>
    </div>
  )
}

function FeedbackLink({ onItemClick }: { onItemClick: () => void }) {
  return (
    <button
      type="button"
      className="dropdown-item py-1"
      onClick={() => {
        onItemClick()
        feedbackDialogStore.getState().open()
      }}
    >
      Share feedback
    </button>
  )
}

function LogoutForm() {
  // The CSRF token comes from a server-rendered <meta> tag and is stable across
  // the page lifecycle; reading it inside `useState`'s lazy initializer runs
  // exactly once at mount and avoids the react-hooks/set-state-in-effect rule.
  const [token] = useState(() => getCSRFToken() ?? "")

  return (
    <form action="/logout" method="post" className="flex" onSubmitCapture={delegateLogoutToNativeShell}>
      <input type="hidden" name="csrf_token" value={token} />
      <button type="submit" className="w-full">
        <span className="w-full text-left dropdown-item flex items-center gap-2 py-1 px-1">
          <span className="material-symbols-outlined text-base text-base-500">logout</span>
          Logout
        </span>
      </button>
    </form>
  )
}
