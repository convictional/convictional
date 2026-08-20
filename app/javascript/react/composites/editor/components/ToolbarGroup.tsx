import { type ReactNode, useEffect, useRef, useState } from "react"

import { FLOATING_PORTAL_ROOT_ID } from "~/react/ui/floatingPortalRoot"
import { Tooltip } from "~/react/ui/Tooltip"

interface ToolbarGroupProps {
  icon: string
  label: string
  active?: boolean
  className?: string
  children: ReactNode
}

export function ToolbarGroup({ icon, label, active, className, children }: ToolbarGroupProps) {
  const [open, setOpen] = useState(false)
  const wrapperRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return

    const handleClick = (e: MouseEvent) => {
      // Dropdowns like LinkDialog and the GIF picker render into a FloatingPortal
      // outside wrapperRef, so their clicks must count as inside the group.
      if (document.getElementById(FLOATING_PORTAL_ROOT_ID)?.contains(e.target as Node)) return
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false)
    }

    const timer = setTimeout(() => {
      window.addEventListener("click", handleClick)
      window.addEventListener("keydown", handleEscape)
    }, 0)
    return () => {
      clearTimeout(timer)
      window.removeEventListener("click", handleClick)
      window.removeEventListener("keydown", handleEscape)
    }
  }, [open])

  return (
    <div ref={wrapperRef} className="relative">
      <Tooltip content={label}>
        <button
          type="button"
          aria-label={label}
          className={`btn gap-0.5 px-1.5 ${active ? "text-info-content" : ""} ${className || ""}`}
          tabIndex={-1}
          onMouseDown={e => {
            e.preventDefault()
            setOpen(prev => !prev)
          }}
        >
          <span className="material-symbols-outlined !text-lg">{icon}</span>
          <span className="material-symbols-outlined !text-xs">keyboard_arrow_down</span>
        </button>
      </Tooltip>
      {open && (
        <div className="absolute left-0 top-full mt-1 floating-card !p-1 z-50 flex items-center gap-0.5">
          {children}
        </div>
      )}
    </div>
  )
}
