import { StickyHeader } from "~/react/ui/StickyHeader"

interface GroupsHeaderProps {
  canManage: boolean
  showCreate: boolean
  onCreate: () => void
}

export function GroupsHeader({ canManage, showCreate, onCreate }: GroupsHeaderProps) {
  return (
    <StickyHeader>
      <div className="flex items-center justify-between gap-2 p-2">
        <h1 className="text-lg font-accent px-1">Groups</h1>
        {canManage && showCreate && (
          <button type="button" className="btn btn-primary" onClick={onCreate}>
            <span className="material-symbols-outlined text-lg">add</span>
            Create group
          </button>
        )}
      </div>
    </StickyHeader>
  )
}
