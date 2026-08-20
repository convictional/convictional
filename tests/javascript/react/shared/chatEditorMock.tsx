import { forwardRef, useImperativeHandle, useRef } from "react"

// ChatComposerEditor is ProseMirror-backed and doesn't run in jsdom. This stub
// stands in for it: it renders a real <textarea> (so placeholder / display-value
// queries and typing keep working) and exposes the same imperative handle the
// real editor does, with send() emitting the current value as "markdown".
//
// Use in a test with:
//   vi.mock("~/react/composites/chat/ChatComposerEditor", () => import("../../shared/chatEditorMock"))
//   import { editorCapture } from "../../shared/chatEditorMock"
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const editorCapture = { lastProps: null as any }

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const ChatComposerEditor = forwardRef(function ChatComposerEditor(props: any, ref) {
  editorCapture.lastProps = props
  const valueRef = useRef<string>(props.initialContent ?? "")
  useImperativeHandle(ref, () => ({
    send: () => props.onSend(valueRef.current),
    focus: () => {},
    triggerUpload: () => {},
    uploadFiles: () => {},
    insertImage: () => {},
    getReferencedAttachmentIds: () => [],
  }))
  return (
    <textarea
      data-testid="chat-editor"
      placeholder={props.placeholder}
      defaultValue={props.initialContent}
      onChange={e => {
        valueRef.current = e.target.value
        props.onChange?.(e.target.value)
      }}
    />
  )
})
