interface ErrorStateProps {
  message?: string
}

export function ErrorState({ message = "Please try refreshing the page." }: ErrorStateProps) {
  return (
    <div className="px-4 py-12 text-center">
      <p className="text-sm font-semibold text-base-content mb-1">Something went wrong</p>
      <p className="text-sm text-base-content/60">{message}</p>
    </div>
  )
}
