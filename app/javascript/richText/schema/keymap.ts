import { chainCommands, newlineInCode, splitBlock } from "prosemirror-commands"
import { redo, undo } from "prosemirror-history"
import { keymap as keymapPlugin } from "prosemirror-keymap"
import { Fragment, Node, NodeType, ResolvedPos } from "prosemirror-model"
import { liftListItem, sinkListItem, splitListItem, wrapInList } from "prosemirror-schema-list"
import { Command, EditorState, Plugin, Selection, Transaction } from "prosemirror-state"
import { EditorView } from "prosemirror-view"

import { schema } from "./instance"

function isListContainer(type: NodeType): boolean {
  return type === schema.nodes.bullet_list || type === schema.nodes.ordered_list
}

function isListItem(type: NodeType): boolean {
  return type === schema.nodes.regular_list_item || type === schema.nodes.task_list_item
}

// Walk up from a resolved position to the nearest enclosing list container,
// returning its depth (0 if the position is not inside a list).
function enclosingListDepth($pos: ResolvedPos): number {
  let depth = $pos.depth
  while (depth > 0 && !isListContainer($pos.node(depth).type)) {
    depth--
  }
  return depth
}

function listAttrsFor(listType: NodeType, sourceNode: Node): Record<string, unknown> {
  const attrs: Record<string, unknown> = { spread: sourceNode.attrs.spread ?? false }
  if (listType === schema.nodes.ordered_list) {
    attrs.start = 1
  }
  return attrs
}

// If the cursor is at the end of the last paragraph in a block, exit the block
// by navigating to the next block or creating a new one
export function exitBlockQuoteForward(state: EditorState, dispatch?: (tr: Transaction) => void): boolean {
  const { $from, $to } = state.selection
  if (!$from.sameParent($to) || $from.parentOffset !== $from.parent.content.size) {
    return false
  }

  if ($from.parent.type !== schema.nodes.paragraph) {
    return false
  }

  const grandparent = $from.node(-1)
  if (grandparent.type !== schema.nodes.blockquote) {
    return false
  }

  // Parent should be the last child of the grandparent
  const grandparentIndex = $from.index(-1)
  if (grandparentIndex !== grandparent.childCount - 1) {
    return false
  }

  if (dispatch) {
    const pos = $from.after(-1)
    const tr = state.tr
    // Insert a paragraph if we are at the end of element containing the blockquote
    if (pos === $from.end(-2)) {
      tr.insert(pos, schema.nodes.paragraph.create())
    }
    tr.setSelection(Selection.near(tr.doc.resolve(pos + 1)))
    dispatch(tr.scrollIntoView())
  }

  return true
}

// If the cursor is at the beginning of the first paragraph in a block, exit the block
// by navigating to the previous block or creating a new one
export function exitBlockQuoteBackward(state: EditorState, dispatch?: (tr: Transaction) => void): boolean {
  const { $from, $to } = state.selection
  if (!$from.sameParent($to) || $from.parentOffset !== 0) {
    return false
  }

  if ($from.parent.type !== schema.nodes.paragraph) {
    return false
  }

  const grandparent = $from.node(-1)
  if (grandparent.type !== schema.nodes.blockquote) {
    return false
  }

  // Parent should be the first child of the grandparent
  const grandparentIndex = $from.index(-1)
  if (grandparentIndex !== 0) {
    return false
  }

  // Create and select a new paragraph before the blockquote
  if (dispatch) {
    const pos = $from.before(-1)
    const tr = state.tr
    if (pos === $from.start(-2)) {
      tr.insert(pos, schema.nodes.paragraph.create())
    }
    tr.setSelection(Selection.near(tr.doc.resolve(pos), -1))
    dispatch(tr.scrollIntoView())
  }

  return true
}

// If the cursor is at the end of a code block, exit the code block
// by navigating to the next block or creating a new one
export function exitCodeBlockForward(state: EditorState, dispatch?: (tr: Transaction) => void): boolean {
  const { $from, $to } = state.selection
  if (!$from.sameParent($to) || $from.parentOffset !== $from.parent.content.size) {
    return false
  }

  if ($from.parent.type !== schema.nodes.code_block) {
    return false
  }

  // Create and select a new paragraph after the code block
  if (dispatch) {
    const pos = $from.after()
    const tr = state.tr
    if (pos === $from.end(-1)) {
      tr.insert(pos, schema.nodes.paragraph.create())
    }
    tr.setSelection(Selection.near(tr.doc.resolve(pos + 1)))
    dispatch(tr.scrollIntoView())
  }

  return true
}

