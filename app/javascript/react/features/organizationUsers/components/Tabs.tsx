export type ActiveTab = "active" | "deleted"

interface TabsProps {
  activeTab: ActiveTab
  onTabChange: (tab: ActiveTab) => void
}

// The Active/Deleted member tab row — a segmented pill control matching the
// meeting agenda/summary tabs and the scheduled-research frequency picker.
export function Tabs({ activeTab, onTabChange }: TabsProps) {
  const tabClass = (tab: ActiveTab) =>
    `px-3 py-1 rounded-full text-sm transition-colors cursor-pointer ${
      activeTab === tab
        ? "bg-base-100 text-base-content font-medium shadow-xs"
        : "text-base-content/50 hover:text-base-content"
    }`

  return (
    <div
      role="tablist"
      className="inline-flex items-center gap-0.5 rounded-full border border-base-300 bg-base-200/40 p-0.5"
    >
      <button
        type="button"
        role="tab"
        aria-selected={activeTab === "active"}
        className={tabClass("active")}
        onClick={() => onTabChange("active")}
      >
        Active Members
      </button>
      <button
        type="button"
        role="tab"
        aria-selected={activeTab === "deleted"}
        className={tabClass("deleted")}
        onClick={() => onTabChange("deleted")}
      >
        Deleted Members
      </button>
    </div>
  )
}
