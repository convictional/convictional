import type { MentionState } from "../features/useMentions"

export function MentionSuggester({ suggesterState, dropdownRef, actions }: MentionState) {
  if (!suggesterState.shouldShow) return null

  // suggesterState.results is already sorted collaborators-first by sortResults
  const collaborators = suggesterState.results.filter(u => u.is_collaborator)
  const nonCollaborators = suggesterState.results.filter(u => !u.is_collaborator)

  return (
    <div
      ref={dropdownRef}
      className="dropdown-card py-2 shadow-sm max-h-56 overflow-y-auto z-50 absolute"
      onMouseDown={e => {
        e.stopPropagation()
        e.preventDefault()
      }}
    >
      {collaborators.length > 0 && (
        <div className="px-2 pb-0">
          {nonCollaborators.length > 0 && (
            <div className="text-xs font-semibold opacity-75 px-1 pb-1">Collaborators</div>
          )}
          <ul className="grid">
            {collaborators.map((user, i) => (
              <li key={user.id}>
                <button
                  data-suggester-item
                  className={`dropdown-item p-1 grid grid-cols-[auto_1fr] gap-1 items-center w-full text-left ${
                    suggesterState.highlightedIndex === i ? "bg-base-400" : ""
                  }`}
                  onClick={e => {
                    e.preventDefault()
                    e.stopPropagation()
                    actions.select(user)
                  }}
                  onMouseOver={() => actions.setHighlightedIndex(i)}
                >
                  <span>{user.display_name}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {collaborators.length > 0 && nonCollaborators.length > 0 && <div className="divider my-0" />}

      {nonCollaborators.length > 0 && (
        <div className="px-2 pt-0">
          {/* Only label this section when there's a Collaborators section to contrast it
              with. Org-wide contexts that don't expose collaborators (posts, goals, docs)
              flag nobody, so they render a flat, headerless list. */}
          {collaborators.length > 0 && (
            <div className="text-xs font-semibold opacity-75 px-1 pb-1">Invite to collaborate</div>
          )}
          <ul className="grid">
            {nonCollaborators.map((user, i) => {
              const idx = collaborators.length + i
              return (
                <li key={user.id}>
                  <button
                    data-suggester-item
                    className={`dropdown-item p-1 w-full text-left ${
                      suggesterState.highlightedIndex === idx ? "bg-base-400" : ""
                    }`}
                    onClick={e => {
                      e.preventDefault()
                      e.stopPropagation()
                      actions.select(user)
                    }}
                    onMouseOver={() => actions.setHighlightedIndex(idx)}
                  >
                    <span>{user.display_name}</span>
                  </button>
                </li>
              )
            })}
          </ul>
        </div>
      )}

      {suggesterState.results.length === 0 && (
        <div className="text-center px-2 text-sm text-base-content/70">No results</div>
      )}
    </div>
  )
}
