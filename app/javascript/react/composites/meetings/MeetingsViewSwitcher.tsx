import { Dropdown } from "~/react/ui/Dropdown"

type View = "collections" | "upcoming"

interface MeetingsViewSwitcherProps {
  current: View
}

// The view switcher that sits at the top-left of the meetings list pages. Three
// destinations: Upcoming (/meetings/upcoming), Most Recent (/meetings) and
// Collections (/meetings_collections) — the latter two are distinct routes, so
// "Collections" links to the collections index rather than the most-recent list.
// Plain <a href> links because each option is a different page render, not
// in-island state.
export function MeetingsViewSwitcher({ current }: MeetingsViewSwitcherProps) {
  return (
    <Dropdown
      placement="bottom-start"
      className="dropdown-card p-2 z-50"
      trigger={
        <button type="button" className="btn border border-neutral font-normal text-base-600 flex items-center gap-1">
          <span className="material-symbols-outlined text-base">
            {current === "upcoming" ? "calendar_today" : "folder"}
          </span>
          {current === "upcoming" ? "Upcoming" : "Collections"}
        </button>
      }
    >
      <ul>
        <li>
          <a className="dropdown-item text-xs" href="/meetings/upcoming">
            Upcoming
          </a>
        </li>
        <li>
          <a className="dropdown-item text-xs" href="/meetings">
            Most Recent
          </a>
        </li>
        <li>
          <a className="dropdown-item text-xs" href="/meetings_collections">
            Collections
          </a>
        </li>
      </ul>
    </Dropdown>
  )
}
