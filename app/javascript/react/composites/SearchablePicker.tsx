import type { Placement } from "@floating-ui/react"
import { cloneElement, useCallback, useMemo, useState, type ReactElement, type ReactNode } from "react"

import { useIsMobile } from "~/react/shared/hooks/useIsMobile"
import { BottomSheet } from "~/react/ui/BottomSheet"
import { Dropdown } from "~/react/ui/Dropdown"

interface SearchablePickerProps<T> {
  trigger: ReactElement
  title?: ReactNode
  items: T[]
  getKey: (item: T) => string
  getSearchText: (item: T) => string
  renderItem: (item: T, close: () => void) => ReactNode
  // renderHeader/renderFooter/listLabel render outside the list's `p-2` wrapper —
  // callers own the horizontal padding of these slots (see consumers' `px-2` wrap).
  renderHeader?: (close: () => void) => ReactNode
  renderFooter?: (close: () => void) => ReactNode
  listLabel?: ReactNode
  searchPlaceholder: string
  emptyText?: string
  loading?: boolean
  ariaLabel: string
  placement?: Placement
  panelClassName?: string
}

export function SearchablePicker<T>({
  trigger,
  title,
  items,
  getKey,
  getSearchText,
  renderItem,
  renderHeader,
  renderFooter,
  listLabel,
  searchPlaceholder,
  emptyText = "No results match your search",
  loading = false,
  ariaLabel,
  placement = "bottom-end",
  panelClassName = "dropdown-card w-56 z-50",
}: SearchablePickerProps<T>): ReactNode {
  const isMobile = useIsMobile()
  const [query, setQuery] = useState("")
  const [open, setOpen] = useState(false)

  const focusSearch = useCallback((node: HTMLInputElement | null) => node?.focus({ preventScroll: true }), [])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return items
    return items.filter(item => getSearchText(item).toLowerCase().includes(q))
  }, [items, query, getSearchText])

  const renderPanel = (close: () => void) => (
    <div>
      {(items.length > 0 || loading) && (
        <div className="p-2 pb-0">
          <input
            type="text"
            placeholder={searchPlaceholder}
            autoComplete="off"
            className="input input-sm input-bordered !outline-none bg-base-50 w-full"
            value={query}
            onChange={e => setQuery(e.target.value)}
            // Focus-on-open is desktop-only: the bottom sheet omits the ref so
            // opening the picker doesn't pop the mobile keyboard.
            ref={isMobile ? undefined : focusSearch}
          />
        </div>
      )}
      {renderHeader?.(close)}
      <div className="p-2 pt-0">
        {listLabel}
        <ul className="max-h-60 overflow-y-auto grid gap-1">
          {loading ? (
            <li className="text-center py-2 text-sm text-base-500">Loading…</li>
          ) : items.length > 0 && filtered.length === 0 ? (
            <li className="text-center py-2 text-sm text-base-500">{emptyText}</li>
          ) : (
            filtered.map(item => <li key={getKey(item)}>{renderItem(item, close)}</li>)
          )}
        </ul>
      </div>
      {renderFooter?.(close)}
    </div>
  )

  if (isMobile) {
    const closeSheet = () => {
      setOpen(false)
      setQuery("")
    }
    return (
      <>
        {/* Mobile opens on trigger click. Unlike ui/Dropdown (which composes onClick via
            getReferenceProps), this REPLACES any onClick on the trigger — pass a trigger
            without its own onClick. */}
        {cloneElement(trigger, { onClick: () => setOpen(true) } as Record<string, unknown>)}
        {open && (
          <BottomSheet title={title} ariaLabel={ariaLabel} onClose={closeSheet}>
            <div className="overflow-y-auto pb-4">{renderPanel(closeSheet)}</div>
          </BottomSheet>
        )}
      </>
    )
  }

  return (
    <Dropdown
      trigger={trigger}
      placement={placement}
      className={panelClassName}
      ariaLabel={ariaLabel}
      initialFocus={-1}
      onOpenChange={isOpen => !isOpen && setQuery("")}
    >
      {({ close }) => renderPanel(close)}
    </Dropdown>
  )
}
