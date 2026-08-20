import { test, expect } from 'vitest';
import { builders } from 'prosemirror-test-builder';
import { Node } from 'prosemirror-model';
import { TextSelection, Transaction } from 'prosemirror-state';
import { schema } from '../../../../app/javascript/richText/schema';
import {
  exitBlockQuoteForward,
  exitBlockQuoteBackward,
  exitCodeBlockForward,
  exitCodeBlockBackward,
  exitTableForward,
  exitTableBackward,
  exitTaskListForward,
  exitTaskListBackward,
  convertTaskItemToParaBackspace,
  convertRegularItemToParaBackspace,
  getEnterCommand,
  getShiftEnterCommand,
  getTabCommand,
  getShiftTabCommand,
  insertTabIndent,
  removeTabOutdent,
} from '../../../../app/javascript/richText/schema/keymap';
import { assertCommand, assertNoOp, mkState } from './testHelpers';

const { doc, paragraph, heading, blockquote, code_block, table, table_row, table_cell, table_header, bullet_list, ordered_list, task_list_item, regular_list_item } = builders(schema);

function runEnter(docIn: Node, expected: Node): Transaction {
  let resultTr: Transaction | undefined
  const handled = getEnterCommand()(mkState(docIn), tr => { resultTr = tr })
  expect(handled).toBe(true)
  expect(resultTr).toBeDefined()
  expect(resultTr!.doc.eq(expected)).toBe(true)
  expect(resultTr!.selection).toBeInstanceOf(TextSelection)
  expect(resultTr!.selection.empty).toBe(true)
  return resultTr!
}

test('exitBlockQuoteForward', () => {
  // Just a blockquote
  assertCommand(
    exitBlockQuoteForward,
    doc(
      blockquote(paragraph('foo<a>'))
    ),
    doc(
      blockquote(paragraph('foo')),
      paragraph('<a>')
    )
  )

  // Nested blockquotes
  assertCommand(
    exitBlockQuoteForward,
    doc(
      blockquote(
        paragraph('food'),
        blockquote(
          paragraph('bar<a>')
        )
      )
    ),
    doc(
      blockquote(
        paragraph('food'),
        blockquote(
          paragraph('bar')
        ),
        paragraph('<a>')
      )
    )
  )
})

test('exitBlockQuoteBackward', () => {
  // Just a blockquote
  assertCommand(
    exitBlockQuoteBackward,
    doc(
      blockquote(paragraph('<a>foo'))
    ),
    doc(
      paragraph(''),
      blockquote(paragraph('foo'))
    )
  )

  // Nested blockquotes
  assertCommand(
    exitBlockQuoteBackward,
    doc(
      blockquote(
        blockquote(
          paragraph('<a>bar')
        ),
        paragraph('food')
      )
    ),
    doc(
      blockquote(
        paragraph('<a>'),
        blockquote(
          paragraph('bar')
        ),
        paragraph('food')
      )
    )
  )
})

test('exitCodeBlockForward', () => {
  assertCommand(
    exitCodeBlockForward,
    doc(
      code_block('foo<a>')
    ),
    doc(
      code_block('foo'),
      paragraph('<a>')
    )
  )
})

test('exitCodeBlockBackward', () => {
  assertCommand(
    exitCodeBlockBackward,
    doc(
      code_block('<a>foo')
    ),
    doc(
      paragraph(''),
      code_block('foo')
    )
  )
})

test('exitTableForward inserts a trailing paragraph when table is the last block', () => {
  assertCommand(
    exitTableForward,
    doc(
      table(
        table_row(table_header(paragraph('A')), table_header(paragraph('B'))),
        table_row(table_cell(paragraph('1')), table_cell(paragraph('2<a>')))
      )
    ),
    doc(
      table(
        table_row(table_header(paragraph('A')), table_header(paragraph('B'))),
        table_row(table_cell(paragraph('1')), table_cell(paragraph('2')))
      ),
      paragraph('<a>')
    )
  )
})

test('exitTableForward moves into an existing sibling without inserting', () => {
  assertCommand(
    exitTableForward,
    doc(
      table(
        table_row(table_header(paragraph('A'))),
        table_row(table_cell(paragraph('1<a>')))
      ),
      paragraph('after')
    ),
    doc(
      table(
        table_row(table_header(paragraph('A'))),
        table_row(table_cell(paragraph('1')))
      ),
      paragraph('<a>after')
    )
  )
})

