import diff from "fast-diff"
import { keymap as keymapPlugin } from "prosemirror-keymap"
import { type Command, Plugin } from "prosemirror-state"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import {
  prosemirrorToYXmlFragment,
  redo,
  undo,
  yCursorPlugin,
  ySyncPlugin,
  ySyncPluginKey,
  yUndoPlugin,
  yUndoPluginKey,
  yXmlFragmentToProseMirrorRootNode,
} from "y-prosemirror"
import * as Y from "yjs"

import { ChannelsClient } from "~/channels/client"
import { Topic } from "~/channels/topic"
import { ChannelsYjsProvider } from "~/channels/yjsProvider"
import { parse, schema, serialize } from "~/richText/schema"
import { createLocalPersistence } from "~/shared/localPersistence"
import type { ChannelStream } from "~/types/channels"
import type { EditorFeature, SyncStatus } from "../types"
import { buildCursorElement, createCursorRevealPlugin } from "./cursorReveal"

export interface CollaborationFeature extends EditorFeature {
  status: SyncStatus
  docSynced: boolean
  ready: boolean
  // Imperative release of the Yjs WebSocket. Lets callers tear the socket down
  // before React unmounts so a subsequent reconnection on the same topic can't
  // race the still-open one (DRAFT_REMOVED → DRAFT_STARTED in the email composer).
  disconnect: () => void
}

interface UseCollaborationOptions {
  channelsClient: ChannelsClient | null
  // The live-document topic the editor collaborates on, named by stream + identity
  // params (e.g. DOCUMENT + { document_id }). Subscribed unsigned via subscribeTo.
  stream: ChannelStream
  params: Record<string, string>
  currentUser: { id: string; displayName: string }
  initialContent: string | null
}

type YjsDelta = { insert: string } | { retain: number } | { delete: number }

export function diffToDelta(diffResult: ReturnType<typeof diff>): YjsDelta[] {
  return diffResult.map(([op, value]) =>
    op === diff.INSERT ? { insert: value } : op === diff.EQUAL ? { retain: value.length } : { delete: value.length }
  )
}

