import { useEffect, useState } from "react"

import { Tooltip } from "~/react/ui/Tooltip"

import type { MeetingDetail, TabKey } from "../types"

import { AgendaEditor } from "./AgendaEditor"
import { SummaryTab } from "./SummaryTab"

const TAB_KEYS: TabKey[] = ["summary", "agenda"]

function readHashTab(): TabKey | null {
  const hash = window.location.hash.replace(/^#/, "") as TabKey
  return TAB_KEYS.includes(hash) ? hash : null
}

interface TabsProps {
  meeting: MeetingDetail
  onLocalUpdate: <K extends keyof MeetingDetail>(field: K, value: MeetingDetail[K]) => void
  onServerUpdate: (meeting: MeetingDetail) => void
}

export function Tabs({ meeting, onLocalUpdate, onServerUpdate }: TabsProps) {
  const summaryAvailable = !!meeting.summary
  // Summary first when present, else agenda.
  const defaultTab: TabKey = summaryAvailable ? "summary" : "agenda"
  const [active, setActive] = useState<TabKey>(() => {
    const hash = readHashTab()
    if (hash === "summary" && !summaryAvailable) return defaultTab
    return hash ?? defaultTab
  })

  useEffect(() => {
    const onHashChange = () => {
      const tab = readHashTab()
      if (!tab) return
      if (tab === "summary" && !summaryAvailable) return
      setActive(tab)
    }
    window.addEventListener("hashchange", onHashChange)
    return () => window.removeEventListener("hashchange", onHashChange)
  }, [summaryAvailable])

  function activate(tab: TabKey) {
    if (tab === "summary" && !summaryAvailable) return
    setActive(tab)
    // Use replaceState so back-button doesn't bounce between tabs — feels
    // closer to "tab is part of the page" than "tab is its own history entry".
    history.replaceState(history.state, "", `#${tab}`)
  }

  return (
    <div>
      <div
        role="tablist"
        className="inline-flex items-center gap-0.5 rounded-full border border-base-300 bg-base-200/40 p-0.5"
      >
        <TabHandle label="Agenda" active={active === "agenda"} onClick={() => activate("agenda")} />
        {summaryAvailable ? (
          <TabHandle label="Summary" active={active === "summary"} onClick={() => activate("summary")} />
        ) : (
          <DisabledSummaryTab />
        )}
      </div>
      <div className="mt-3 rounded-2xl border border-base-300 bg-base-50 p-4 group min-h-32" role="tabpanel">
        {active === "summary" && (
          <SummaryTab meeting={meeting} onLocalUpdate={onLocalUpdate} onServerUpdate={onServerUpdate} />
        )}
        {active === "agenda" && (
          <AgendaEditor meetingId={meeting.id} initialContent={meeting.agenda} workspaceId={meeting.workspace_id} />
        )}
      </div>
    </div>
  )
}

interface TabHandleProps {
  label: string
  active: boolean
  onClick: () => void
}

// A segmented pill control tab (see ScheduleFormFields for the same pattern):
// the active tab lifts with a base-100 fill + shadow inside the base-200 track.
export const TAB_HANDLE_CLASS = "px-3 py-1 rounded-full text-sm transition-colors cursor-pointer"

function TabHandle({ label, active, onClick }: TabHandleProps) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={`${TAB_HANDLE_CLASS} ${
        active ? "bg-base-100 text-base-content font-medium shadow-xs" : "text-base-content/50 hover:text-base-content"
      }`}
    >
      {label}
    </button>
  )
}

function DisabledSummaryTab() {
  return (
    <Tooltip content="The meeting summary will be available after the meeting ends">
      <span
        role="tab"
        aria-disabled="true"
        className={`${TAB_HANDLE_CLASS} text-base-content/30 flex items-center gap-1`}
      >
        Summary <span className="material-symbols-outlined text-base">info</span>
      </span>
    </Tooltip>
  )
}
