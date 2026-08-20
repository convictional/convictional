import { Plugin } from "prosemirror-state"
import type { Awareness } from "y-protocols/awareness"
import type { Transaction } from "yjs"

// Must match app/styles/prosemirror.css.
const CURSOR_CLASS = "ProseMirror-yjs-cursor"
const CURSOR_LABEL_CLASS = "cursor-label"
const FADED_CLASS = "faded"

// Time from a collaborator's last activity until their name tag re-fades.
const CURSOR_LABEL_LINGER_MS = 3000

// A cursor move or document edit makes yCursorPlugin rebuild this widget, so its
// faded state must be a pure function of `revealed` to survive the rebuild.
// data-client-id lets the linger timer find the live node to fade it (see below).
export function buildCursorElement(
  user: { name: string; color: string },
  clientId: number,
  revealed: boolean
): HTMLElement {
  const cursor = document.createElement("span")
  cursor.classList.add(CURSOR_CLASS)
  cursor.dataset.clientId = String(clientId)
  cursor.style.borderColor = user.color

  const userDiv = document.createElement("div")
  userDiv.classList.add(CURSOR_LABEL_CLASS)
  userDiv.style.backgroundColor = user.color
  if (!revealed) userDiv.classList.add(FADED_CLASS)
  userDiv.insertBefore(document.createTextNode(user.name), null)

  const wordJoinerBefore = document.createTextNode("\u2060")
  const wordJoinerAfter = document.createTextNode("\u2060")
  cursor.insertBefore(wordJoinerBefore, null)
  cursor.insertBefore(userDiv, null)
  cursor.insertBefore(wordJoinerAfter, null)

  return cursor
}

interface CursorRevealPlugin {
  plugin: Plugin
  // cursorBuilder gets (user, clientId) but not the view, so it can't read plugin
  // state; expose a predicate over the revealed set instead.
  isRevealed: (clientId: number) => boolean
}

export function createCursorRevealPlugin(awareness: Awareness): CursorRevealPlugin {
  const revealedClients = new Set<number>()

  const plugin = new Plugin({
    view(view) {
      const revealTimers = new Map<number, ReturnType<typeof setTimeout>>()
      // A rebuild reuses the on-screen node when a peer types (y-prosemirror keys the
      // widget by clientId, and the edit maps the old position onto the new one, so
      // ProseMirror treats the widgets as equal and keeps the stale node). Toggling the
      // faded class on the live node reveals/hides regardless of whether a rebuild fires.
      const liveLabel = (clientId: number) =>
        view.dom.querySelector(`.${CURSOR_CLASS}[data-client-id="${clientId}"] .${CURSOR_LABEL_CLASS}`)

      const reveal = (clientId: number) => {
        if (clientId === awareness.clientID) return
        revealedClients.add(clientId)
        liveLabel(clientId)?.classList.remove(FADED_CLASS)
        // Re-arm on each signal so continuous activity keeps the label up.
        clearTimeout(revealTimers.get(clientId))
        revealTimers.set(
          clientId,
          setTimeout(() => {
            revealedClients.delete(clientId)
            revealTimers.delete(clientId)
            // CSS opacity transition animates the fade; revealedClients stays cleared
            // so a later rebuild renders it faded too.
            liveLabel(clientId)?.classList.add(FADED_CLASS)
          }, CURSOR_LABEL_LINGER_MS)
        )
      }

      // Listen on "change", not "update": awareness renews each client's clock every
      // ~15s, firing "update" for idle peers; "change" fires only on real state changes,
      // so idle collaborators' tags don't flash. This covers cursor moves and joins.
      const onAwarenessChange = ({
        added,
        updated,
        removed,
      }: {
        added: number[]
        updated: number[]
        removed: number[]
      }) => {
        for (const clientId of removed) {
          clearTimeout(revealTimers.get(clientId))
          revealTimers.delete(clientId)
          revealedClients.delete(clientId)
        }
        for (const clientId of [...added, ...updated]) reveal(clientId)
      }

      // Typing edits the document without moving the awareness cursor enough to fire a
      // "change", so it would otherwise not reveal the label. Reveal any peer whose
      // clock advanced in a transaction, keeping their tag up while they type.
      const onTransaction = (tr: Transaction) => {
        tr.afterState.forEach((clock, clientId) => {
          if ((tr.beforeState.get(clientId) ?? 0) < clock && awareness.getStates().has(clientId)) reveal(clientId)
        })
      }

      awareness.on("change", onAwarenessChange)
      awareness.doc.on("afterTransaction", onTransaction)
      return {
        destroy() {
          awareness.off("change", onAwarenessChange)
          awareness.doc.off("afterTransaction", onTransaction)
          for (const timer of revealTimers.values()) clearTimeout(timer)
          revealTimers.clear()
          revealedClients.clear()
        },
      }
    },
  })

  return { plugin, isRevealed: clientId => revealedClients.has(clientId) }
}
