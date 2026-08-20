export function MailboxViewLoading() {
  return (
    <div className="px-1 py-1">
      <div className="flex justify-center">
        <div className="flex items-center gap-1">
          <span className="relative flex size-2 mr-0.5">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-primary opacity-85" />
            <span className="relative inline-flex size-2 rounded-full bg-primary" />
          </span>
          <span className="text-sm">Organizing your inbox...</span>
        </div>
      </div>
    </div>
  )
}
