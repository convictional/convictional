import { test } from 'vitest';
import { builders } from 'prosemirror-test-builder';
import { schema } from '../../../../../app/javascript/richText/schema';
import { toggleList, toggleTaskList } from '../../../../../app/javascript/richText/schema/keymap';
import { assertCommand, assertNoOp } from '../../../richText/schema/testHelpers';

const { doc, paragraph, bullet_list, ordered_list, task_list_item, regular_list_item } = builders(schema);

// ─── toggle-off: single item ──────────────────────────────────────────────────

test('toggleTaskList toggle-off converts a single task item to a plain paragraph', () => {
  assertCommand(
    toggleTaskList,
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

// ─── toggle-off: selection spanning multiple items ────────────────────────────
// Regression: toggle-off must convert all task items in a range selection,
// not just the item at the anchor position.

test('toggleTaskList toggle-off converts all items in a range selection to paragraphs', () => {
  assertCommand(
    toggleTaskList,
    doc(
      bullet_list(
        task_list_item({ checked: false }, paragraph('<a>first')),
        task_list_item({ checked: false }, paragraph('second')),
        task_list_item({ checked: false }, paragraph('third<b>'))
      )
    ),
    doc(
      paragraph('<a>first'),
      paragraph('second'),
      paragraph('third<b>')
    )
  )
})

// ─── toggle-on: paragraphs become task items ──────────────────────────────────

test('toggleTaskList toggle-on wraps plain paragraphs in a task list', () => {
  assertCommand(
    toggleTaskList,
    doc(paragraph('<a>some text')),
    doc(
      bullet_list(
        task_list_item({ checked: false }, paragraph('<a>some text'))
      )
    )
  )
})

// ─── toggle-on: no-op when already in task list with selection not meeting criteria ──

test('toggleTaskList is a no-op on content that cannot be wrapped in a list', () => {
  // An already-task-list cursor should toggle off, not be a no-op — covered above.
  // A plain paragraph always can be wrapped, so only truly invalid states are no-ops.
  // This test documents that the command returns false for content that can't be wrapped
  // (e.g. a code block, which wrapInList rejects).
  const { code_block } = builders(schema);
  assertNoOp(
    toggleTaskList,
    doc(code_block('<a>code'))
  )
})

// ─── toggleList: conversions between list types ───────────────────────────────

test('toggleList converts between bullet and numbered lists preserving items and order', () => {
  // bullet → numbered
  assertCommand(
    toggleList(schema.nodes.ordered_list, schema.nodes.regular_list_item),
    doc(
      bullet_list(
        regular_list_item(paragraph('<a>a')),
        regular_list_item(paragraph('b'))
      )
    ),
    doc(
      ordered_list(
        regular_list_item(paragraph('a')),
        regular_list_item(paragraph('b'))
      )
    )
  )

  // numbered → bullet (inverse)
  assertCommand(
    toggleList(schema.nodes.bullet_list, schema.nodes.regular_list_item),
    doc(
      ordered_list(
        regular_list_item(paragraph('<a>a')),
        regular_list_item(paragraph('b'))
      )
    ),
    doc(
      bullet_list(
        regular_list_item(paragraph('a')),
        regular_list_item(paragraph('b'))
      )
    )
  )
})

test('toggleList converts regular lists to task lists resetting checkboxes', () => {
  // bullet → task
  assertCommand(
    toggleList(schema.nodes.bullet_list, schema.nodes.task_list_item),
    doc(
      bullet_list(
        regular_list_item(paragraph('<a>a')),
        regular_list_item(paragraph('b'))
      )
    ),
    doc(
      bullet_list(
        task_list_item({ checked: false }, paragraph('a')),
        task_list_item({ checked: false }, paragraph('b'))
      )
    )
  )

  // numbered → task (container ordered→bullet AND items regular→task)
  assertCommand(
    toggleList(schema.nodes.bullet_list, schema.nodes.task_list_item),
    doc(
      ordered_list(
        regular_list_item(paragraph('<a>a')),
        regular_list_item(paragraph('b'))
      )
    ),
    doc(
      bullet_list(
        task_list_item({ checked: false }, paragraph('a')),
        task_list_item({ checked: false }, paragraph('b'))
      )
    )
  )
})

test('toggleList converts task lists to regular lists dropping checkbox state', () => {
  // task → bullet
  assertCommand(
    toggleList(schema.nodes.bullet_list, schema.nodes.regular_list_item),
    doc(
      bullet_list(
        task_list_item({ checked: false }, paragraph('<a>a')),
        task_list_item({ checked: false }, paragraph('b'))
      )
    ),
    doc(
      bullet_list(
        regular_list_item(paragraph('a')),
        regular_list_item(paragraph('b'))
      )
    )
  )

  // task → numbered (container bullet→ordered AND items task→regular)
  assertCommand(
    toggleList(schema.nodes.ordered_list, schema.nodes.regular_list_item),
    doc(
      bullet_list(
        task_list_item({ checked: false }, paragraph('<a>a')),
        task_list_item({ checked: false }, paragraph('b'))
      )
    ),
    doc(
      ordered_list(
        regular_list_item(paragraph('a')),
        regular_list_item(paragraph('b'))
      )
    )
  )
})

// ─── toggleList: toggle-off (matching list type unwraps to paragraphs) ─────────

test('toggleList toggles off a matching list into plain paragraphs', () => {
  // bullet, single item (cursor)
  assertCommand(
    toggleList(schema.nodes.bullet_list, schema.nodes.regular_list_item),
    doc(
      bullet_list(
        regular_list_item(paragraph('<a>only'))
      )
    ),
    doc(
      paragraph('<a>only')
    )
  )

  // bullet, multi-item span selection
  assertCommand(
    toggleList(schema.nodes.bullet_list, schema.nodes.regular_list_item),
    doc(
      bullet_list(
        regular_list_item(paragraph('<a>first')),
        regular_list_item(paragraph('second')),
        regular_list_item(paragraph('third<b>'))
      )
    ),
    doc(
      paragraph('<a>first'),
      paragraph('second'),
      paragraph('third<b>')
    )
  )

  // numbered
  assertCommand(
    toggleList(schema.nodes.ordered_list, schema.nodes.regular_list_item),
    doc(
      ordered_list(
        regular_list_item(paragraph('<a>first')),
        regular_list_item(paragraph('second<b>'))
      )
    ),
    doc(
      paragraph('<a>first'),
      paragraph('second<b>')
    )
  )
})

test('toggleList toggle-off of a subset splits the list rebuilding prefix and suffix with the enclosing list type', () => {
  assertCommand(
    toggleList(schema.nodes.ordered_list, schema.nodes.regular_list_item),
    doc(
      ordered_list(
        regular_list_item(paragraph('first')),
        regular_list_item(paragraph('<a>second<b>')),
        regular_list_item(paragraph('third'))
      )
    ),
    doc(
      ordered_list(
        regular_list_item(paragraph('first'))
      ),
      paragraph('second'),
      ordered_list(
        regular_list_item(paragraph('third'))
      )
    )
  )
})

// ─── toggleList: toggle-on (paragraphs become lists) ──────────────────────────

test('toggleList toggles on paragraphs into the requested list type', () => {
  // bullet
  assertCommand(
    toggleList(schema.nodes.bullet_list, schema.nodes.regular_list_item),
    doc(paragraph('<a>text')),
    doc(
      bullet_list(
        regular_list_item(paragraph('text'))
      )
    )
  )

  // numbered
  assertCommand(
    toggleList(schema.nodes.ordered_list, schema.nodes.regular_list_item),
    doc(paragraph('<a>text')),
    doc(
      ordered_list(
        regular_list_item(paragraph('text'))
      )
    )
  )
})