test('exitTableForward is a no-op at interior positions', () => {
  // First row, not last row
  assertNoOp(
    exitTableForward,
    doc(
      table(
        table_row(table_header(paragraph('A<a>'))),
        table_row(table_cell(paragraph('1')))
      )
    )
  )

  // Last row, but not last cell
  assertNoOp(
    exitTableForward,
    doc(
      table(
        table_row(table_header(paragraph('A')), table_header(paragraph('B'))),
        table_row(table_cell(paragraph('1<a>')), table_cell(paragraph('2')))
      )
    )
  )

  // Last cell, but cursor not at end of text
  assertNoOp(
    exitTableForward,
    doc(
      table(
        table_row(table_header(paragraph('A'))),
        table_row(table_cell(paragraph('<a>12')))
      )
    )
  )

  // Outside any table
  assertNoOp(exitTableForward, doc(paragraph('plain<a>')))
})

test('exitTableBackward inserts a leading paragraph when table is the first block', () => {
  assertCommand(
    exitTableBackward,
    doc(
      table(
        table_row(table_header(paragraph('<a>A')), table_header(paragraph('B'))),
        table_row(table_cell(paragraph('1')), table_cell(paragraph('2')))
      )
    ),
    doc(
      paragraph('<a>'),
      table(
        table_row(table_header(paragraph('A')), table_header(paragraph('B'))),
        table_row(table_cell(paragraph('1')), table_cell(paragraph('2')))
      )
    )
  )
})

test('exitTableBackward moves into an existing sibling without inserting', () => {
  assertCommand(
    exitTableBackward,
    doc(
      paragraph('before'),
      table(
        table_row(table_header(paragraph('<a>A'))),
        table_row(table_cell(paragraph('1')))
      )
    ),
    doc(
      paragraph('before<a>'),
      table(
        table_row(table_header(paragraph('A'))),
        table_row(table_cell(paragraph('1')))
      )
    )
  )
})

test('exitTableBackward is a no-op at interior positions', () => {
  // Not first row
  assertNoOp(
    exitTableBackward,
    doc(
      table(
        table_row(table_header(paragraph('A'))),
        table_row(table_cell(paragraph('<a>1')))
      )
    )
  )

  // First row, not first cell
  assertNoOp(
    exitTableBackward,
    doc(
      table(
        table_row(table_header(paragraph('A')), table_header(paragraph('<a>B'))),
        table_row(table_cell(paragraph('1')), table_cell(paragraph('2')))
      )
    )
  )

  // First cell, but cursor not at start of text
  assertNoOp(
    exitTableBackward,
    doc(
      table(
        table_row(table_header(paragraph('A<a>B'))),
        table_row(table_cell(paragraph('1')))
      )
    )
  )

  // Outside any table
  assertNoOp(exitTableBackward, doc(paragraph('<a>plain')))
})

// ─── Task list exit commands ──────────────────────────────────────────────────

test('exitTaskListForward inserts a trailing paragraph when task list is the last block', () => {
  assertCommand(
    exitTaskListForward,
    doc(
      bullet_list(
        task_list_item({ checked: false }, paragraph('item<a>'))
      )
    ),
    doc(
      bullet_list(
        task_list_item({ checked: false }, paragraph('item'))
      ),
      paragraph('<a>')
    )
  )
})

test('exitTaskListForward moves into an existing sibling without inserting', () => {
  assertCommand(
    exitTaskListForward,
    doc(
      bullet_list(
        task_list_item({ checked: false }, paragraph('item<a>'))
      ),
      paragraph('after')
    ),
    doc(
      bullet_list(
        task_list_item({ checked: false }, paragraph('item'))
      ),
      paragraph('<a>after')
    )
  )
})

test('exitTaskListForward is a no-op at interior positions', () => {
  // Cursor is in an interior item (not the last item)
  assertNoOp(
    exitTaskListForward,
    doc(
      bullet_list(
        task_list_item({ checked: false }, paragraph('first<a>')),
        task_list_item({ checked: false }, paragraph('second'))
      )
    )
  )

  // Cursor is in the last item but not at end of text
  assertNoOp(
    exitTaskListForward,
    doc(
      bullet_list(
        task_list_item({ checked: false }, paragraph('<a>item'))
      )
    )
  )

  // Cursor is at end of first paragraph in a multi-paragraph task item
  assertNoOp(
    exitTaskListForward,
    doc(
      bullet_list(
        task_list_item({ checked: false }, paragraph('first para<a>'), paragraph('second para'))
      )
    )
  )

  // Cursor is outside any task list
  assertNoOp(exitTaskListForward, doc(paragraph('plain<a>')))
})

