import { useCallback, useEffect, useRef, useState } from "react"

import { isNativeShell } from "~/nativeShell"
import { ChatComposerEditor, type ChatEditorHandle } from "~/react/composites/chat/ChatComposerEditor"
import { ComposeReplyPreview } from "~/react/composites/chat/ComposeReplyPreview"
import { LinkPreviewCard } from "~/react/composites/chat/LinkPreviewCard"
import { GifPicker, type KlipyGif } from "~/react/composites/editor/components/GifPicker"
import { useIsMobile } from "~/react/shared/hooks/useIsMobile"
import type { MentionUser } from "~/react/shared/hooks/useMentionableUsers"
import type { ChatType, LinkPreview, ReplyPreview } from "~/react/shared/types"
import { Avatar } from "~/react/ui/Avatar"

// Keeps the compose bar just above the software keyboard. Two positioning modes:
//
// - Native app (position: fixed, nativeShell): the WKWebView shell doesn't
//   re-stick a sticky bar on keyboard-open, so drive an explicit fixed bar. "Open"
//   is keyed off focus because the keyboard-height math reads ~0 there (the layout
//   viewport shrinks with the keyboard); pin to that occlusion when open, and clear
//   to the CSS safe-area clearance when closed. WKWebView emits no settled resize
//   on keyboard-open, so re-measure across the animation off focusin/out.
// - Browser (position: sticky): the layout viewport shrinks (iOS) or the offset
//   math (incl. vv.offsetTop, which tracks Safari's page-pan) handles it, and
//   sticky re-sticks the bar above the keyboard on its own.
function useKeyboardAwareBottom(ref: React.RefObject<HTMLElement | null>, nativeShell: boolean) {
  useEffect(() => {
    const vv = window.visualViewport
    if (!vv) return

    const update = () => {
      const el = ref.current
      if (!el) return
      // Native: focus drives "open" — WKWebView shrinks the layout viewport, so
      // the height math reads ~0 there. Browser: subtract vv.offsetTop too (it
      // tracks Safari's page-pan) and infer "open" from the resulting height.
      const keyboardHeight = Math.max(0, window.innerHeight - vv.height - (nativeShell ? 0 : vv.offsetTop))
      const open = nativeShell ? el.contains(document.activeElement) : keyboardHeight > 0
      el.style.bottom = open ? `${keyboardHeight}px` : ""
      el.style.setProperty("--keyboard-height", `${keyboardHeight}px`)
    }

    update()
    vv.addEventListener("resize", update)
    vv.addEventListener("scroll", update)

    let raf = 0
    const settle = () => {
      cancelAnimationFrame(raf)
      let frames = 0
      const tick = () => {
        update()
        if (frames++ < 24) raf = requestAnimationFrame(tick)
      }
      tick()
    }
    if (nativeShell) {
      document.addEventListener("focusin", settle)
      document.addEventListener("focusout", settle)
    }

    return () => {
      vv.removeEventListener("resize", update)
      vv.removeEventListener("scroll", update)
      document.removeEventListener("focusin", settle)
      document.removeEventListener("focusout", settle)
      cancelAnimationFrame(raf)
    }
  }, [ref, nativeShell])
}

interface ComposeBarProps {
  currentUser: { id: string; displayName: string; picture: string | null }
  sending: boolean
  sendError: boolean
  composePreview: LinkPreview | null
  uploadUrl: string
  mentionableUsers: MentionUser[]
  mentionsEnabled?: boolean
  klipyApiKey: string | null
  chatType: ChatType
  claimId: string
  replyTo: ReplyPreview | null
  editorRef: React.RefObject<ChatEditorHandle | null>
  onSend: (content: string, claimId?: string) => void
  onChange: (content: string) => void
  onEditPrevious: () => boolean
  onDismissPreview: () => void
  onClearReply: () => void
  // Skip the initial desktop autofocus (e.g. the chat was opened from a mailbox
  // list, where focus in the composer would swallow the prev/next nav hotkeys).
  // The after-send refocus and reply focus are unaffected.
  suppressInitialAutoFocus?: boolean
}