// If the cursor is at the beginning of a code block, exit the code block
// by navigating to the previous block or creating a new one
export function exitCodeBlockBackward(state: EditorState, dispatch?: (tr: Transaction) => void): boolean {
  const { $from, $to } = state.selection
  if (!$from.sameParent($to) || $from.parentOffset !== 0) {
    return false
  }

  if ($from.parent.type !== schema.nodes.code_block) {
    return false
  }

  // Create and select a new paragraph before the code block
  if (dispatch) {
    const pos = $from.before()
    const tr = state.tr
    if (pos === $from.start(-1)) {
      tr.insert(pos, schema.nodes.paragraph.create())
    }
    tr.setSelection(Selection.near(tr.doc.resolve(pos), -1))
    dispatch(tr.scrollIntoView())
  }

  return true
}

// If the cursor is at the end of the last cell in a table, exit by creating
// a paragraph after the table. Returns false for interior positions so
// tableEditing()'s cell navigation still works.
export function exitTableForward(state: EditorState, dispatch?: (tr: Transaction) => void): boolean {
  const { $from, $to } = state.selection
  if (!$from.sameParent($to) || $from.parentOffset !== $from.parent.content.size) {
    return false
  }

  // Walk up to find a table ancestor. Cells are nested: table > row > cell > paragraph
  let tableDepth = -1
  for (let d = $from.depth; d > 0; d--) {
    if ($from.node(d).type === schema.nodes.table) {
      tableDepth = d
      break
    }
  }
  if (tableDepth === -1) return false

  const table = $from.node(tableDepth)
  const rowIndex = $from.index(tableDepth)
  const row = table.child(rowIndex)
  const cellIndex = $from.index(tableDepth + 1)
  const cell = row.child(cellIndex)
  const blockIndex = $from.index(tableDepth + 2)

  // Only exit at the last block of the last cell of the last row
  if (rowIndex !== table.childCount - 1 || cellIndex !== row.childCount - 1 || blockIndex !== cell.childCount - 1) {
    return false
  }

  if (dispatch) {
    const pos = $from.after(tableDepth)
    const tr = state.tr
    if (pos === $from.end(tableDepth - 1)) {
      tr.insert(pos, schema.nodes.paragraph.create())
    }
    tr.setSelection(Selection.near(tr.doc.resolve(pos + 1)))
    dispatch(tr.scrollIntoView())
  }

  return true
}

// If the cursor is at the beginning of the first cell in a table, exit by
// creating a paragraph before the table.
export function exitTableBackward(state: EditorState, dispatch?: (tr: Transaction) => void): boolean {
  const { $from, $to } = state.selection
  if (!$from.sameParent($to) || $from.parentOffset !== 0) {
    return false
  }

  let tableDepth = -1
  for (let d = $from.depth; d > 0; d--) {
    if ($from.node(d).type === schema.nodes.table) {
      tableDepth = d
      break
    }
  }
  if (tableDepth === -1) return false

  const rowIndex = $from.index(tableDepth)
  const cellIndex = $from.index(tableDepth + 1)
  const blockIndex = $from.index(tableDepth + 2)

  // Only exit at the first block of the first cell of the first row
  if (rowIndex !== 0 || cellIndex !== 0 || blockIndex !== 0) {
    return false
  }

  if (dispatch) {
    const pos = $from.before(tableDepth)
    const tr = state.tr
    if (pos === $from.start(tableDepth - 1)) {
      tr.insert(pos, schema.nodes.paragraph.create())
    }
    tr.setSelection(Selection.near(tr.doc.resolve(pos), -1))
    dispatch(tr.scrollIntoView())
  }

  return true
}

// If the cursor is at the end of the last paragraph in the last task item,
// exit the task list by navigating to the next block or creating a new one.
export function exitTaskListForward(state: EditorState, dispatch?: (tr: Transaction) => void): boolean {
  const { $from, $to } = state.selection
  if (!$from.sameParent($to) || $from.parentOffset !== $from.parent.content.size) {
    return false
  }

  if ($from.parent.type !== schema.nodes.paragraph) {
    return false
  }

  const taskListItem = $from.node(-1)
  if (taskListItem.type !== schema.nodes.task_list_item) {
    return false
  }

  const bulletList = $from.node(-2)
  if (bulletList.type !== schema.nodes.bullet_list) {
    return false
  }

  // Cursor must be in the last item of the list
  if ($from.index(-2) !== bulletList.childCount - 1) {
    return false
  }

  // Cursor must be in the last paragraph of that item
  if ($from.index(-1) !== taskListItem.childCount - 1) {
    return false
  }

  if (dispatch) {
    const pos = $from.after(-2)
    const tr = state.tr
    if (pos === $from.end(-3)) {
      tr.insert(pos, schema.nodes.paragraph.create())
    }
    tr.setSelection(Selection.near(tr.doc.resolve(pos + 1)))
    dispatch(tr.scrollIntoView())
  }

  return true
}

