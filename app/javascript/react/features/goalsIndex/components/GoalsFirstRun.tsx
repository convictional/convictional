import { ResourceBadge } from "~/react/composites/ResourceBadge"
import { EmptyStateSurface } from "~/react/ui/EmptyStateSurface"

import inboxFocusGif from "./inbox_focus.gif"

// First-run state for the goals index when the org has no goals yet. Goals are solo-authorable and
// nothing gates them, so this supplies the reason (a goal is the spine work aligns to) and opens the
// inline create row, rather than handing over a tool or pushing invites the way chat/posts do.
//
// Composition: copy + CTA anchored left, the "By Goals" inbox Focus demo bleeding in from the right.
// At lg+ the clip is oversized and left-anchored so its right and bottom edges run past the surface
// and get masked by overflow-hidden — it reads as the inbox peeking in mid-regroup. Below lg the
// split collapses to a stacked layout with the clip as a normal framed panel below the copy.
export function GoalsFirstRun({ onStartCreating }: { onStartCreating: () => void }) {
  return (
    <EmptyStateSurface className="relative overflow-hidden">
      <div className="flex flex-col items-center gap-10 lg:flex-row lg:items-stretch lg:gap-0">
        <div className="flex flex-col items-center px-8 pt-14 text-center lg:w-[46%] lg:shrink-0 lg:items-start lg:py-20 lg:pr-6 lg:pl-10 lg:text-left">
          <div className="mb-4 rounded-2xl border border-base-300 bg-base-50 p-1 shadow-sm">
            <ResourceBadge contentType="goal" size="medium" />
          </div>

          <h2 className="max-w-md font-accent text-lg text-base-content text-balance">
            Focus everyone&rsquo;s work with goals
          </h2>
          <p className="mt-2 max-w-md text-sm text-base-content/60 text-pretty">
            Align every chat, post, and decision to a goal, and the whole team&rsquo;s work organizes around what
            actually moves it forward.
          </p>

          <button type="button" onClick={onStartCreating} className="btn btn-primary mt-5 rounded-full">
            <span className="material-symbols-outlined text-base">add</span>
            Create your first goal
          </button>
        </div>

        <div className="relative w-full max-w-md px-8 pb-14 lg:max-w-none lg:flex-1 lg:self-stretch lg:px-0 lg:pb-0">
          <img
            src={inboxFocusGif}
            alt="Switching to the By Goals focus regroups the inbox so each message sits under the goal it moves"
            loading="lazy"
            className="dark-media-invert block w-full rounded-xl border border-base-300 shadow-md lg:absolute lg:top-10 lg:left-0 lg:w-[120%] lg:max-w-none lg:rounded-2xl lg:shadow-xl"
          />
        </div>
      </div>
    </EmptyStateSurface>
  )
}
