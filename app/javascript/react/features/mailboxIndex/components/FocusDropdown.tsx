import { Link, useNavigate } from "@tanstack/react-router"
import { type ReactNode, useCallback, useEffect, useRef, useState } from "react"

import { confirm } from "~/react/composites/confirmationDialog/confirm"
import { apiFetch } from "~/react/shared/apiFetch"
import { useCurrentUser } from "~/react/shared/hooks/useCurrentUser"
import { useIsMobile } from "~/react/shared/hooks/useIsMobile"
import { fetchAllPages } from "~/react/shared/paginate"
import type { PaginatedResponse } from "~/react/shared/types"
import { BottomSheet } from "~/react/ui/BottomSheet"
import { Dialog } from "~/react/ui/Dialog"
import { Dropdown } from "~/react/ui/Dropdown"
import { showFlash } from "~/shared/flash"

import { useOnboardingFocusExplainer } from "../hooks/useOnboardingFocusExplainer"
import type { ActiveMailboxView, GoalOption, MailboxViewLayout, MailboxViewSummary } from "../types"
import { type FocusEntryEdit, FocusEntryForm, type FocusEntryKind } from "./FocusEntryForm"
import { GoalPicker } from "./GoalPicker"

// "Focus" promotes the AI-powered custom views/sorts out of the SortDropdown into a dedicated entry
// point with two sections — Custom Views (grouped) and Custom Sorts (ranked). Built-in templates
// render alongside the user's saved views/sorts; selecting any entry navigates (the existing routing
// + inbox_sort_preference cookie does the serving), so this component owns no generation glue.

// Built-in templates are server constants (app/models/collaboration/mailbox.py:MAILBOX_VIEW_TEMPLATES),
// not rows in `all_views`, so they're hardcoded here.
interface TemplateEntry {
  name: string
  title: string
  subtitle: string
  requiresGoals?: boolean
}

const VIEW_TEMPLATES: TemplateEntry[] = [
  { name: "urgent_important", title: "Urgent/Important", subtitle: "Sorted by importance and urgency" },
  { name: "by_goals", title: "By Goals", subtitle: "Grouped under each of your goals", requiresGoals: true },
]

const SORT_TEMPLATES: TemplateEntry[] = [
  { name: "priority", title: "Priority", subtitle: "Items needing attention soonest, first" },
]

const KIND_LABEL: Record<FocusEntryKind, string> = { view: "view", sort: "sort" }

const GOAL_NAV_DEBOUNCE_MS = 300

// Every focus row targets the inbox; only the selector differs. These are the
// search shapes <Link> and navigate() both want, which also drops the hand-built
// query strings these used to be.
type FocusSelection = { mailbox_view_id: string } | { mailbox_view_template: string; goal_id?: string }

const viewSelection = (id: string): FocusSelection => ({ mailbox_view_id: id })
const templateSelection = (name: string): FocusSelection => ({ mailbox_view_template: name })
const byGoalSelection = (goalId: string): FocusSelection => ({ mailbox_view_template: "by_goal", goal_id: goalId })

// Clearing the focus can't just navigate to a bare "/": that re-resolves the stored
// preference and lands back on the active focus. Overwriting the preference with the
// default sort is what opts out, the same path the Newest sort option takes.
const CLEAR_FOCUS_SEARCH = { sort: "newest" } as const

interface GoalsListResponse extends PaginatedResponse {
  goals: {
    id: string
    title: string | null
    owner: { id: string } | null
    group: { id: string; name: string } | null
  }[]
}

interface GroupsListResponse {
  groups: { id: string; is_member: boolean }[]
}

function SectionHeader({ label, icon }: { label: string; icon: string }) {
  return (
    <p className="px-2 pt-2 pb-1 text-xs font-semibold text-base-700 flex items-center gap-1.5">
      <span className="material-symbols-outlined text-sm">{icon}</span>
      {label}
    </p>
  )
}