// If the cursor is at the beginning of the first paragraph in the first task item,
// exit the task list by navigating to the previous block or creating a new one.
export function exitTaskListBackward(state: EditorState, dispatch?: (tr: Transaction) => void): boolean {
  const { $from, $to } = state.selection
  if (!$from.sameParent($to) || $from.parentOffset !== 0) {
    return false
  }

  if ($from.parent.type !== schema.nodes.paragraph) {
    return false
  }

  const taskListItem = $from.node(-1)
  if (taskListItem.type !== schema.nodes.task_list_item) {
    return false
  }

  const bulletList = $from.node(-2)
  if (bulletList.type !== schema.nodes.bullet_list) {
    return false
  }

  // Cursor must be in the first item of the list
  if ($from.index(-2) !== 0) {
    return false
  }

  // Cursor must be in the first paragraph of that item
  if ($from.index(-1) !== 0) {
    return false
  }

  if (dispatch) {
    const pos = $from.before(-2)
    const tr = state.tr
    if (pos === $from.start(-3)) {
      tr.insert(pos, schema.nodes.paragraph.create())
    }
    tr.setSelection(Selection.near(tr.doc.resolve(pos), -1))
    dispatch(tr.scrollIntoView())
  }

  return true
}

// When the cursor is at position 0 of the first paragraph in a task_list_item,
// convert the task item to a plain paragraph and remove the bullet_list wrapper
// if it was the only item.
export function convertTaskItemToParaBackspace(state: EditorState, dispatch?: (tr: Transaction) => void): boolean {
  const { $from, $to } = state.selection
  if (!$from.sameParent($to) || $from.parentOffset !== 0 || !state.selection.empty) {
    return false
  }

  if ($from.parent.type !== schema.nodes.paragraph) {
    return false
  }

  const taskListItem = $from.node(-1)
  if (taskListItem.type !== schema.nodes.task_list_item) {
    return false
  }

  // Only fire at the start of the first paragraph child of the task item
  if ($from.index(-1) !== 0) {
    return false
  }

  // Only handle the first item — for non-first items, default Backspace (merge) is correct
  if ($from.index(-2) !== 0) {
    return false
  }

  if (dispatch) {
    const tr = state.tr
    const bulletList = $from.node(-2)
    const bulletListStart = $from.before(-2)
    const bulletListEnd = bulletListStart + bulletList.nodeSize
    if (bulletList.childCount === 1) {
      // Only item: replace the whole bullet_list with the paragraph content
      tr.replaceWith(bulletListStart, bulletListEnd, taskListItem.content)
    } else {
      // Extract first item's content as paragraph(s), keep remaining items in a new bullet_list
      const remainingItems: Node[] = []
      bulletList.forEach((child, _offset, index) => {
        if (index > 0) remainingItems.push(child)
      })
      const newList = schema.nodes.bullet_list.create(bulletList.attrs, Fragment.from(remainingItems))
      tr.replaceWith(bulletListStart, bulletListEnd, taskListItem.content.append(Fragment.from(newList)))
    }
    tr.setSelection(Selection.near(tr.doc.resolve(bulletListStart + 1)))
    dispatch(tr)
  }

  return true
}