test('exitTaskListBackward inserts a leading paragraph when task list is the first block', () => {
  assertCommand(
    exitTaskListBackward,
    doc(
      bullet_list(
        task_list_item({ checked: false }, paragraph('<a>item'))
      )
    ),
    doc(
      paragraph('<a>'),
      bullet_list(
        task_list_item({ checked: false }, paragraph('item'))
      )
    )
  )
})

test('exitTaskListBackward moves into an existing sibling without inserting', () => {
  assertCommand(
    exitTaskListBackward,
    doc(
      paragraph('before'),
      bullet_list(
        task_list_item({ checked: false }, paragraph('<a>item'))
      )
    ),
    doc(
      paragraph('before<a>'),
      bullet_list(
        task_list_item({ checked: false }, paragraph('item'))
      )
    )
  )
})

test('exitTaskListBackward is a no-op at interior positions', () => {
  // Cursor is in an interior item (not the first item)
  assertNoOp(
    exitTaskListBackward,
    doc(
      bullet_list(
        task_list_item({ checked: false }, paragraph('first')),
        task_list_item({ checked: false }, paragraph('<a>second'))
      )
    )
  )

  // Cursor is in the first item but not at start of text
  assertNoOp(
    exitTaskListBackward,
    doc(
      bullet_list(
        task_list_item({ checked: false }, paragraph('it<a>em'))
      )
    )
  )

  // Cursor is at start of second paragraph in a multi-paragraph task item
  assertNoOp(
    exitTaskListBackward,
    doc(
      bullet_list(
        task_list_item({ checked: false }, paragraph('first para'), paragraph('<a>second para'))
      )
    )
  )

  // Cursor is outside any task list
  assertNoOp(exitTaskListBackward, doc(paragraph('<a>plain')))
})

// ─── Backspace handler: convert task item to paragraph ───────────────────────

test('convertTaskItemToParaBackspace converts a task item to a paragraph at start of item', () => {
  // Only item in the list — list wrapper should be removed too
  assertCommand(
    convertTaskItemToParaBackspace,
    doc(
      bullet_list(
        task_list_item({ checked: false }, paragraph('<a>task text'))
      )
    ),
    doc(
      paragraph('<a>task text')
    )
  )
})

test('convertTaskItemToParaBackspace is a no-op when cursor is mid-text', () => {
  assertNoOp(
    convertTaskItemToParaBackspace,
    doc(
      bullet_list(
        task_list_item({ checked: false }, paragraph('task<a> text'))
      )
    )
  )
})

test('convertTaskItemToParaBackspace is a no-op when cursor is in a plain paragraph', () => {
  assertNoOp(
    convertTaskItemToParaBackspace,
    doc(paragraph('<a>plain text'))
  )
})

test('convertTaskItemToParaBackspace on first item of multi-item list extracts paragraph and keeps rest', () => {
  assertCommand(
    convertTaskItemToParaBackspace,
    doc(
      bullet_list(
        task_list_item({ checked: false }, paragraph('<a>first')),
        task_list_item({ checked: false }, paragraph('second'))
      )
    ),
    doc(
      paragraph('<a>first'),
      bullet_list(
        task_list_item({ checked: false }, paragraph('second'))
      )
    )
  )
})

test('convertTaskItemToParaBackspace is a no-op when text is selected starting at offset 0', () => {
  assertNoOp(
    convertTaskItemToParaBackspace,
    doc(
      bullet_list(
        task_list_item({ checked: false }, paragraph('<a>task text<b>'))
      )
    )
  )
})

test('convertTaskItemToParaBackspace is a no-op at the start of a non-first item', () => {
  assertNoOp(
    convertTaskItemToParaBackspace,
    doc(
      bullet_list(
        task_list_item({ checked: false }, paragraph('first')),
        task_list_item({ checked: false }, paragraph('<a>second'))
      )
    )
  )
})