// Each sub-list scrolls on its own (not the whole dropdown), with `overscroll-contain` so reaching
// an end doesn't chain the scroll to the page. A soft gradient fades the top/bottom edge only while
// there's more content in that direction, signaling scrollability without a heavy scrollbar.
function ScrollFadeList({ children }: { children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null)
  const [fade, setFade] = useState({ top: false, bottom: false })

  const update = useCallback(() => {
    const el = ref.current
    if (!el) return
    const { scrollTop, scrollHeight, clientHeight } = el
    setFade({ top: scrollTop > 1, bottom: scrollTop + clientHeight < scrollHeight - 1 })
  }, [])

  useEffect(() => {
    update()
    const el = ref.current
    if (!el) return
    const observer = new ResizeObserver(update)
    observer.observe(el)
    return () => observer.disconnect()
  }, [update])

  return (
    <div className="relative">
      <div ref={ref} onScroll={update} className="max-h-44 overflow-y-auto overscroll-contain [scrollbar-width:thin]">
        {children}
      </div>
      {fade.top && (
        <div className="pointer-events-none absolute inset-x-0 top-0 h-5 bg-gradient-to-b from-base-300 to-transparent" />
      )}
      {fade.bottom && (
        <div className="pointer-events-none absolute inset-x-0 bottom-0 h-5 bg-gradient-to-t from-base-300 to-transparent" />
      )}
    </div>
  )
}

// A single row. The primary target is a link (selecting a focus is a navigation, which is what
// persists it); edit/delete are sibling buttons so we don't nest interactive content (WHATWG
// anchor content model). Edit/delete are only passed for saved views/sorts — built-in templates
// aren't editable.
function FocusRow({
  search,
  title,
  subtitle,
  active,
  kind,
  onEdit,
  onDelete,
}: {
  search: FocusSelection
  title: string
  subtitle: string
  active: boolean
  kind?: FocusEntryKind
  onEdit?: () => void
  onDelete?: () => void
}) {
  return (
    <li className={`group/entry dropdown-item flex items-start gap-2 ${active ? "bg-base-400" : ""}`}>
      <Link to="/" search={search} className="flex items-start gap-2 flex-1 min-w-0">
        <span className="min-w-0">
          <span className={`block text-xs font-medium truncate ${active ? "text-primary" : "text-base-900"}`}>
            {title}
          </span>
          <span className="block text-[11px] text-base-600 truncate">{subtitle}</span>
        </span>
      </Link>
      {(onEdit || onDelete) && (
        <span className="flex items-center gap-1 mt-0.5 opacity-100 @desktop:opacity-0 @desktop:group-hover/entry:opacity-100 transition-opacity">
          {onEdit && (
            <button
              type="button"
              className="cursor-pointer"
              aria-label={`Edit ${kind ? KIND_LABEL[kind] : "entry"}`}
              onClick={onEdit}
            >
              <span className="material-symbols-outlined text-sm">edit</span>
            </button>
          )}
          {onDelete && (
            <button
              type="button"
              className="cursor-pointer"
              aria-label={`Delete ${kind ? KIND_LABEL[kind] : "entry"}`}
              onClick={onDelete}
            >
              <span className="material-symbols-outlined text-sm">close</span>
            </button>
          )}
        </span>
      )}
    </li>
  )
}

// The standing, non-deletable "By goal" sort. Its target goal is changeable via the picker overlay;
// the row itself navigates to the currently-selected goal (or opens the picker if none is chosen).
function GoalSortRow({
  selectedGoal,
  active,
  onApply,
  onChangeGoal,
}: {
  selectedGoal: GoalOption | null
  active: boolean
  onApply: () => void
  onChangeGoal: () => void
}) {
  return (
    <div className="px-2">
      <div className={`group/entry dropdown-item flex items-start gap-2 ${active ? "bg-base-400" : ""}`}>
        <button type="button" className="flex min-w-0 flex-1 items-start gap-2 text-left" onClick={onApply}>
          <span className="min-w-0">
            <span className={`block truncate text-xs font-medium ${active ? "text-primary" : "text-base-900"}`}>
              By goal
            </span>
            <span className="block truncate text-[11px] text-base-600">{selectedGoal?.title ?? "Choose a goal"}</span>
          </span>
        </button>
        <button type="button" className="mt-0.5 cursor-pointer" aria-label="Change goal" onClick={onChangeGoal}>
          <span className="material-symbols-outlined text-sm">chevron_right</span>
        </button>
      </div>
    </div>
  )
}

