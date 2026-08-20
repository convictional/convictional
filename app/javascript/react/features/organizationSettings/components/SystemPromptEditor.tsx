import { forwardRef, useImperativeHandle } from "react"

import { Toolbar, type ToolbarTool } from "~/react/composites/editor/components/Toolbar"
import { Editor, EditorContent } from "~/react/composites/editor/Editor"
import { useViewRef } from "~/react/composites/editor/features/useViewRef"
import { parse, schema, serialize } from "~/richText/schema"

export interface SystemPromptEditorHandle {
  getContent: () => string
}

// The system prompt is stored as markdown, and the markdown schema has no underline
// mark (markdown can't represent it, so it wouldn't survive the round-trip), so the
// toolbar omits underline; the toolbar also names blockquote "quote". Hence this subset.
const TOOLS: readonly ToolbarTool[] = ["bold", "italic", "code", "quote", "bulletList", "orderedList"]

interface SystemPromptEditorProps {
  initialContent: string
  placeholder?: string
}

// A minimal document editor for the superuser system prompt: a limited toolbar
// over a markdown-native ProseMirror editor, no mentions/emoji/uploads. Content
// rides the wire as raw markdown and round-trips unchanged.
export const SystemPromptEditor = forwardRef<SystemPromptEditorHandle, SystemPromptEditorProps>(
  function SystemPromptEditor({ initialContent, placeholder }, ref) {
    const { viewRef, plugin: viewRefPlugin } = useViewRef()

    useImperativeHandle(
      ref,
      () => ({
        getContent: () => {
          const view = viewRef.current
          return view ? serialize(view.state.doc) : ""
        },
      }),
      [viewRef]
    )

    return (
      <Editor
        features={[{ plugins: [viewRefPlugin] }]}
        doc={initialContent ? parse(initialContent) : (schema.nodes.doc.createAndFill() ?? undefined)}
        placeholder={placeholder}
        className="markdown-content min-h-40 max-h-96 overflow-y-auto focus:outline-hidden text-sm p-3"
        autoFocus={false}
      >
        <div className="rounded-lg border border-neutral overflow-hidden bg-base-100">
          <div className="border-b border-neutral px-2 py-1">
            <Toolbar hasKlipy={false} klipyApiKey={null} tools={TOOLS} />
          </div>
          <EditorContent />
        </div>
      </Editor>
    )
  }
)
