import { RangeWithCursor, Suggester } from "prosemirror-suggest"
import { EditorView } from "prosemirror-view"
import { useCallback, useEffect, useMemo, useRef, type RefObject } from "react"

import type { MentionUser } from "~/react/shared/hooks/useMentionableUsers"
import { schema } from "~/richText/schema"
import type { EditorFeature } from "../types"
import { SuggesterActions, SuggesterCallback, SuggesterState, useSuggester } from "./useSuggester"
import { useViewRef } from "./useViewRef"

const invalidNodes = [schema.nodes.heading.name, schema.nodes.code_block.name]
const invalidMarks = [schema.marks.code.name]

export interface MentionState {
  suggesterState: SuggesterState<MentionUser>
  dropdownRef: RefObject<HTMLDivElement | null>
  actions: SuggesterActions<MentionUser>
}

export interface MentionFeature extends EditorFeature {
  state: MentionState
}

interface UseMentionsOptions {
  // Mention candidates, sourced from the organizationMembers store via
  // useMentionableUsers. Empty until the store loads.
  users: MentionUser[]
  // Whether this editor supports mentions at all (e.g. chat dm/self chats don't).
  // Replaces the old "is the mentions url non-null" gate.
  enabled?: boolean
}

// Sort collaborators first so keyboard nav order matches the rendered sections.
// MentionSuggester splits its dropdown into "Collaborators" and "Invite to
// collaborate" using the same flag.
function sortCollaboratorsFirst(users: MentionUser[]): MentionUser[] {
  return [...users.filter(u => u.is_collaborator), ...users.filter(u => !u.is_collaborator)]
}

export function useMentions({ users, enabled = true }: UseMentionsOptions): MentionFeature {
  const { viewRef, plugin: viewPlugin } = useViewRef()
  const onChangeRef = useRef<SuggesterCallback | null>(null)

  const suggester: Suggester = useMemo(
    () => ({
      char: "@",
      name: "mentions",
      invalidNodes,
      invalidMarks,
      // Fire onChange from prosemirror-suggest's appendTransaction (which runs in
      // state.apply) rather than its plugin-view update. The view-update path only
      // runs via @handlewithcare/react-prosemirror's commitPendingEffects layout
      // effect, which does not propagate when the editor is nested inside another
      // ProseMirror editor (document comment composers live inside the doc body
      // editor), so the dropdown never opens there. state.apply runs in every
      // editor, nested or not.
      appendTransaction: true,
      onChange: props => onChangeRef.current?.(props),
    }),
    []
  )

  const insertMention = useCallback((item: MentionUser, range: RangeWithCursor, view: EditorView) => {
    const { from, to } = range
    const tr = view.state.tr
      .replaceRangeWith(from, to, schema.nodes.mention.create({ name: item.display_name }))
      .insertText(" ")
    view.dispatch(tr)
  }, [])

  const {
    state: suggesterState,
    dropdownRef,
    onChange,
    actions,
  } = useSuggester<MentionUser>({
    name: "mentions",
    items: users,
    fuseKeys: ["display_name"],
    onSelect: insertMention,
    sortResults: sortCollaboratorsFirst,
    viewRef,
  })

  useEffect(() => {
    onChangeRef.current = onChange
  }, [onChange])

  return {
    plugins: [viewPlugin],
    suggesters: enabled ? [suggester] : [],
    state: { suggesterState, dropdownRef, actions },
  }
}