// Lives outside the hook so it can be called from useEffect, where cleanup
// of the provider, IndexedDB, and listeners is guaranteed.
function createLiveDocumentSession(
  channelsClient: ChannelsClient,
  stream: ChannelStream,
  params: Record<string, string>,
  currentUser: { id: string; displayName: string },
  initialContent: string | null,
  onStatus: (status: SyncStatus) => void,
  onSync: () => void
) {
  const ydoc = new Y.Doc()
  const yXmlFragment = ydoc.getXmlFragment("prosemirror")
  const yMarkdownText = ydoc.getText("markdown")
  const yInitialContent = ydoc.getText("initial_content")
  const editors = ydoc.getMap("editors")

  const provider = new ChannelsYjsProvider(channelsClient, stream, params, ydoc)
  // Key IndexedDB by the canonical topic name — stable identity across subscribe forms.
  const persistence = createLocalPersistence(new Topic(stream, params).name, ydoc)

  // y-prosemirror validates the cursor color as a 6-digit hex and warns otherwise,
  // so resolve --color-primary (a hex in every theme) instead of passing the raw var.
  const primaryColor =
    getComputedStyle(document.documentElement).getPropertyValue("--color-primary").trim() || "#2b7fff"
  provider.awareness.setLocalStateField("user", {
    id: currentUser.id,
    name: currentUser.displayName,
    color: primaryColor,
  })

  // Set clientID to 0 so all clients seeding the same initial content produce
  // identical Yjs state vectors. Without this, each client's copy gets a unique
  // clientID, causing diverging state and duplicate content on sync.
  const withDeterministicClientID = <T>(fn: () => T): T => {
    const originalClientID = ydoc.clientID
    ydoc.clientID = 0
    try {
      return fn()
    } finally {
      ydoc.clientID = originalClientID
    }
  }

  const existingDoc = initialContent ? parse(initialContent) : null
  const hasLocalContent = existingDoc && existingDoc.content.size > 2

  // Wait for IndexedDB to load before checking whether to seed from initialContent.
  // Without this, the WebSocket sync could fire first on a fast server, see an empty
  // yXmlFragment (IndexedDB hasn't loaded yet), and double-seed the document.
  const registerSeedHandler = () => {
    ydoc.once("sync", () => {
      if (hasLocalContent && yXmlFragment.length === 0) {
        withDeterministicClientID(() => prosemirrorToYXmlFragment(existingDoc, yXmlFragment))
      }
    })
  }
  persistence.scheduleAfterSync(registerSeedHandler)

  const migrateInitialContent = () => {
    if (yInitialContent.length === 0) return
    if (yXmlFragment.length > 0) {
      ydoc.transact(() => yInitialContent.delete(0, yInitialContent.length), "initial-content-migration")
      return
    }
    const doc = parse(yInitialContent.toString())
    withDeterministicClientID(() => {
      ydoc.transact(() => {
        prosemirrorToYXmlFragment(doc, yXmlFragment)
        yInitialContent.delete(0, yInitialContent.length)
      }, "initial-content-migration")
    })
  }

  const applyMarkdownDiff = (oldText: string, newText: string) => {
    const diffs = diff(oldText, newText)
    const delta = diffToDelta(diffs)
    ydoc.transact(() => yMarkdownText.applyDelta(delta))
  }

  ydoc.on("afterTransaction", (tr: Y.Transaction) => {
    // Relies on remote (websocket) transactions having a non-null origin set
    // by ChannelsYjsProvider. When persistence.provider is null, the check
    // collapses to `tr.origin !== null`, which still excludes those.
    if (!tr.local && tr.origin !== persistence.provider) return
    const currentMarkdown = yMarkdownText.toString()
    const newMarkdown = serialize(yXmlFragmentToProseMirrorRootNode(yXmlFragment, schema))

    if (currentMarkdown !== newMarkdown) {
      if (currentMarkdown.length === 0) {
        yMarkdownText.insert(0, newMarkdown)
      } else {
        applyMarkdownDiff(currentMarkdown, newMarkdown)
      }

      if (tr.origin !== "initial-content-migration" && currentUser.id) {
        editors.set(currentUser.id, true)
      }
    }
  })

  const initialContentObserver = () => {
    if (yInitialContent.length > 0) {
      yInitialContent.unobserve(initialContentObserver)
      migrateInitialContent()
    }
  }
  yInitialContent.observe(initialContentObserver)

  provider.on("status", (data: { status: SyncStatus }) => onStatus(data.status))
  ydoc.on("sync", () => onSync())

  // No `mapping` option on ySyncPlugin: passing one signals "I've pre-built a
  // PM doc that mirrors yXmlFragment", which suppresses y-prosemirror's
  // `_forceRerender` at view construction. We can't pre-build a doc (the
  // React editor doesn't accept one), so without `_forceRerender` any content
  // that populated yXmlFragment between session creation and editor mount
  // (typical on reload via IndexedDB or network sync) never reaches the view.
  // Undoing all content down to a zero-node fragment forces ProseMirror to
  // schema-fill an empty paragraph, which y-prosemirror then writes back to Yjs
  // as a tracked ySyncPlugin edit. The UndoManager treats that write as a fresh
  // user edit, clearing the redo stack — so redo right after undo restored
  // nothing. The write is deferred (the React binding batches dispatches), so a
  // synchronous guard around undo()/redo() can't catch it. Instead, when an
  // undo/redo empties the fragment, arm a one-shot flag that drops the very next
  // tracked ySyncPlugin write (the schema-fill) from history. The fill always
  // lands before any further user input, so this can't swallow a real edit.
  // Only arm when the command actually ran (result truthy): a no-op undo on an
  // already-empty doc must not arm the flag, or it would drop the user's next
  // real edit from history.
  let dropNextFillWrite = false
  const guardUndoRedo =
    (command: Command): Command =>
    (state, dispatch, view) => {
      const result = command(state, dispatch, view)
      if (result && yXmlFragment.length === 0) dropNextFillWrite = true
      return result
    }

  const cursorReveal = createCursorRevealPlugin(provider.awareness)

  const plugins = [
    ySyncPlugin(yXmlFragment),
    yCursorPlugin(provider.awareness, {
      cursorBuilder: (user, clientId) => buildCursorElement(user, clientId, cursorReveal.isRevealed(clientId)),
    }),
    yUndoPlugin(),
    keymapPlugin({ "Mod-z": guardUndoRedo(undo), "Mod-Shift-z": guardUndoRedo(redo) }),
    cursorReveal.plugin,
    new Plugin({
      view(view) {
        const undoManager = yUndoPluginKey.getState(view.state)?.undoManager
        // captureTransaction is a documented Y.UndoManager option but we override
        // it as an instance property, which relies on its internal storage. Guard
        // so a future y-prosemirror/yjs upgrade that moves it degrades to "redo
        // fix inactive" (still covered by test_document_redo_after_undo) rather
        // than throwing on every collaborative editor mount.
        if (undoManager && typeof undoManager.captureTransaction === "function") {
          const captureTransaction = undoManager.captureTransaction.bind(undoManager)
          undoManager.captureTransaction = (tr: Y.Transaction) => {
            if (dropNextFillWrite && tr.origin === ySyncPluginKey) {
              dropNextFillWrite = false
              return false
            }
            return captureTransaction(tr)
          }
        }
        return {}
      },
    }),
  ]

  return {
    plugins,
    destroy: () => {
      persistence.destroy()
      // Clear awareness before destroying so other clients remove this cursor
      // immediately rather than waiting for the stale awareness timeout
      provider.awareness.setLocalState(null)
      provider.destroy()
    },
  }
}

