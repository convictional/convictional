import { test, describe, expect } from 'vitest';
import { builders } from 'prosemirror-test-builder';
import { parse, schema, serialize } from '../../../app/javascript/richText/schema';
import { toggleCode, toggleHeading } from '../../../app/javascript/richText/commands';
import { assertCommand, assertNoOp } from './schema/testHelpers';

const { doc, paragraph, heading, code, bullet_list, regular_list_item, blockquote, code_block, image, strong, table, table_row, table_cell } = builders(schema);

describe('toggleHeading', () => {
  test('sets and toggles heading levels for a single block', () => {
    // 1. Cursor inside a paragraph → click H2 → block becomes Heading 2
    assertCommand(
      toggleHeading(2),
      doc(paragraph('hello<a>')),
      doc(heading({ level: 2 }, 'hello<a>'))
    );

    // 2. Cursor inside a Heading 2 → click H2 → block becomes paragraph (toggle off).
    //    Also verifies edge case 5: the result doc has a paragraph (not a heading),
    //    so the active-state binding would turn off.
    assertCommand(
      toggleHeading(2),
      doc(heading({ level: 2 }, 'hello<a>')),
      doc(paragraph('hello<a>'))
    );

    // 3. Cursor inside a Heading 1 → click H3 → block becomes Heading 3
    //    (switch levels, NOT toggle off).
    assertCommand(
      toggleHeading(3),
      doc(heading({ level: 1 }, 'hello<a>')),
      doc(heading({ level: 3 }, 'hello<a>'))
    );

    // 4. Full round-trip: paragraph → H1 → paragraph again.
    assertCommand(toggleHeading(1), doc(paragraph('round<a>')), doc(heading({ level: 1 }, 'round<a>')));
    assertCommand(toggleHeading(1), doc(heading({ level: 1 }, 'round<a>')), doc(paragraph('round<a>')));
  });

  test('is a no-op inside a code block', () => {
    // 6. Cursor inside a code block → toggleHeading(1) is a no-op.
    assertNoOp(
      toggleHeading(1),
      doc(code_block('const x = 1;<a>'))
    );
  });

  test('is a no-op for a selection that spans a code block', () => {
    // Ensure the range scan catches code blocks even when the selection starts
    // in a paragraph. Without the range scan, only $from.node() would be checked
    // and the code block would get converted.
    assertNoOp(
      toggleHeading(1),
      doc(paragraph('para<a>graph'), code_block('const x = 1;<b>'))
    );
  });

  test('applies heading to all blocks in a multi-block selection starting in a paragraph', () => {
    // 7. Multi-block selection starting in a paragraph: clicking H2 sets ALL
    //    blocks in range to H2 (all-same rule: not every block is already H2,
    //    so apply rather than toggle off).
    assertCommand(
      toggleHeading(2),
      doc(paragraph('fi<a>rst'), paragraph('sec<b>ond')),
      doc(heading({ level: 2 }, 'first'), heading({ level: 2 }, 'second'))
    );
  });

  test('applies heading when multi-block selection starts in a same-level heading but includes non-headings', () => {
    // 8. [H2, paragraph] selected, click H2 → all-same rule means we APPLY
    //    (set both to H2), not toggle off. Toggle-off only fires when every
    //    selected block is already at the target level.
    assertCommand(
      toggleHeading(2),
      doc(heading({ level: 2 }, 'fi<a>rst'), paragraph('sec<b>ond')),
      doc(heading({ level: 2 }, 'first'), heading({ level: 2 }, 'second'))
    );
  });

  test('preserves an inline image when converting an adjacent text line to a heading', () => {
    // 1. Image and text share one paragraph; converting the text to a heading must
    //    keep the image (its own paragraph above) and preserve its src.
    assertCommand(
      toggleHeading(1),
      doc(paragraph(image({ src: 'trulli.jpg' }), 'Heading text<a>')),
      doc(paragraph(image({ src: 'trulli.jpg' })), heading({ level: 1 }, 'Heading text'))
    );

    // 2. A leftover separator newline between image and text is normalized away —
    //    no leading space, no embedded newline. The leading "\n" boundary node
    //    trims to empty and must be dropped.
    assertCommand(
      toggleHeading(1),
      doc(paragraph(image({ src: 'x.png' }), '\nHeading text<a>')),
      doc(paragraph(image({ src: 'x.png' })), heading({ level: 1 }, 'Heading text'))
    );

    // 3. Inline marks on the text survive the conversion.
    assertCommand(
      toggleHeading(1),
      doc(paragraph(image({ src: 'x.png' }), strong('Bold<a>'))),
      doc(paragraph(image({ src: 'x.png' })), heading({ level: 1 }, strong('Bold')))
    );

    // 4. The result survives a parse(serialize(...)) round-trip: the image node
    //    (src intact) and the heading text both persist.
    const result = doc(paragraph(image({ src: 'trulli.jpg' })), heading({ level: 1 }, 'Heading text'));
    const roundTripped = parse(serialize(result));

    let foundImage = false;
    let foundHeadingText = false;
    roundTripped.descendants((node) => {
      if (node.type.name === 'image' && node.attrs.src === 'trulli.jpg') foundImage = true;
      if (node.type.name === 'heading' && node.textContent === 'Heading text') foundHeadingText = true;
      return true;
    });
    expect(foundImage).toBe(true);
    expect(foundHeadingText).toBe(true);

    // 5. Block containing only an image (no text run): the image is preserved and
    //    no empty heading is created.
    assertCommand(
      toggleHeading(1),
      doc(paragraph(image({ src: 'x.png' }), '<a>')),
      doc(paragraph(image({ src: 'x.png' })))
    );

    // 6. Multi-block selection: a text-only block converts in place; a block with an
    //    image splits into its own paragraph above a heading. Order is preserved.
    assertCommand(
      toggleHeading(1),
      doc(paragraph('Intro<a>'), paragraph(image({ src: 'x.png' }), 'More<b>')),
      doc(heading({ level: 1 }, 'Intro'), paragraph(image({ src: 'x.png' })), heading({ level: 1 }, 'More'))
    );

    // 7. Container matrix — blockquote (content `block+`) CAN hold [paragraph, heading],
    //    so the image+text paragraph reconstructs in place, nested inside the blockquote.
    assertCommand(
      toggleHeading(1),
      doc(blockquote(paragraph(image({ src: 'x.png' }), 'Quote text<a>'))),
      doc(blockquote(paragraph(image({ src: 'x.png' })), heading({ level: 1 }, 'Quote text')))
    );

    // 8. Container matrix — table_cell content is `paragraph`, so it can't hold a heading.
    //    The guard skips the block: no-op, image preserved, nothing lifted out of the table.
    assertNoOp(
      toggleHeading(1),
      doc(table(table_row(table_cell(paragraph(image({ src: 'x.png' }), 'Cell text<a>')))))
    );

    // 9. Container matrix — regular_list_item is `paragraph block*` (first child must be a
    //    paragraph). Text-then-image would reconstruct to [heading, paragraph(image)], which
    //    is invalid (heading can't be first), so the guard skips it: no-op, image preserved.
    assertNoOp(
      toggleHeading(1),
      doc(bullet_list(regular_list_item(paragraph('Item text<a>', image({ src: 'x.png' })))))
    );
  });
});

