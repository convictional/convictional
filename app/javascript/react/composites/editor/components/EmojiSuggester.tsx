import type { EmojiState } from "../features/useEmojis"

export function EmojiSuggester({ suggesterState, dropdownRef, actions }: EmojiState) {
  if (!suggesterState.shouldShow) return null

  return (
    <div
      ref={dropdownRef}
      className="dropdown-card py-2 shadow-sm max-h-56 overflow-y-auto z-50 absolute"
      onMouseDown={e => {
        e.stopPropagation()
        e.preventDefault()
      }}
    >
      {suggesterState.results.length > 0 ? (
        <div className="px-2">
          <ul className="grid">
            {suggesterState.results.map((emoji, i) => (
              <li key={emoji.name}>
                <button
                  data-suggester-item
                  className={`dropdown-item p-1 grid grid-cols-[auto_1fr] gap-2 items-center w-full text-left ${
                    suggesterState.highlightedIndex === i ? "bg-base-400" : ""
                  }`}
                  onClick={e => {
                    e.preventDefault()
                    e.stopPropagation()
                    actions.select(emoji)
                  }}
                  onMouseOver={() => actions.setHighlightedIndex(i)}
                >
                  <span>{emoji.emoji}</span>
                  <span className="text-sm opacity-75">:{emoji.name}:</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <div className="text-center px-2 text-sm text-base-content/70">No emojis found</div>
      )}
    </div>
  )
}