// When the cursor is at position 0 of the first paragraph in a regular_list_item
// (bullet or ordered list), lift the item out of its list as a plain paragraph.
// Mirrors convertTaskItemToParaBackspace but handles bullet_list and ordered_list.
// The replacement list preserves the original list type and attributes.
export function convertRegularItemToParaBackspace(state: EditorState, dispatch?: (tr: Transaction) => void): boolean {
  const { $from, $to } = state.selection
  if (!$from.sameParent($to) || $from.parentOffset !== 0 || !state.selection.empty) {
    return false
  }

  if ($from.parent.type !== schema.nodes.paragraph) {
    return false
  }

  const listItem = $from.node(-1)
  if (listItem.type !== schema.nodes.regular_list_item) {
    return false
  }

  // Only fire at the start of the first paragraph child of the list item
  if ($from.index(-1) !== 0) {
    return false
  }

  // Only handle the first item — for non-first items, default Backspace (merge) is correct
  if ($from.index(-2) !== 0) {
    return false
  }

  // Only handle top-level list items — nested items (inside another list item) fall through.
  // For a nested item, the container of the list ($from.node(-3)) is a list item, not a doc or block.
  const enclosingContainer = $from.node(-3)
  if (
    enclosingContainer.type === schema.nodes.regular_list_item ||
    enclosingContainer.type === schema.nodes.task_list_item
  ) {
    return false
  }

  if (dispatch) {
    const tr = state.tr
    const parentList = $from.node(-2)
    const parentListStart = $from.before(-2)
    const parentListEnd = parentListStart + parentList.nodeSize
    if (parentList.childCount === 1) {
      // Only item: replace the whole list with the item's paragraph content
      tr.replaceWith(parentListStart, parentListEnd, listItem.content)
    } else {
      // Extract first item's content as paragraph(s), keep remaining items in a new list of the same type
      const remainingItems: Node[] = []
      parentList.forEach((child, _offset, index) => {
        if (index > 0) remainingItems.push(child)
      })
      const newList = parentList.type.create(parentList.attrs, Fragment.from(remainingItems))
      tr.replaceWith(parentListStart, parentListEnd, listItem.content.append(Fragment.from(newList)))
    }
    tr.setSelection(Selection.near(tr.doc.resolve(parentListStart + 1)))
    dispatch(tr.scrollIntoView())
  }

  return true
}

export function toggleList(listType: NodeType, itemType: NodeType): Command {
  return (state: EditorState, dispatch?: (tr: Transaction) => void, view?: EditorView): boolean => {
    const { from, to } = state.selection
    const itemsInSelection: Array<{ pos: number }> = []
    state.doc.nodesBetween(from, to, (node, pos) => {
      if (node.type === itemType) {
        itemsInSelection.push({ pos })
        return false
      }
    })

    if (itemsInSelection.length > 0) {
      const $pos = state.doc.resolve(itemsInSelection[0].pos)
      const listDepth = enclosingListDepth($pos)
      const enclosingList = $pos.node(listDepth)

      if (enclosingList.type === listType) {
        if (!dispatch) return true

        const tr = state.tr
        const listFrom = $pos.before(listDepth)
        const listTo = $pos.after(listDepth)
        const selectedPosSet = new Set(itemsInSelection.map(({ pos }) => pos))

        const paragraphsToInsert: Node[] = []
        const prefixItems: Node[] = []
        const suffixItems: Node[] = []
        let seenSelected = false

        enclosingList.forEach((child, offset) => {
          const childAbsPos = listFrom + 1 + offset
          if (child.type === itemType && selectedPosSet.has(childAbsPos)) {
            seenSelected = true
            child.content.forEach(p => paragraphsToInsert.push(p))
          } else if (!seenSelected) {
            prefixItems.push(child)
          } else {
            suffixItems.push(child)
          }
        })

        const replacement: Node[] = []
        if (prefixItems.length > 0) {
          replacement.push(enclosingList.type.create(enclosingList.attrs, Fragment.from(prefixItems)))
        }
        replacement.push(...paragraphsToInsert)
        if (suffixItems.length > 0) {
          replacement.push(enclosingList.type.create(enclosingList.attrs, Fragment.from(suffixItems)))
        }

        tr.replaceWith(listFrom, listTo, Fragment.from(replacement))
        dispatch(tr.scrollIntoView())
        return true
      }
    }

    const { $from } = state.selection
    const listDepth = enclosingListDepth($from)
    if (listDepth > 0) {
      if (!dispatch) return true

      const listNode = $from.node(listDepth)
      const listStart = $from.before(listDepth)
      const tr = state.tr
      if (listNode.type !== listType) {
        tr.setNodeMarkup(listStart, listType, listAttrsFor(listType, listNode))
      }
      listNode.forEach((item, offset) => {
        if (isListItem(item.type) && item.type !== itemType) {
          // task→regular intentionally drops the checkbox state
          tr.setNodeMarkup(
            listStart + 1 + offset,
            itemType,
            itemType === schema.nodes.task_list_item ? { checked: false } : null
          )
        }
      })
      if (tr.steps.length > 0) {
        dispatch(tr.scrollIntoView())
      }
      return true
    }

    if (!dispatch) return wrapInList(listType)(state, undefined, view)

    let capturedTr: Transaction | undefined
    wrapInList(listType)(
      state,
      t => {
        capturedTr = t
      },
      view
    )
    if (!capturedTr) return false
    const tr = capturedTr

    if (itemType === schema.nodes.task_list_item) {
      const mappedFrom = tr.mapping.map(state.selection.from)
      const mappedTo = tr.mapping.map(state.selection.to)
      tr.doc.nodesBetween(mappedFrom, mappedTo, (node, pos) => {
        if (node.type === schema.nodes.regular_list_item) {
          tr.setNodeMarkup(pos, itemType, { checked: false })
        }
      })
    }

    dispatch(tr.scrollIntoView())
    return true
  }
}

