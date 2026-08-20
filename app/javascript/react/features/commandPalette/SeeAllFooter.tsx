import { useEffect, useRef } from "react"

interface SeeAllFooterProps {
  query: string
  isSelected: boolean
  onHover: () => void
  onActivate: () => void
}

export function SeeAllFooter({ query, isSelected, onHover, onActivate }: SeeAllFooterProps) {
  const ref = useRef<HTMLAnchorElement>(null)
  useEffect(() => {
    if (isSelected) ref.current?.scrollIntoView({ block: "nearest" })
  }, [isSelected])

  return (
    <div className="border-t border-base-400 p-2">
      <a
        ref={ref}
        href={`/search?q=${encodeURIComponent(query)}`}
        onClick={onActivate}
        onMouseOver={onHover}
        data-test-id="palette-see-all-results"
        {...(isSelected ? { "data-palette-active": "true" } : {})}
        className={`rounded-lg py-2 px-4 grid grid-cols-[auto_1fr_auto] gap-2 items-center cursor-pointer transition hover:bg-base-200 ${
          isSelected ? "bg-base-200" : ""
        }`}
      >
        <div className="pr-2">
          <span className="material-symbols-outlined text-lg text-base-500">manage_search</span>
        </div>
        <div>
          <p className="text-sm">See all results for &ldquo;{query}&rdquo;</p>
        </div>
        <div className="text-base-500 flex items-center">
          <span className="material-symbols-outlined text-base">arrow_forward</span>
        </div>
      </a>
    </div>
  )
}