// ─── Backspace handler: convert regular list item to paragraph ───────────────

test('convertRegularItemToParaBackspace lifts bullet item when it is the only item, with a preceding paragraph', () => {
  const docIn = doc(
    paragraph('before'),
    bullet_list(regular_list_item(paragraph('<a>x')))
  )
  assertCommand(
    convertRegularItemToParaBackspace,
    docIn,
    doc(paragraph('before'), paragraph('<a>x'))
  )

  // Also verify selection is TextSelection, not NodeSelection
  const state = mkState(docIn)
  let resultTr: Transaction | null = null
  convertRegularItemToParaBackspace(state, (tr) => { resultTr = tr })
  expect(resultTr.selection).toBeInstanceOf(TextSelection)
  expect(resultTr.selection.empty).toBe(true)
})

test('convertRegularItemToParaBackspace lifts bullet item when list is the only block in the doc', () => {
  const docIn = doc(bullet_list(regular_list_item(paragraph('<a>x'))))
  assertCommand(
    convertRegularItemToParaBackspace,
    docIn,
    doc(paragraph('<a>x'))
  )

  const state = mkState(docIn)
  let resultTr: Transaction | null = null
  convertRegularItemToParaBackspace(state, (tr) => { resultTr = tr })
  expect(resultTr.selection).toBeInstanceOf(TextSelection)
  expect(resultTr.selection.empty).toBe(true)
})

test('convertRegularItemToParaBackspace on first of multiple bullet items extracts paragraph and keeps rest', () => {
  const docIn = doc(
    bullet_list(
      regular_list_item(paragraph('<a>first')),
      regular_list_item(paragraph('second'))
    )
  )
  assertCommand(
    convertRegularItemToParaBackspace,
    docIn,
    doc(
      paragraph('<a>first'),
      bullet_list(regular_list_item(paragraph('second')))
    )
  )

  const state = mkState(docIn)
  let resultTr: Transaction | null = null
  convertRegularItemToParaBackspace(state, (tr) => { resultTr = tr })
  expect(resultTr.selection).toBeInstanceOf(TextSelection)
  expect(resultTr.selection.empty).toBe(true)
})

test('convertRegularItemToParaBackspace lifts ordered item when it is the only item', () => {
  const docIn = doc(ordered_list(regular_list_item(paragraph('<a>x'))))
  // Single item: the entire list wrapper is removed. List-type preservation
  // is tested in the multi-item case below.
  assertCommand(
    convertRegularItemToParaBackspace,
    docIn,
    doc(paragraph('<a>x'))
  )

  const state = mkState(docIn)
  let resultTr: Transaction | null = null
  convertRegularItemToParaBackspace(state, (tr) => { resultTr = tr })
  expect(resultTr.selection).toBeInstanceOf(TextSelection)
  expect(resultTr.selection.empty).toBe(true)
})

test('convertRegularItemToParaBackspace on first of multiple ordered items preserves ordered_list type for the remainder', () => {
  const docIn = doc(
    ordered_list(
      regular_list_item(paragraph('<a>first')),
      regular_list_item(paragraph('second'))
    )
  )
  // The remaining list wrapper must be ordered_list, not bullet_list.
  assertCommand(
    convertRegularItemToParaBackspace,
    docIn,
    doc(
      paragraph('<a>first'),
      ordered_list(regular_list_item(paragraph('second')))
    )
  )

  const state = mkState(docIn)
  let resultTr: Transaction | null = null
  convertRegularItemToParaBackspace(state, (tr) => { resultTr = tr })
  expect(resultTr.selection).toBeInstanceOf(TextSelection)
  expect(resultTr.selection.empty).toBe(true)
})

test('convertRegularItemToParaBackspace is a no-op when cursor is mid-text', () => {
  assertNoOp(
    convertRegularItemToParaBackspace,
    doc(bullet_list(regular_list_item(paragraph('bull<a>et'))))
  )
})

test('convertRegularItemToParaBackspace is a no-op at the start of a non-first item', () => {
  assertNoOp(
    convertRegularItemToParaBackspace,
    doc(
      bullet_list(
        regular_list_item(paragraph('first')),
        regular_list_item(paragraph('<a>second'))
      )
    )
  )
})