interface UseLiveDocumentResult {
  plugins: Plugin[]
  syncStatus: SyncStatus
  docSynced: boolean
  disconnect: () => void
}

function useLiveDocument(
  channelsClient: ChannelsClient | null,
  stream: ChannelStream | null,
  params: Record<string, string>,
  currentUser: { id: string; displayName: string },
  initialContent: string | null
): UseLiveDocumentResult {
  const [syncStatus, setSyncStatus] = useState<SyncStatus>("connecting")
  const [docSynced, setDocSynced] = useState(false)
  const [plugins, setPlugins] = useState<Plugin[]>([])
  const sessionRef = useRef<{ destroy: () => void } | null>(null)

  // Provider creation and cleanup are both inside useEffect, so React guarantees
  // the cleanup runs before a new effect fires. This prevents the orphaned-provider
  // bug that occurred when the provider was created during render — if the component
  // unmounted before useEffect ran, the provider leaked with its resync interval.
  useEffect(() => {
    if (!stream || !channelsClient) return

    const session = createLiveDocumentSession(
      channelsClient,
      stream,
      params,
      currentUser,
      initialContent,
      setSyncStatus,
      () => setDocSynced(true)
    )
    sessionRef.current = session

    // Plugins are created here (not during render) because they depend on the
    // provider, which must live in useEffect for cleanup guarantees. The cascading
    // re-render is intentional — the parent waits for plugins before mounting ProseMirror.
    setPlugins(session.plugins) // eslint-disable-line react-hooks/set-state-in-effect

    // On page refresh, useEffect cleanup may not run (or runs too late for the
    // WebSocket message to be sent). beforeunload fires early enough to clear
    // awareness so other clients remove this user's cursor immediately.
    const onBeforeUnload = () => sessionRef.current?.destroy()
    window.addEventListener("beforeunload", onBeforeUnload)

    return () => {
      window.removeEventListener("beforeunload", onBeforeUnload)
      sessionRef.current?.destroy()
      sessionRef.current = null
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Imperative disconnect lets a host tear the socket down before React unmounts
  // (e.g. on a remote DRAFT_REMOVED). Idempotent: clearing the ref makes the
  // useEffect cleanup a no-op when React eventually unmounts the component.
  const disconnect = useCallback(() => {
    sessionRef.current?.destroy()
    sessionRef.current = null
  }, [])

  return { plugins, syncStatus, docSynced, disconnect }
}

export function useCollaboration({
  channelsClient,
  stream,
  params,
  currentUser,
  initialContent,
}: UseCollaborationOptions): CollaborationFeature {
  const stableCurrentUser = useMemo(
    () => ({ id: currentUser.id, displayName: currentUser.displayName }),
    [currentUser.id, currentUser.displayName]
  )

  const { plugins, syncStatus, docSynced, disconnect } = useLiveDocument(
    channelsClient,
    stream,
    params,
    stableCurrentUser,
    initialContent
  )

  return {
    plugins,
    // yUndoPlugin (added in createLiveDocumentSession) owns undo/redo here, so
    // the Editor must not also register prosemirror-history.
    providesHistory: true,
    status: syncStatus,
    docSynced,
    // ready gates rendering because ProseMirror's defaultState is only read on
    // mount — plugins can't be added after the fact.
    ready: plugins.length > 0,
    disconnect,
  }
}
