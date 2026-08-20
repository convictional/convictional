interface CommentButtonProps {
  goalId: string
  commentCount: number
  isOpen: boolean
  onToggle: (goalId: string | null) => void
}

export function CommentButton({ goalId, commentCount, isOpen, onToggle }: CommentButtonProps) {
  if (isOpen) {
    return (
      <button
        type="button"
        className="btn btn-sm btn-square join-item btn-primary"
        onClick={e => {
          e.stopPropagation()
          onToggle(null)
        }}
      >
        <span className="material-symbols-outlined text-base">chat_bubble</span>
      </button>
    )
  }

  if (commentCount > 0) {
    return (
      <>
        <button
          type="button"
          className="btn btn-sm btn-square join-item relative hidden group-hover:inline-flex"
          onClick={e => {
            e.stopPropagation()
            onToggle(goalId)
          }}
        >
          <span className="material-symbols-outlined text-base">chat_bubble</span>
          <span className="w-2 h-2 rounded-full bg-primary absolute -top-1 -right-1" />
        </button>
        <button
          type="button"
          aria-hidden="true"
          tabIndex={-1}
          className="btn btn-sm btn-square btn-ghost relative text-primary inline-flex group-hover:hidden"
          onClick={e => {
            e.stopPropagation()
            onToggle(goalId)
          }}
        >
          <span className="material-symbols-outlined text-base">chat_bubble</span>
          <span className="w-2 h-2 rounded-full bg-primary absolute -top-1 -right-1" />
        </button>
      </>
    )
  }

  return (
    <button
      type="button"
      className="btn btn-sm btn-square join-item opacity-0 group-hover:opacity-100 transition-opacity"
      onClick={e => {
        e.stopPropagation()
        onToggle(goalId)
      }}
    >
      <span className="material-symbols-outlined text-base">chat_bubble</span>
    </button>
  )
}