// Shown in place of the focus menu when the user tries to leave the onboarding "Getting started"
// focus (via the Clear-focus X or by picking another focus). It teaches the Focus concept — the
// thing they just bumped into — and frames leaving as reversible before letting them proceed.
function OnboardingFocusExplainer({ onConfirm, onCancel }: { onConfirm: () => void; onCancel: () => void }) {
  return (
    <div className="p-4">
      <div className="flex size-10 items-center justify-center rounded-xl bg-base-200">
        <span className="material-symbols-outlined text-primary">filter_center_focus</span>
      </div>
      <h3 className="mt-3 text-sm font-semibold text-base-900">This is a Focus</h3>
      <p className="mt-1 text-pretty text-xs text-base-600">
        Organize your inbox around your goals with a Focus. Getting started is your focus right now, but you can leave
        and come back anytime.
      </p>
      <div className="mt-4 flex gap-2">
        <button type="button" className="btn btn-sm flex-1 font-normal" onClick={onConfirm}>
          Leave
        </button>
        <button type="button" className="btn btn-sm btn-primary flex-1 font-normal" onClick={onCancel}>
          Stay in setup
        </button>
      </div>
    </div>
  )
}

interface FormState {
  kind: FocusEntryKind
  editing: FocusEntryEdit | null
  // The saved view/sort being edited, or null when creating a new one.
  viewId: string | null
}

interface FocusDropdownProps {
  allViews: MailboxViewSummary[]
  active: ActiveMailboxView | null
  hasGoalsForView: boolean
  onboardingAvailable: boolean
  createView: (params: { view_request: string; title?: string; layout?: MailboxViewLayout }) => Promise<void>
  updateView: (
    viewId: string,
    params: { view_request?: string; title?: string; layout?: MailboxViewLayout }
  ) => Promise<void>
  deleteView: (viewId: string) => Promise<void>
}

