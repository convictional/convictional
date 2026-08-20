import {
  FloatingFocusManager,
  FloatingPortal,
  type Middleware,
  type Placement,
  autoUpdate,
  flip,
  offset,
  shift,
  useClick,
  useDismiss,
  useFloating,
  useInteractions,
  useListNavigation,
  useRole,
} from "@floating-ui/react"
import { type ReactElement, type ReactNode, cloneElement, isValidElement, useCallback, useRef, useState } from "react"

import { FLOATING_PORTAL_ROOT_ID } from "./floatingPortalRoot"
import { useCloseOnGroupLeave } from "./hooks/useCloseOnGroupLeave"

interface ListNavigationApi {
  // Pass to each focusable item: `<button ref={list.setItemRef(idx)} {...list.getItemProps()}>`.
  setItemRef: (index: number) => (node: HTMLElement | null) => void
  activeIndex: number | null
  getItemProps: (props?: React.HTMLAttributes<HTMLElement>) => Record<string, unknown>
}

export interface DropdownChildArgs {
  close: () => void
  // Populated only when the `listNavigation` prop is true.
  list: ListNavigationApi | null
}

export interface DropdownTriggerProps {
  ref: (node: Element | null) => void
  // Spread of @floating-ui/react's getReferenceProps().
  [key: string]: unknown
}

interface DropdownProps {
  // The trigger gets `aria-expanded`, `aria-haspopup="menu"`, an `onClick`
  // handler, and a `ref` injected via cloneElement, so callers pass any
  // <button> / <a> and don't need to wire the floating-ui props themselves.
  // For triggers that need their own wrapping (e.g. a Tooltip around the
  // button) pass a render function instead.
  trigger: ReactElement | ((props: DropdownTriggerProps) => ReactNode)
  children: ReactNode | ((args: DropdownChildArgs) => ReactNode)
  placement?: Placement
  className?: string
  ariaLabel?: string
  open?: boolean
  onOpenChange?: (open: boolean) => void
  // Initial focus target inside the panel on open. Defaults to 0 (first
  // focusable child). Pass -1 to disable initial focus when the menu has
  // no semantic "first" option to preselect.
  initialFocus?: number
  // "fixed" anchors the floating element to the viewport. Use when an
  // ancestor's transform or focus-driven scroll makes "absolute" positioning
  // jump the page (see ReactionMenu).
  strategy?: "absolute" | "fixed"
  // Keep the dropdown open while the cursor is over the trigger's `.group`
  // ancestor or the floating panel. Used for chat hover groups; see
  // useCloseOnGroupLeave for the rationale.
  closeOnGroupLeave?: boolean
  // When true, attach @floating-ui/react's useListNavigation. Children must
  // wire `list.setItemRef(idx)` and `list.getItemProps()` for each item.
  listNavigation?: boolean
  // Override the default `[offset(4), flip(), shift({ padding: 8 })]`
  // middleware. Use when a panel needs custom flip fallbacks or shift
  // padding (e.g. chat dropdowns that must stay clear of the composer).
  middleware?: Middleware[]
  // Whether focus returns to the trigger when the panel closes. Defaults to true
  // (keyboard users keep their place). Pass false for menus where returning
  // focus is undesirable — e.g. a mouse-driven reaction picker, where WebKit
  // would paint a focus ring on the trigger after a click.
  returnFocus?: boolean
}

const DEFAULT_MIDDLEWARE: Middleware[] = [offset(4), flip(), shift({ padding: 8 })]

// Generalized dropdown primitive. Wraps @floating-ui/react with the patterns
// every menu in this app needs: outside-click + Escape close, focus trap
// inside the panel, focus return to trigger on close, role="menu" on the
// panel. Visual parity with the Jinja `dropdown-card` class is automatic
// because we apply that class to the panel container.
export function Dropdown({
  trigger,
  children,
  placement = "bottom-end",
  className,
  ariaLabel,
  open: controlledOpen,
  onOpenChange,
  initialFocus,
  strategy = "absolute",
  closeOnGroupLeave = false,
  listNavigation = false,
  middleware,
  returnFocus = true,
}: DropdownProps) {
  const [uncontrolledOpen, setUncontrolledOpen] = useState(false)
  const isControlled = controlledOpen !== undefined
  const isOpen = isControlled ? controlledOpen : uncontrolledOpen
  const setIsOpen = useCallback(
    (next: boolean) => {
      if (!isControlled) setUncontrolledOpen(next)
      onOpenChange?.(next)
    },
    [isControlled, onOpenChange]
  )
  const close = useCallback(() => setIsOpen(false), [setIsOpen])

  const { refs, floatingStyles, context } = useFloating({
    open: isOpen,
    onOpenChange: setIsOpen,
    placement,
    strategy,
    middleware: middleware ?? DEFAULT_MIDDLEWARE,
    whileElementsMounted: autoUpdate,
  })
  const { setReference, setFloating } = refs

  const listRef = useRef<Array<HTMLElement | null>>([])
  const [activeIndex, setActiveIndex] = useState<number | null>(null)

  const click = useClick(context)
  const dismiss = useDismiss(context, { escapeKey: true, outsidePress: true })
  const role = useRole(context, { role: "menu" })
  // Calling useListNavigation unconditionally keeps hook order stable across
  // renders. The hook is cheap when the dropdown is closed.
  const navigation = useListNavigation(context, {
    listRef,
    activeIndex,
    onNavigate: setActiveIndex,
    enabled: listNavigation,
    loop: true,
    focusItemOnOpen: "auto",
  })

  const { getReferenceProps, getFloatingProps, getItemProps } = useInteractions([click, dismiss, role, navigation])

  useCloseOnGroupLeave(closeOnGroupLeave && isOpen, close, refs.reference, refs.floating)

  const setItemRef = useCallback(
    (index: number) => (node: HTMLElement | null) => {
      listRef.current[index] = node
    },
    []
  )

  const list: ListNavigationApi | null = listNavigation ? { setItemRef, activeIndex, getItemProps } : null

  const triggerNode =
    typeof trigger === "function"
      ? trigger({ ref: setReference, ...getReferenceProps() })
      : isValidElement(trigger)
        ? // Pass the trigger's own props to getReferenceProps so floating-ui's
          // handlers compose with (rather than overwrite) any existing
          // onClick / onMouseDown / etc. set on the trigger element.
          cloneElement(trigger, {
            ref: setReference,
            ...getReferenceProps(trigger.props as Record<string, unknown>),
          } as Record<string, unknown>)
        : trigger

  const panelChildren = typeof children === "function" ? children({ close, list }) : children

  return (
    <>
      {triggerNode}
      {isOpen && (
        <FloatingPortal id={FLOATING_PORTAL_ROOT_ID}>
          <FloatingFocusManager context={context} modal={false} initialFocus={initialFocus} returnFocus={returnFocus}>
            <div
              ref={setFloating}
              style={floatingStyles}
              {...getFloatingProps()}
              aria-label={ariaLabel}
              className={className ?? "dropdown-card z-50"}
            >
              {panelChildren}
            </div>
          </FloatingFocusManager>
        </FloatingPortal>
      )}
    </>
  )
}
