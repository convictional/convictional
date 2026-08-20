// The activity phrasings shared by every event-driven inbox body — the actions that mean the same
// thing on any resource (collaborator add/remove, assignment, decided). One home so the wording
// can't drift between the resources. It lives in composites/ (not the mailboxIndex island) so every
// consumer can reach it: the post/goal bodies and goal's composites-layer preview all import it,
// which composites↛features layering would forbid if it lived under the island. Resources that have
// their own extra vocabulary (posts: created/announced/pinned; goals: state changes) fall back here.

import type { EventAction } from "~/react/shared/types"

type Details = Record<string, unknown>

export interface ActivityContext {
  actorName?: string | null
  // The event actor's id and the viewer's id, so collaborator phrasing can say "You"/"you"
  // when the actor or the added person is the current user.
  actorId?: string | null
  currentUserId?: string | null
}

// The added/removed collaborator and the assignee ride a User.field_values object on Event.details
// (collaborator under `collaborator`, assignment under `assignee`), JSON-serialized so `id` is a string.
function userRecord(details: Details, key: string): Record<string, unknown> | undefined {
  const user = details[key]
  return user && typeof user === "object" ? (user as Record<string, unknown>) : undefined
}

// Prefer name, fall back to email — mirrors the resource timelines.
export function userName(details: Details, key: string): string | undefined {
  const record = userRecord(details, key)
  const label = record?.name ?? record?.email
  return typeof label === "string" ? label : undefined
}

function userId(details: Details, key: string): string | undefined {
  const id = userRecord(details, key)?.id
  return typeof id === "string" ? id : undefined
}

// Phrase an "<actor> <verb> <person>" activity line, substituting "You"/"you" when the actor or the
// person (the User under `personKey` on details) is the viewer; otherwise use names. `verb` is the
// lowercase past tense ("added", "assigned to"); the actor-less form capitalizes it ("Added X").
// `fallback` is returned when neither party is known ("Added a collaborator", "Assigned").
function describeUserAction(
  verb: string,
  personKey: string,
  fallback: string,
  details: Details,
  context: ActivityContext
): string {
  const isViewer = (id: string | null | undefined): boolean => !!context.currentUserId && id === context.currentUserId
  const actorLabel = isViewer(context.actorId) ? "You" : context.actorName
  const personLabel = isViewer(userId(details, personKey)) ? "you" : userName(details, personKey)
  const capitalized = `${verb[0].toUpperCase()}${verb.slice(1)}`

  if (actorLabel && personLabel) return `${actorLabel} ${verb} ${personLabel}`
  if (personLabel) return `${capitalized} ${personLabel}`
  return fallback
}

// A phrased line for a cross-resource action, or null when the action is resource-specific and the
// caller must phrase it itself.
export function describeCrossResourceActivity(
  action: EventAction | null,
  details: Details,
  context: ActivityContext
): string | null {
  switch (action) {
    case "added_collaborator":
      return describeUserAction("added", "collaborator", "Added a collaborator", details, context)
    case "removed_collaborator":
      return describeUserAction("removed", "collaborator", "Removed a collaborator", details, context)
    case "assigned":
      return describeUserAction("assigned to", "assignee", "Assigned", details, context)
    case "unassigned":
      return describeUserAction("unassigned", "assignee", "Unassigned", details, context)
    case "decided":
      return "Marked as decided"
    default:
      return null
  }
}