test('convertRegularItemToParaBackspace is a no-op when text is selected starting at offset 0', () => {
  assertNoOp(
    convertRegularItemToParaBackspace,
    doc(bullet_list(regular_list_item(paragraph('<a>bullet<b>'))))
  )
})

test('convertRegularItemToParaBackspace is a no-op in the second paragraph of a multi-paragraph item', () => {
  assertNoOp(
    convertRegularItemToParaBackspace,
    doc(
      bullet_list(
        regular_list_item(paragraph('one'), paragraph('<a>two'))
      )
    )
  )
})

test('convertRegularItemToParaBackspace at start of first paragraph of a multi-paragraph item lifts the full item content', () => {
  // Matches convertTaskItemToParaBackspace's behavior: when the cursor is at
  // the start of the FIRST paragraph of a multi-paragraph item, the whole
  // item's content is lifted out of the list (not just the first paragraph).
  assertCommand(
    convertRegularItemToParaBackspace,
    doc(
      bullet_list(
        regular_list_item(paragraph('<a>one'), paragraph('two'))
      )
    ),
    doc(paragraph('<a>one'), paragraph('two'))
  )

  // Analogous task-item case to confirm the same multi-paragraph behavior.
  assertCommand(
    convertTaskItemToParaBackspace,
    doc(
      bullet_list(
        task_list_item({ checked: false }, paragraph('<a>one'), paragraph('two'))
      )
    ),
    doc(paragraph('<a>one'), paragraph('two'))
  )
})

test('convertRegularItemToParaBackspace is a no-op for a nested list item', () => {
  // Documents current behavior: the new handler should not fire for nested
  // items. Backspace in a nested item falls through to the default handling.
  assertNoOp(
    convertRegularItemToParaBackspace,
    doc(
      bullet_list(
        regular_list_item(
          paragraph('outer'),
          bullet_list(regular_list_item(paragraph('<a>inner')))
        )
      )
    )
  )
})

test('convertRegularItemToParaBackspace is a no-op when cursor is in a plain paragraph', () => {
  assertNoOp(
    convertRegularItemToParaBackspace,
    doc(paragraph('<a>plain text'))
  )
})

// ─── Enter handler: split/lift list items ────────────────────────────────────

test('Enter inside a code block inserts a newline', () => {
  assertCommand(
    getEnterCommand(),
    doc(code_block('a<a>b')),
    doc(code_block('a\nb'))
  )
})

test('Enter on regular_list_item — empty item lifts out', () => {
  // only item in a bullet list
  runEnter(
    doc(bullet_list(regular_list_item(paragraph('<a>')))),
    doc(paragraph('<a>'))
  )

  // empty item with a preceding paragraph
  runEnter(
    doc(paragraph('before'), bullet_list(regular_list_item(paragraph('<a>')))),
    doc(paragraph('before'), paragraph('<a>'))
  )

  // empty item at end of list
  runEnter(
    doc(bullet_list(regular_list_item(paragraph('one')), regular_list_item(paragraph('<a>')))),
    doc(bullet_list(regular_list_item(paragraph('one'))), paragraph('<a>'))
  )

  // empty item at start of list
  runEnter(
    doc(bullet_list(regular_list_item(paragraph('<a>')), regular_list_item(paragraph('two')))),
    doc(paragraph('<a>'), bullet_list(regular_list_item(paragraph('two'))))
  )

  // empty item in the middle of a list
  runEnter(
    doc(
      bullet_list(
        regular_list_item(paragraph('one')),
        regular_list_item(paragraph('<a>')),
        regular_list_item(paragraph('two'))
      )
    ),
    doc(
      bullet_list(regular_list_item(paragraph('one'))),
      paragraph('<a>'),
      bullet_list(regular_list_item(paragraph('two')))
    )
  )

  // empty item at end of an ordered list — remaining list keeps ordered_list type
  const orderedEndTr = runEnter(
    doc(ordered_list(regular_list_item(paragraph('one')), regular_list_item(paragraph('<a>')))),
    doc(ordered_list(regular_list_item(paragraph('one'))), paragraph('<a>'))
  )
  expect(orderedEndTr.doc.firstChild!.type).toBe(schema.nodes.ordered_list)

  // only item in an ordered list
  runEnter(
    doc(ordered_list(regular_list_item(paragraph('<a>')))),
    doc(paragraph('<a>'))
  )
})