export const toggleTaskList: Command = toggleList(schema.nodes.bullet_list, schema.nodes.task_list_item)

// Shift+Enter starts a new block everywhere — chat, post body, and post comments.
// Lists and code blocks get their contextual split/newline via getEnterCommand;
// everything else splits the paragraph. Bound in getKeymap ahead of
// prosemirror-remark's Shift-Enter → hard_break so all composers share this one
// behavior instead of drifting. Splitting into a fresh block also sidesteps the
// Safari bug where the caret after a trailing <br> stays unpainted until the next
// keystroke.
export function getShiftEnterCommand(): Command {
  return chainCommands(getEnterCommand(), splitBlock)
}

export function getEnterCommand(): Command {
  const taskListItem = schema.nodes.task_list_item
  const regularListItem = schema.nodes.regular_list_item
  return chainCommands(
    newlineInCode,
    splitListItem(taskListItem, { checked: false }),
    liftListItem(taskListItem),
    splitListItem(regularListItem),
    liftListItem(regularListItem)
  )
}

// Tab inserts a literal \t only inside surfaces that preserve authored whitespace:
// code_block (always pre) and blockquote (opted into pre-wrap in markdown-content.css).
// Everywhere else — plain paragraphs, headings, lists already handled upstream, table
// cells handled by tableKeymap — we return false so the keymap plugin doesn't
// preventDefault and the browser's native Tab moves focus to the next UI element.
function inTabPreservingAncestor($pos: ResolvedPos): boolean {
  for (let d = $pos.depth; d >= 0; d--) {
    const type = $pos.node(d).type
    if (type === schema.nodes.code_block || type === schema.nodes.blockquote) return true
  }
  return false
}

export function insertTabIndent(state: EditorState, dispatch?: (tr: Transaction) => void): boolean {
  const { $from, $to } = state.selection
  if (!$from.sameParent($to)) return false
  if (!inTabPreservingAncestor($from)) return false
  if (dispatch) dispatch(state.tr.insertText("\t").scrollIntoView())
  return true
}

export function removeTabOutdent(state: EditorState, dispatch?: (tr: Transaction) => void): boolean {
  const { $from } = state.selection
  if (!state.selection.empty) return false
  if (!inTabPreservingAncestor($from)) return false
  if ($from.parentOffset === 0) return false
  const before = $from.parent.textBetween($from.parentOffset - 1, $from.parentOffset)
  if (before !== "\t") return false
  if (dispatch) dispatch(state.tr.delete($from.pos - 1, $from.pos).scrollIntoView())
  return true
}

export function getTabCommand(): Command {
  const taskListItem = schema.nodes.task_list_item
  const regularListItem = schema.nodes.regular_list_item
  return chainCommands(sinkListItem(taskListItem), sinkListItem(regularListItem), insertTabIndent)
}

export function getShiftTabCommand(): Command {
  const taskListItem = schema.nodes.task_list_item
  const regularListItem = schema.nodes.regular_list_item
  return chainCommands(liftListItem(taskListItem), liftListItem(regularListItem), removeTabOutdent)
}

export function getKeymap(): Plugin {
  const blockKey = () => true

  return keymapPlugin({
    "Mod-Enter": blockKey,
    "Mod-`": blockKey,
    Escape(_state: EditorState, _dispatch?: (tr: Transaction) => void, view?: EditorView) {
      if (view) {
        ;(view.dom as HTMLElement).blur()
      }
      return true
    },
    Enter: getEnterCommand(),
    "Shift-Enter": getShiftEnterCommand(),
    Tab: getTabCommand(),
    "Shift-Tab": getShiftTabCommand(),
    Backspace: chainCommands(convertTaskItemToParaBackspace, convertRegularItemToParaBackspace),
    ArrowUp: chainCommands(exitTaskListBackward, exitBlockQuoteBackward, exitCodeBlockBackward, exitTableBackward),
    ArrowDown: chainCommands(exitTaskListForward, exitBlockQuoteForward, exitCodeBlockForward, exitTableForward),
    "Mod-z": undo,
    // Redo needs all three: Shift-Mod-z is the Mac convention, Mod-y the
    // Windows/Linux one. The capital-letter "Mod-Z" form matched Cmd+Shift+z on
    // mac but silently failed to match Ctrl+Shift+z on other platforms, so redo
    // was dead everywhere except mac.
    "Shift-Mod-z": redo,
    "Mod-y": redo,
  })
}