export function FocusDropdown({
  allViews,
  active,
  hasGoalsForView,
  onboardingAvailable,
  createView,
  updateView,
  deleteView,
}: FocusDropdownProps) {
  const { user } = useCurrentUser()
  const currentUserId = user?.id ?? null
  const isMobile = useIsMobile()
  const navigate = useNavigate()

  const customViews = allViews.filter(v => v.layout === "grouped")
  const customSorts = allViews.filter(v => v.layout === "ranked")

  // A template's channel_id is `template:<name>` or, for by_goal, `template:<name>:<goalId>`.
  const activeParts = active?.kind === "template" ? active.id.split(":") : []
  const activeTemplateName = activeParts[1] ?? null
  const activeGoalId = activeParts[2] ?? null
  const activeViewId = active?.kind === "view" ? active.id : null
  const onboardingActive = activeTemplateName === "getting_started"

  const [goals, setGoals] = useState<GoalOption[] | null>(null)
  // Ids of groups the current user belongs to — drives the per-group sections in the picker.
  const [myGroupIds, setMyGroupIds] = useState<string[]>([])
  const goalsLoadingRef = useRef(false)
  const goalsAbortRef = useRef<AbortController | null>(null)
  const [selectedGoalId, setSelectedGoalId] = useState<string | null>(activeGoalId)
  const [goalPickerOpen, setGoalPickerOpen] = useState(false)
  const [formState, setFormState] = useState<FormState | null>(null)
  const [sheetOpen, setSheetOpen] = useState(false)
  // Desktop dropdown open state is controlled so the Clear-focus X can force the menu open into
  // the exit-confirmation panel (see onboardingActive handling below).
  const [menuOpen, setMenuOpen] = useState(false)
  const { needsExplainer, pendingIntent, openExplainer, dismissExplainer } =
    useOnboardingFocusExplainer(onboardingActive)

  const ensureGoals = useCallback(async () => {
    if (goals !== null || goalsLoadingRef.current) return
    goalsLoadingRef.current = true
    const controller = new AbortController()
    goalsAbortRef.current = controller
    try {
      // The picker filters goals client-side, so load every page (not just the first 30) by
      // draining the cursor until the API reports no more.
      // Group membership is a picker-only enhancement, so a failed /api/groups must not block the
      // goals from rendering — fall back to an empty membership set (no group sections).
      const [allGoals, groupsRes] = await Promise.all([
        fetchAllPages("/api/goals", (r: GoalsListResponse) => r.goals, { signal: controller.signal }),
        apiFetch<GroupsListResponse>("/api/groups", { signal: controller.signal }).catch(
          () => ({ groups: [] }) as GroupsListResponse
        ),
      ])
      // An unmount aborted the requests; skip the state updates on a torn-down component.
      if (controller.signal.aborted) return
      setGoals(
        allGoals.map(g => ({
          id: g.id,
          title: g.title ?? "Untitled goal",
          ownerId: g.owner?.id ?? null,
          groupId: g.group?.id ?? null,
          groupName: g.group?.name ?? null,
        }))
      )
      setMyGroupIds((groupsRes.groups ?? []).filter(group => group.is_member).map(group => group.id))
    } catch {
      // An intentional unmount abort isn't a failure — don't surface the error flash.
      if (controller.signal.aborted) return
      // Leave `goals` null (don't set []) so the re-entry guard stays open and the next dropdown
      // open retries — a transient /api/goals failure shouldn't brick the picker for the session.
      showFlash("Couldn't load goals. Try again.", "error")
    } finally {
      goalsLoadingRef.current = false
    }
  }, [goals])

  // Navigating to a goal triggers an LLM generation. Debounce so rapidly swapping goals in the
  // picker doesn't spawn a stream per click — only the last selection within the window navigates.
  const navTimerRef = useRef<number | null>(null)
  useEffect(
    () => () => {
      if (navTimerRef.current !== null) clearTimeout(navTimerRef.current)
    },
    []
  )

  // Cancel any in-flight goals/groups load if the picker unmounts mid-fetch so the
  // resolved setters don't fire (and don't flash an error) on a torn-down component.
  useEffect(() => () => goalsAbortRef.current?.abort(), [])
  const debouncedNavigate = useCallback(
    (search: FocusSelection) => {
      if (navTimerRef.current !== null) clearTimeout(navTimerRef.current)
      navTimerRef.current = window.setTimeout(() => {
        // `replace` so swapping goals in the picker doesn't stack a history entry per
        // selection — the back button should leave the picker, not walk its goals.
        void navigate({ to: "/", search, replace: true })
      }, GOAL_NAV_DEBOUNCE_MS)
    },
    [navigate]
  )

  const selectedGoal = selectedGoalId ? (goals?.find(g => g.id === selectedGoalId) ?? null) : null

  const isByGoalActive = activeTemplateName === "by_goal"
  const activeLabel = (() => {
    if (!active) return "Focus"
    // For a goal sort the server sets the active title to the goal's name; the client-loaded
    // `selectedGoal` is preferred once the goals list resolves (covers a just-picked goal).
    if (isByGoalActive) return selectedGoal?.title ?? active.title ?? "By goal"
    return active.title ?? "Focus"
  })()

  const handleSave = async ({ criteria, title }: { criteria: string; title: string }) => {
    if (!formState) return
    const layout: MailboxViewLayout = formState.kind === "sort" ? "ranked" : "grouped"
    const params = { view_request: criteria, title: title || undefined, layout }
    // Both mutations navigate on success and flash on failure; nothing to do here either way.
    if (formState.viewId) await updateView(formState.viewId, params)
    else await createView(params)
  }

  const handleDelete = async (view: MailboxViewSummary) => {
    const kindLabel = view.layout === "ranked" ? "sort" : "view"
    if (!(await confirm({ message: `Delete this ${kindLabel}? This cannot be undone.` }))) return
    await deleteView(view.id)
  }

  const openEdit = (view: MailboxViewSummary) => {
    setFormState({
      kind: view.layout === "ranked" ? "sort" : "view",
      editing: { title: view.title, criteria: view.view_request },
      viewId: view.id,
    })
  }

  // `min-w-0 !shrink` lets the chip give up width and truncate its label so the header button
  // row never overflows when an active focus has a long name (daisyUI `.btn` is `flex-shrink: 0`
  // by default).
  const triggerClassName = `btn flex min-w-0 !shrink items-center gap-1 font-normal ${
    active ? "rounded-r-none border-primary/50 bg-primary/10 text-primary" : "border border-neutral text-base-600"
  }`
  const triggerInner = (
    <>
      <span className="material-symbols-outlined text-lg">{isByGoalActive ? "target" : "filter_center_focus"}</span>
      <span className="max-w-[12rem] truncate">{activeLabel}</span>
    </>
  )

  // The menu body is identical on both platforms; only its container differs (floating Dropdown on
  // desktop, BottomSheet on mobile). `close` dismisses whichever container is open.
  const renderMenu = (close: () => void) => {
    if (pendingIntent) {
      const intent = pendingIntent
      return (
        <OnboardingFocusExplainer
          onCancel={() => {
            dismissExplainer()
            close()
          }}
          onConfirm={() => {
            dismissExplainer()
            // "leave" navigates away; "browse" just clears the panel so the real menu renders in place.
            if (intent.type === "leave") {
              close()
              void navigate({ to: "/", search: CLEAR_FOCUS_SEARCH })
            }
          }}
        />
      )
    }
    return (
      <>
        {onboardingAvailable && (
          <>
            <SectionHeader label="Onboarding" icon="rocket_launch" />
            <ul className="px-2">
              <FocusRow
                search={templateSelection("getting_started")}
                title="Getting started"
                subtitle="Set up your workspace"
                active={activeTemplateName === "getting_started"}
              />
            </ul>
          </>
        )}
        <SectionHeader label="Custom Views" icon="dashboard" />
        <ScrollFadeList>
          <ul className="px-2">
            {VIEW_TEMPLATES.filter(t => !t.requiresGoals || hasGoalsForView).map(template => (
              <FocusRow
                key={template.name}
                search={templateSelection(template.name)}
                title={template.title}
                subtitle={template.subtitle}
                active={activeTemplateName === template.name}
              />
            ))}
            {customViews.map(view => (
              <FocusRow
                key={view.id}
                search={viewSelection(view.id)}
                title={view.title}
                subtitle={view.view_request}
                active={activeViewId === view.id}
                kind="view"
                onEdit={() => {
                  close()
                  openEdit(view)
                }}
                onDelete={() => handleDelete(view)}
              />
            ))}
          </ul>
        </ScrollFadeList>
        <SectionHeader label="Custom Sorts" icon="sort" />
        {hasGoalsForView && (
          <GoalSortRow
            selectedGoal={selectedGoal}
            active={activeTemplateName === "by_goal"}
            onApply={() => {
              if (selectedGoalId) {
                void navigate({ to: "/", search: byGoalSelection(selectedGoalId) })
              } else {
                close()
                void ensureGoals()
                setGoalPickerOpen(true)
              }
            }}
            onChangeGoal={() => {
              close()
              void ensureGoals()
              setGoalPickerOpen(true)
            }}
          />
        )}
        <ScrollFadeList>
          <ul className="px-2 pb-2">
            {SORT_TEMPLATES.map(template => (
              <FocusRow
                key={template.name}
                search={templateSelection(template.name)}
                title={template.title}
                subtitle={template.subtitle}
                active={activeTemplateName === template.name}
              />
            ))}
            {customSorts.map(sort => (
              <FocusRow
                key={sort.id}
                search={viewSelection(sort.id)}
                title={sort.title}
                subtitle={sort.view_request}
                active={activeViewId === sort.id}
                kind="sort"
                onEdit={() => {
                  close()
                  openEdit(sort)
                }}
                onDelete={() => handleDelete(sort)}
              />
            ))}
          </ul>
        </ScrollFadeList>
        <div className="flex gap-2 border-t border-base-300 p-2">
          <button
            type="button"
            className="btn btn-sm flex-1 gap-1 font-normal"
            onClick={() => {
              close()
              setFormState({ kind: "view", editing: null, viewId: null })
            }}
          >
            <span className="material-symbols-outlined text-base">add</span>
            New view
          </button>
          <button
            type="button"
            className="btn btn-sm flex-1 gap-1 font-normal"
            onClick={() => {
              close()
              setFormState({ kind: "sort", editing: null, viewId: null })
            }}
          >
            <span className="material-symbols-outlined text-base">add</span>
            New sort
          </button>
        </div>
      </>
    )
  }

  const goalPickerContent = (
    <GoalPicker
      goals={goals ?? []}
      loading={goals === null}
      selectedId={selectedGoalId}
      currentUserId={currentUserId}
      myGroupIds={myGroupIds}
      onSelect={goalId => {
        setSelectedGoalId(goalId)
        setGoalPickerOpen(false)
        debouncedNavigate(byGoalSelection(goalId))
      }}
    />
  )

  return (
    <div className="flex min-w-0 items-center">
      {isMobile ? (
        <>
          <button
            type="button"
            className={triggerClassName}
            data-test-id="focus-dropdown"
            onClick={() => {
              setSheetOpen(true)
              void ensureGoals()
              // First touch during onboarding opens into the explainer instead of the menu.
              if (needsExplainer) openExplainer({ type: "browse" })
            }}
          >
            {triggerInner}
          </button>
          {sheetOpen && (
            <BottomSheet
              title="Focus"
              ariaLabel="Focus views and sorts"
              onClose={() => {
                setSheetOpen(false)
                dismissExplainer()
              }}
            >
              <div className="overflow-y-auto pb-3">
                {renderMenu(() => {
                  setSheetOpen(false)
                  dismissExplainer()
                })}
              </div>
            </BottomSheet>
          )}
        </>
      ) : (
        <Dropdown
          placement="bottom-start"
          ariaLabel="Focus views and sorts"
          open={menuOpen}
          onOpenChange={open => {
            setMenuOpen(open)
            if (open) {
              void ensureGoals()
              // First touch during onboarding opens into the explainer instead of the menu.
              if (needsExplainer) openExplainer({ type: "browse" })
            } else {
              dismissExplainer()
            }
          }}
          trigger={
            <button type="button" className={triggerClassName} data-test-id="focus-dropdown">
              {triggerInner}
            </button>
          }
          className="dropdown-card z-50 w-72"
        >
          {({ close }) => renderMenu(close)}
        </Dropdown>
      )}
      {active &&
        (onboardingActive ? (
          // First touch during onboarding routes through the "This is a Focus" explainer: open the
          // menu (or sheet) into it instead of clearing. Once seen, the X clears like normal.
          <button
            type="button"
            className="btn rounded-l-none border border-l-0 border-primary/50 bg-primary/10 px-2 text-primary hover:bg-primary/20"
            aria-label="Clear focus"
            onClick={() => {
              if (needsExplainer) {
                openExplainer({ type: "leave" })
                if (isMobile) setSheetOpen(true)
                else setMenuOpen(true)
              } else {
                void navigate({ to: "/", search: CLEAR_FOCUS_SEARCH })
              }
            }}
          >
            <span className="material-symbols-outlined text-base">close</span>
          </button>
        ) : (
          <Link
            to="/"
            search={CLEAR_FOCUS_SEARCH}
            className="btn rounded-l-none border border-l-0 border-primary/50 bg-primary/10 px-2 text-primary hover:bg-primary/20"
            aria-label="Clear focus"
          >
            <span className="material-symbols-outlined text-base">close</span>
          </Link>
        ))}

      {/* Forms and the goal picker: a BottomSheet on mobile, a centered Dialog on desktop. The
          inner content components are shared verbatim. */}
      {isMobile ? (
        <>
          {formState && (
            <BottomSheet
              ariaLabel={formState.kind === "sort" ? "Custom sort" : "Custom view"}
              onClose={() => setFormState(null)}
            >
              <FocusEntryForm
                kind={formState.kind}
                editingEntry={formState.editing}
                onSave={handleSave}
                onCancel={() => setFormState(null)}
              />
            </BottomSheet>
          )}
          {goalPickerOpen && (
            <BottomSheet ariaLabel="Sort by goal" onClose={() => setGoalPickerOpen(false)}>
              {goalPickerContent}
            </BottomSheet>
          )}
        </>
      ) : (
        <>
          <Dialog
            isOpen={formState !== null}
            onClose={() => setFormState(null)}
            ariaLabel={formState?.kind === "sort" ? "Custom sort" : "Custom view"}
            className="floating-card w-11/12 max-w-lg overflow-hidden !p-0"
          >
            {formState && (
              <FocusEntryForm
                kind={formState.kind}
                editingEntry={formState.editing}
                onSave={handleSave}
                onCancel={() => setFormState(null)}
              />
            )}
          </Dialog>
          <Dialog
            isOpen={goalPickerOpen}
            onClose={() => setGoalPickerOpen(false)}
            ariaLabel="Sort by goal"
            className="floating-card w-11/12 max-w-md overflow-hidden !p-0"
          >
            {goalPickerContent}
          </Dialog>
        </>
      )}
    </div>
  )
}