test('Enter on regular_list_item — non-empty item splits', () => {
  // Cursor at end of text
  assertCommand(
    getEnterCommand(),
    doc(bullet_list(regular_list_item(paragraph('hello<a>')))),
    doc(bullet_list(regular_list_item(paragraph('hello')), regular_list_item(paragraph('<a>'))))
  )

  // Cursor mid-text
  assertCommand(
    getEnterCommand(),
    doc(bullet_list(regular_list_item(paragraph('hel<a>lo world')))),
    doc(bullet_list(regular_list_item(paragraph('hel')), regular_list_item(paragraph('<a>lo world'))))
  )

  // Cursor at start of non-empty
  assertCommand(
    getEnterCommand(),
    doc(bullet_list(regular_list_item(paragraph('<a>hello')))),
    doc(bullet_list(regular_list_item(paragraph('')), regular_list_item(paragraph('<a>hello'))))
  )

  // Cursor in second item, non-empty
  assertCommand(
    getEnterCommand(),
    doc(
      bullet_list(
        regular_list_item(paragraph('one')),
        regular_list_item(paragraph('tw<a>o'))
      )
    ),
    doc(
      bullet_list(
        regular_list_item(paragraph('one')),
        regular_list_item(paragraph('tw')),
        regular_list_item(paragraph('<a>o'))
      )
    )
  )

  // Ordered non-empty
  assertCommand(
    getEnterCommand(),
    doc(ordered_list(regular_list_item(paragraph('hel<a>lo')))),
    doc(ordered_list(regular_list_item(paragraph('hel')), regular_list_item(paragraph('<a>lo'))))
  )
})

test('Enter on task_list_item — split and lift', () => {
  // Empty task item lifts out
  runEnter(
    doc(bullet_list(task_list_item({ checked: false }, paragraph('<a>')))),
    doc(paragraph('<a>'))
  )

  // Non-empty unchecked task item splits, new sibling unchecked
  assertCommand(
    getEnterCommand(),
    doc(bullet_list(task_list_item({ checked: false }, paragraph('hello<a>')))),
    doc(
      bullet_list(
        task_list_item({ checked: false }, paragraph('hello')),
        task_list_item({ checked: false }, paragraph('<a>'))
      )
    )
  )

  // Non-empty checked task item splits, new sibling unchecked
  assertCommand(
    getEnterCommand(),
    doc(bullet_list(task_list_item({ checked: true }, paragraph('hello<a>')))),
    doc(
      bullet_list(
        task_list_item({ checked: true }, paragraph('hello')),
        task_list_item({ checked: false }, paragraph('<a>'))
      )
    )
  )
})

test('Enter outside any list — no-op (falls through)', () => {
  assertNoOp(getEnterCommand(), doc(paragraph('hello<a>')))
  assertNoOp(getEnterCommand(), doc(heading({ level: 1 }, 'title<a>')))
  assertNoOp(getEnterCommand(), doc(blockquote(paragraph('quote<a>'))))
  assertNoOp(getEnterCommand(), doc(table(table_row(table_cell(paragraph('cell<a>'))))))
})

// ─── Shift+Enter handler ─────────────────────────────────────────────────────
// The one shared new-block gesture for every composer (chat, post body, post
// comments), bound ahead of prosemirror-remark's Shift-Enter → hard_break so the
// composers don't drift and Safari never loses the caret after a trailing <br>.

test('Shift+Enter splits a plain paragraph where Enter falls through', () => {
  // getEnterCommand no-ops on a plain paragraph (asserted above); Shift+Enter
  // splits it into a fresh block instead.
  assertCommand(
    getShiftEnterCommand(),
    doc(paragraph('hello<a>')),
    doc(paragraph('hello'), paragraph('<a>'))
  )

  // Mid-text split
  assertCommand(
    getShiftEnterCommand(),
    doc(paragraph('hel<a>lo')),
    doc(paragraph('hel'), paragraph('<a>lo'))
  )
})

