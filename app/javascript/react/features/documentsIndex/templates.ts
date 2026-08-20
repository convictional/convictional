// Starter templates for the "Start a new document" row. Selecting one POSTs its title + markdown
// body to /api/documents, which seeds the Yjs body server-side, then opens the editor. Bodies are
// intentionally light scaffolds. (How docs work is taught by the seeded "You should read this" doc,
// not a template — see app/organization_setup.py.)

export interface DocTemplate {
  key: string
  label: string
  // Material Symbols icon name shown on the card.
  icon: string
  // A function when the title depends on the moment (the daily note carries today's date).
  title: string | (() => string)
  body: string
}

const todayLabel = () => new Date().toLocaleDateString(undefined, { month: "long", day: "numeric", year: "numeric" })

const DAILY_NOTE = `## Focus
What matters most today?

## Notes

## Follow-ups
`

const MEETING_NOTES = `## Attendees

## Agenda

## Notes

## Decisions
`

const PROJECT_BRIEF = `## Problem
What are we solving, and for whom?

## Goal
What does success look like?

## Approach
How will we get there?

## Open questions
`

export const DOC_TEMPLATES: DocTemplate[] = [
  { key: "blank", label: "Blank", icon: "add", title: "", body: "" },
  { key: "daily", label: "Daily note", icon: "today", title: () => `Daily note, ${todayLabel()}`, body: DAILY_NOTE },
  { key: "meeting", label: "Meeting notes", icon: "groups", title: "Meeting notes", body: MEETING_NOTES },
  { key: "brief", label: "Project brief", icon: "assignment", title: "Project brief", body: PROJECT_BRIEF },
]
