import { type ReactNode, useEffect, useRef } from "react"

interface ResultRowProps {
  href?: string
  onClick?: () => void
  onHover: () => void
  isSelected: boolean
  icon: ReactNode
  rowDetails: ReactNode
  testId?: string
}

// Shared row layout for lookup + recent results.
export function ResultRow({ href, onClick, onHover, isSelected, icon, rowDetails, testId }: ResultRowProps) {
  const ref = useRef<HTMLElement>(null)

  useEffect(() => {
    if (isSelected) ref.current?.scrollIntoView({ block: "nearest" })
  }, [isSelected])

  const className = `py-2.5 px-4 grid grid-cols-[auto_1fr] gap-2 items-start cursor-pointer transition bg-base-50 hover:bg-base-200 ${
    isSelected ? "bg-base-200" : ""
  }`

  const content = (
    <>
      {icon}
      <div className="min-w-0">{rowDetails}</div>
    </>
  )

  // `data-palette-active` lets CommandPalette's Enter handler click the
  // selected element without knowing its type (anchor vs button) — see
  // useArrowKeySelection + CommandPalette's handleEnter.
  const activeAttr = isSelected ? { "data-palette-active": "true" as const } : {}

  return (
    <li>
      {href ? (
        <a
          ref={ref as React.RefObject<HTMLAnchorElement>}
          href={href}
          onClick={onClick}
          onMouseOver={onHover}
          data-test-id={testId}
          className={className}
          {...activeAttr}
        >
          {content}
        </a>
      ) : (
        <button
          ref={ref as React.RefObject<HTMLButtonElement>}
          type="button"
          onClick={onClick}
          onMouseOver={onHover}
          data-test-id={testId}
          className={`${className} w-full text-left`}
          {...activeAttr}
        >
          {content}
        </button>
      )}
    </li>
  )
}