test('Shift+Enter defers to the block-aware Enter inside code and lists', () => {
  // Code block: newline, not a split
  assertCommand(
    getShiftEnterCommand(),
    doc(code_block('a<a>b')),
    doc(code_block('a\nb'))
  )

  // Regular list item: new sibling item
  assertCommand(
    getShiftEnterCommand(),
    doc(bullet_list(regular_list_item(paragraph('hello<a>')))),
    doc(bullet_list(regular_list_item(paragraph('hello')), regular_list_item(paragraph('<a>'))))
  )

  // Task list item: new unchecked sibling
  assertCommand(
    getShiftEnterCommand(),
    doc(bullet_list(task_list_item({ checked: false }, paragraph('hello<a>')))),
    doc(
      bullet_list(
        task_list_item({ checked: false }, paragraph('hello')),
        task_list_item({ checked: false }, paragraph('<a>'))
      )
    )
  )
})

test('Tab sinks list items (both task and regular)', () => {
  // Regular bullet item nests under its preceding sibling
  assertCommand(
    getTabCommand(),
    doc(
      bullet_list(
        regular_list_item(paragraph('one')),
        regular_list_item(paragraph('tw<a>o'))
      )
    ),
    doc(
      bullet_list(
        regular_list_item(
          paragraph('one'),
          bullet_list(regular_list_item(paragraph('tw<a>o')))
        )
      )
    )
  )

  // Regular ordered item nests, preserving ordered_list type for the nested level
  assertCommand(
    getTabCommand(),
    doc(
      ordered_list(
        regular_list_item(paragraph('one')),
        regular_list_item(paragraph('tw<a>o'))
      )
    ),
    doc(
      ordered_list(
        regular_list_item(
          paragraph('one'),
          ordered_list(regular_list_item(paragraph('tw<a>o')))
        )
      )
    )
  )

  // Task item still sinks (regression)
  assertCommand(
    getTabCommand(),
    doc(
      bullet_list(
        task_list_item({ checked: false }, paragraph('one')),
        task_list_item({ checked: false }, paragraph('tw<a>o'))
      )
    ),
    doc(
      bullet_list(
        task_list_item(
          { checked: false },
          paragraph('one'),
          bullet_list(task_list_item({ checked: false }, paragraph('tw<a>o')))
        )
      )
    )
  )

  // First item can't sink — no preceding sibling to nest under
  assertNoOp(
    getTabCommand(),
    doc(bullet_list(regular_list_item(paragraph('<a>only'))))
  )

  // Plain paragraph — chain falls through to insertTabIndent which bails (no whitespace-preserving
  // ancestor), so the keymap returns false and Tab moves browser focus instead of inserting.
  assertNoOp(getTabCommand(), doc(paragraph('hello<a>')))
  // Inside a code_block — falls through to insertTabIndent and inserts \t
  assertCommand(getTabCommand(), doc(code_block('code<a>')), doc(code_block('code\t<a>')))
  // Inside a blockquote — also inserts \t
  assertCommand(
    getTabCommand(),
    doc(blockquote(paragraph('quote<a>'))),
    doc(blockquote(paragraph('quote\t<a>')))
  )
})

test('Shift-Tab lifts list items (both task and regular)', () => {
  // Nested regular item lifts back to the outer list
  assertCommand(
    getShiftTabCommand(),
    doc(
      bullet_list(
        regular_list_item(
          paragraph('one'),
          bullet_list(regular_list_item(paragraph('tw<a>o')))
        )
      )
    ),
    doc(
      bullet_list(
        regular_list_item(paragraph('one')),
        regular_list_item(paragraph('tw<a>o'))
      )
    )
  )

  // Top-level regular item lifts out of the list as a paragraph
  assertCommand(
    getShiftTabCommand(),
    doc(bullet_list(regular_list_item(paragraph('on<a>e'))))
  ,
    doc(paragraph('on<a>e'))
  )

  // Task item still lifts (regression)
  assertCommand(
    getShiftTabCommand(),
    doc(
      bullet_list(
        task_list_item(
          { checked: false },
          paragraph('one'),
          bullet_list(task_list_item({ checked: false }, paragraph('tw<a>o')))
        )
      )
    ),
    doc(
      bullet_list(
        task_list_item({ checked: false }, paragraph('one')),
        task_list_item({ checked: false }, paragraph('tw<a>o'))
      )
    )
  )

  // Outside any list — no-op
  assertNoOp(getShiftTabCommand(), doc(paragraph('hello<a>')))
})