describe('toggleCode', () => {
  test('toggles the inline code mark on a single-textblock selection', () => {
    // Selection inside one paragraph → wrap the selected run in the inline code mark.
    assertCommand(
      toggleCode(),
      doc(paragraph('he<a>ll<b>o')),
      doc(paragraph('he', code('ll'), 'o'))
    );

    // Selection covers an existing inline code run → remove the mark.
    // ProseMirror coalesces the resulting unmarked text nodes into one.
    assertCommand(
      toggleCode(),
      doc(paragraph('he', code('<a>ll<b>'), 'o')),
      doc(paragraph('hello'))
    );
  });

  test('collapses a multi-textblock selection into one code_block joined by \\n', () => {
    // Two paragraphs → single code_block joined by '\n'.
    assertCommand(
      toggleCode(),
      doc(paragraph('fi<a>rst'), paragraph('seco<b>nd')),
      doc(code_block('first\nsecond'))
    );

    // Intervening heading also contributes its text.
    assertCommand(
      toggleCode(),
      doc(paragraph('one<a>'), heading({ level: 2 }, 'two'), paragraph('th<b>ree')),
      doc(code_block('one\ntwo\nthree'))
    );

    // Selection spanning list items: the resulting code_block replaces the list entirely.
    assertCommand(
      toggleCode(),
      doc(bullet_list(regular_list_item(paragraph('a<a>')), regular_list_item(paragraph('b<b>')))),
      doc(code_block('a\nb'))
    );

    // Selection inside a blockquote: code_block is a valid child of blockquote,
    // so smart-fit keeps the new code_block nested rather than lifting it.
    assertCommand(
      toggleCode(),
      doc(blockquote(paragraph('one<a>'), paragraph('two<b>'))),
      doc(blockquote(code_block('one\ntwo')))
    );
  });

  test('toggles a code_block back to one paragraph per newline-separated line', () => {
    // Non-empty code_block, cursor at end → one paragraph per line.
    assertCommand(
      toggleCode(),
      doc(code_block('first\nsecond\nthird<a>')),
      doc(paragraph('first'), paragraph('second'), paragraph('third'))
    );

    // Cursor in the middle of the code_block → same result. The unwrap is position-independent;
    // this test guards against a future regression that uses the cursor offset to slice content.
    assertCommand(
      toggleCode(),
      doc(code_block('fi<a>rst\nsecond')),
      doc(paragraph('first'), paragraph('second'))
    );

    // Empty code_block → a single empty paragraph.
    assertCommand(
      toggleCode(),
      doc(code_block('<a>')),
      doc(paragraph())
    );
  });

  test('toggles a selection spanning multiple code_blocks back to paragraphs', () => {
    // Two adjacent code_blocks selected end-to-end → unwrap both. Without this branch the
    // command would fall through to the merge path and combine them into a single larger
    // code_block, surprising users who clicked an active "<>" button expecting toggle-off.
    assertCommand(
      toggleCode(),
      doc(code_block('a<a>'), code_block('b<b>')),
      doc(paragraph('a'), paragraph('b'))
    );

    // Multi-line content on each block also splits on '\n'.
    assertCommand(
      toggleCode(),
      doc(code_block('one<a>\ntwo'), code_block('three\nfour<b>')),
      doc(paragraph('one'), paragraph('two'), paragraph('three'), paragraph('four'))
    );
  });
});