export function ComposeBar({
  currentUser,
  sending,
  sendError,
  composePreview,
  uploadUrl,
  mentionableUsers,
  mentionsEnabled,
  klipyApiKey,
  chatType,
  claimId,
  replyTo,
  editorRef,
  onSend,
  onChange,
  onEditPrevious,
  onDismissPreview,
  onClearReply,
  suppressInitialAutoFocus = false,
}: ComposeBarProps) {
  const isMobile = useIsMobile()
  // After a send, claimId rotates and the editor remounts (key=claimId).
  // On the first mount we gate autoFocus on pointer-fine so mobile doesn't
  // pop the keyboard on page load. On every subsequent mount the keyboard is
  // already open, so we always re-focus.
  const [initialClaimId] = useState(claimId)
  const autoFocus =
    claimId !== initialClaimId || (!suppressInitialAutoFocus && window.matchMedia("(pointer: fine)").matches)
  const stickyRef = useRef<HTMLDivElement>(null)
  const barRef = useRef<HTMLDivElement>(null)
  const [barHeight, setBarHeight] = useState(0)
  const nativeShell = isNativeShell()

  useKeyboardAwareBottom(stickyRef, nativeShell)

  // The native fixed bar leaves normal flow, so reserve its resting height (plus
  // the safe-area clearance it sits at when closed) as an in-flow spacer — keeps
  // the last message clear of it and the viewport-fill math intact. The browser
  // sticky bar occupies its own flow space, so no spacer there.
  useEffect(() => {
    const el = barRef.current
    if (!el || !nativeShell) return
    const measure = () => {
      const safeArea =
        parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--safe-area-inset-bottom")) || 0
      setBarHeight(el.offsetHeight + safeArea)
    }
    const observer = new ResizeObserver(measure)
    observer.observe(el)
    measure()
    return () => observer.disconnect()
  }, [nativeShell])

  useEffect(() => {
    if (replyTo) editorRef.current?.focus()
  }, [replyTo, editorRef])

  const handleSend = useCallback(
    (content: string) => {
      onSend(content, claimId)
    },
    [onSend, claimId]
  )

  const handleSelectGif = useCallback(
    (gif: KlipyGif) => {
      editorRef.current?.insertImage(gif.content_url, gif.title)
    },
    [editorRef]
  )

  // The mobile wrapper supplies its own vertical padding (py-2) and the editor
  // sits beside ~36px button siblings, so we drop the desktop default's min-h-8
  // — otherwise the editor reserves a 32px content area and pins the single
  // line to its top, leaving dead space below the text.
  const editor = (
    <ChatComposerEditor
      key={claimId}
      ref={editorRef}
      autoFocus={autoFocus}
      onSend={handleSend}
      onChange={onChange}
      onEditPrevious={onEditPrevious}
      chatType={chatType}
      uploadUrl={uploadUrl}
      mentionableUsers={mentionableUsers}
      mentionsEnabled={mentionsEnabled}
      claimId={claimId}
      className="max-h-24 overflow-y-auto focus:outline-hidden text-sm"
    />
  )

  if (isMobile) {
    const mobileBar = (
      <div ref={barRef} className="bg-base-100/90 backdrop-blur-xl px-3 pt-2">
        {sendError && <div className="text-xs text-error mb-1 px-1">Message failed to send. Try again.</div>}
        {replyTo && (
          <div className="mb-2">
            <ComposeReplyPreview replyTo={replyTo} onClear={onClearReply} />
          </div>
        )}
        {composePreview && (
          <div className="mb-2">
            <LinkPreviewCard linkPreview={composePreview} onDismiss={onDismissPreview} />
          </div>
        )}
        <div className="flex items-center gap-2">
          <div className="flex-1 min-w-0 flex items-center gap-0.5 bg-base-200/80 border border-base-300 rounded-3xl py-1 pl-4 pr-1.5">
            <div className="flex-1 min-w-0">{editor}</div>
            {klipyApiKey && (
              <GifPicker
                klipyApiKey={klipyApiKey}
                onSelectGif={handleSelectGif}
                naked
                buttonClassName="w-8 h-8 text-base-content/50 active:bg-base-300"
              />
            )}
            <button
              type="button"
              className="flex items-center justify-center w-8 h-8 shrink-0 rounded-full text-base-content/50 active:bg-base-300 cursor-pointer"
              // Keep focus in the editor so tapping doesn't blur it and dismiss
              // the keyboard (WKWebView steals focus on button tap; Safari doesn't).
              onMouseDown={e => e.preventDefault()}
              onClick={() => editorRef.current?.triggerUpload()}
            >
              <span className="material-symbols-outlined text-xl">attach_file</span>
            </button>
          </div>
          <button
            type="button"
            className="flex items-center justify-center w-10 h-10 shrink-0 rounded-full bg-primary text-primary-content cursor-pointer disabled:opacity-50"
            disabled={sending}
            // Keep focus in the editor so the tap sends instead of blurring it
            // and dismissing the keyboard (WKWebView steals focus on button tap).
            onMouseDown={e => e.preventDefault()}
            onClick={() => editorRef.current?.send()}
          >
            <span className="material-symbols-outlined text-lg">arrow_upward</span>
          </button>
        </div>
        <div className="w-full bg-base-100/90 h-2" />
      </div>
    )

    // Native app: an explicit fixed bar (sticky doesn't re-stick on keyboard-open
    // in WKWebView), out of flow, so a spacer reserves its resting height.
    if (nativeShell) {
      return (
        <>
          <div aria-hidden style={{ height: barHeight }} />
          <div
            ref={stickyRef}
            data-chat-composer
            className="fixed inset-x-0 bottom-[calc(var(--mobile-nav-offset)+var(--safe-area-inset-bottom))] z-20"
          >
            {/* One opaque underlay behind the bar, tall enough for whichever
                strip needs covering: the keyboard occlusion when the lifted bar
                leaves it exposed (--keyboard-height), or the resting
                safe-area/home-indicator strip when the keyboard is closed so
                chat content doesn't scroll through it. */}
            <div
              aria-hidden
              className="pointer-events-none fixed bottom-0 inset-x-0 bg-base-100 h-[max(var(--keyboard-height,0px),calc(var(--mobile-nav-offset)+var(--safe-area-inset-bottom)))]"
            />
            {mobileBar}
          </div>
        </>
      )
    }

    // Browser: the original sticky bar (unchanged). The underlay covers the strip
    // revealed above the keyboard by the lift.
    return (
      <div ref={stickyRef} data-chat-composer className="sticky bottom-[var(--mobile-nav-offset)] z-20">
        <div
          aria-hidden
          className="pointer-events-none fixed bottom-0 inset-x-0 h-[var(--keyboard-height,0px)] bg-base-100"
        />
        {mobileBar}
      </div>
    )
  }

  return (
    <div ref={stickyRef} className="sticky bottom-0 z-20">
      <div className="max-w-composer mx-auto flex items-start gap-2 border border-neutral rounded-3xl px-2 py-1 bg-base-300">
        <div className="shrink-0 flex h-9 items-center">
          <Avatar picture={currentUser.picture} displayName={currentUser.displayName} size="large" />
        </div>
        <div className="relative flex-1 min-w-0">
          {sendError && <div className="text-xs text-error mb-1">Message failed to send. Try again.</div>}
          {replyTo && <ComposeReplyPreview replyTo={replyTo} onClear={onClearReply} />}
          {composePreview && (
            <div className="mb-1">
              <LinkPreviewCard linkPreview={composePreview} onDismiss={onDismissPreview} />
            </div>
          )}
          <div
            className={`grid ${klipyApiKey ? "grid-cols-[1fr_auto_auto_auto]" : "grid-cols-[1fr_auto_auto]"} gap-1 items-end`}
          >
            <div className="min-w-0 self-center">{editor}</div>
            {klipyApiKey && (
              <GifPicker klipyApiKey={klipyApiKey} onSelectGif={handleSelectGif} buttonClassName="btn-ghost" />
            )}
            <button
              type="button"
              className="btn btn-ghost btn-square"
              onClick={() => editorRef.current?.triggerUpload()}
            >
              <span className="material-symbols-outlined text-lg">attach_file</span>
            </button>
            <button
              type="button"
              className="btn btn-ghost btn-square"
              disabled={sending}
              onClick={() => editorRef.current?.send()}
            >
              <span className="material-symbols-outlined text-lg">arrow_upward</span>
            </button>
          </div>
        </div>
      </div>
      <div className="w-full h-4 bg-base-100" />
    </div>
  )
}