test('Tab inserts a literal tab character only inside code blocks and blockquotes', () => {
  // Inside a code_block — inserts \t at the cursor
  assertCommand(insertTabIndent, doc(code_block('code<a>')), doc(code_block('code\t<a>')))
  // Mid-content code_block insertion
  assertCommand(insertTabIndent, doc(code_block('co<a>de')), doc(code_block('co\tde')))
  // Inside a blockquote paragraph — inserts \t
  assertCommand(
    insertTabIndent,
    doc(blockquote(paragraph('quote<a>'))),
    doc(blockquote(paragraph('quote\t<a>')))
  )
  // Code block nested inside a blockquote — ancestor walk finds blockquote (and code_block)
  assertCommand(
    insertTabIndent,
    doc(blockquote(code_block('code<a>'))),
    doc(blockquote(code_block('code\t<a>')))
  )
  // Non-empty selection within a blockquote textblock is replaced by \t
  assertCommand(
    insertTabIndent,
    doc(blockquote(paragraph('he<a>ll<b>o'))),
    doc(blockquote(paragraph('he\to')))
  )

  // Plain paragraph — no whitespace-preserving ancestor, so Tab falls through to browser focus.
  assertNoOp(insertTabIndent, doc(paragraph('hello<a>')))
  // Heading — same, falls through to browser focus.
  assertNoOp(insertTabIndent, doc(heading({ level: 2 }, 'title<a>')))
  // List items — falls through (list-item commands earlier in the chain handle these).
  assertNoOp(insertTabIndent, doc(bullet_list(regular_list_item(paragraph('item<a>')))))
  assertNoOp(insertTabIndent, doc(bullet_list(task_list_item({ checked: false }, paragraph('item<a>')))))
  // Table cells — falls through (tableKeymap.Tab navigates).
  assertNoOp(insertTabIndent, doc(table(table_row(table_cell(paragraph('cell<a>'))))))
  assertNoOp(insertTabIndent, doc(table(table_row(table_header(paragraph('hdr<a>'))))))
  // Selection spans two textblocks — bail regardless of ancestor.
  assertNoOp(insertTabIndent, doc(paragraph('fi<a>rst'), paragraph('seco<b>nd')))
})

test('Shift-Tab removes a preceding tab character only inside code blocks and blockquotes', () => {
  // Inside a code_block, single \t immediately before cursor is deleted
  assertCommand(removeTabOutdent, doc(code_block('code\t<a>')), doc(code_block('code<a>')))
  // Only one \t removed per call inside a code_block, even if multiple precede
  assertCommand(removeTabOutdent, doc(code_block('\t\t<a>middle')), doc(code_block('\t<a>middle')))
  // Inside a blockquote paragraph
  assertCommand(
    removeTabOutdent,
    doc(blockquote(paragraph('quote\t<a>'))),
    doc(blockquote(paragraph('quote<a>')))
  )

  // Plain paragraph with preceding \t — no whitespace-preserving ancestor, Shift+Tab moves focus.
  assertNoOp(removeTabOutdent, doc(paragraph('hello\t<a>')))
  // Heading with preceding \t — same
  assertNoOp(removeTabOutdent, doc(heading({ level: 1 }, 'title\t<a>')))
  // Inside a code_block but no preceding \t — no-op
  assertNoOp(removeTabOutdent, doc(code_block('hello<a>')))
  // Cursor at parentOffset 0 inside code_block — nothing before to delete
  assertNoOp(removeTabOutdent, doc(code_block('<a>hello')))
  // Non-empty selection inside a code_block — no-op
  assertNoOp(removeTabOutdent, doc(code_block('hel<a>lo<b>')))
  // Cursor inside a list item — falls through
  assertNoOp(removeTabOutdent, doc(bullet_list(regular_list_item(paragraph('item\t<a>')))))
  // Cursor inside table cell — falls through
  assertNoOp(removeTabOutdent, doc(table(table_row(table_cell(paragraph('cell\t<a>'))))))
})

test('Enter on nested regular list — inner empty item becomes a sibling at the outer level', () => {
  // splitListItem lifts the empty nested item one level: it becomes a sibling
  // list item in the outer list containing an empty paragraph, rather than
  // merging into the outer item as a second paragraph.
  runEnter(
    doc(
      bullet_list(
        regular_list_item(
          paragraph('outer'),
          bullet_list(regular_list_item(paragraph('<a>')))
        )
      )
    ),
    doc(
      bullet_list(
        regular_list_item(paragraph('outer')),
        regular_list_item(paragraph())
      )
    )
  )
})
