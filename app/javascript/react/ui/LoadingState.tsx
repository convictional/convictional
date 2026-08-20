interface LoadingStateProps {
  className?: string
}

export function LoadingState({ className = "py-12" }: LoadingStateProps) {
  return (
    <div className={`flex items-center justify-center ${className}`}>
      <span className="loading loading-spinner" />
    </div>
  )
}
