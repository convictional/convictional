import { chainCommands } from "prosemirror-commands"
import { keymap } from "prosemirror-keymap"
import { Node } from "prosemirror-model"
import { goToNextCell, tableEditing } from "prosemirror-tables"
import { EditorView } from "prosemirror-view"

import { stripCommentMarks } from "./commentMark"
import { pmu, schema, TrailingSpaceBoldExtension, TrailingSpaceItalicExtension } from "./instance"
import { exitTableBackward, exitTableForward } from "./keymap"
import { serializeWithNormalization } from "./markNormalization"
import { TaskListItemView } from "./taskListItemView"

const parse = (content: string) => schema.nodeFromJSON(pmu.parse(content).toJSON())
const serialize = (doc: Node) => serializeWithNormalization(pmu, stripCommentMarks(doc))

// A blank editor is a single empty paragraph, which serializes to "<br />" (not ""),
// so a plain `.trim()` emptiness check reads it as non-empty. Send guards and disabled
// states use this to treat a document whose only content is empty blocks (<br />) and
// whitespace as empty, while real content (text, images, mentions) stays non-empty.
const isBlankMarkdown = (markdown: string): boolean => markdown.replace(/<br\s*\/?>/g, "").trim() === ""

// An attachment upload leaves an empty paragraph after the batch as a caret target, so the next
// keystroke starts a new block (which keeps images grouped for the chat gallery instead of merging
// typed text into their paragraph — see attachments.ts). Left unused, that block serializes to a
// stray "<br />" blank line, so every editor drops trailing empty paragraphs before serializing
// content for send/save. Keeps at least one child so a blank doc stays a single empty paragraph.
const withoutTrailingEmptyBlocks = (doc: Node): Node => {
  let content = doc.content
  while (content.childCount > 1) {
    const last = content.lastChild
    if (!last || last.type !== schema.nodes.paragraph || last.content.size > 0) break
    content = content.cut(0, content.size - last.nodeSize)
  }
  return doc.copy(content)
}

// Tab navigates cells; at the last/first cell it falls through to exit-at-boundary.
const tableKeymap = keymap({
  Tab: chainCommands(goToNextCell(1), exitTableForward),
  "Shift-Tab": chainCommands(goToNextCell(-1), exitTableBackward),
})

// Table plugins trail the unified plugins. `Editor.tsx` composes
// `getKeymap()` before `schemaPlugins`, so ArrowUp/Down boundary-exit
// commands get first crack before `tableEditing()` claims arrow keys
// for in-cell navigation.
const plugins = [pmu.inputRulesPlugin(), pmu.keymapPlugin(), tableKeymap, tableEditing()]
const nodeViews = {
  ...pmu.nodeViews(),
  task_list_item: (node: Node, view: EditorView, getPos: () => number | undefined) =>
    new TaskListItemView(node, view, getPos),
}

export {
  isBlankMarkdown,
  nodeViews,
  parse,
  plugins,
  schema,
  serialize,
  withoutTrailingEmptyBlocks,
  TrailingSpaceItalicExtension,
  TrailingSpaceBoldExtension,
}
