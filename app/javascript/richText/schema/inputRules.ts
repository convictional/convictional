import { nameToEmoji } from "gemoji"
import { InputRule, inputRules } from "prosemirror-inputrules"
import { MarkType } from "prosemirror-model"
import { EditorState, Plugin, Transaction } from "prosemirror-state"

import { schema } from "./instance"

/* eslint-disable @typescript-eslint/no-explicit-any */
type Attributes = { [key: string]: any }
/* eslint-enable @typescript-eslint/no-explicit-any */
type AttributesGetter = (match: RegExpMatchArray) => Attributes

function markInputRule(
  regexp: RegExp,
  markType: MarkType,
  getAttrs?: Attributes | AttributesGetter,
  skipStart?: RegExp
): InputRule {
  return new InputRule(
    regexp,
    (state: EditorState, match: RegExpMatchArray, start: number, end: number): Transaction | null => {
      const attrs = typeof getAttrs === "function" ? getAttrs(match) : getAttrs
      const tr = state.tr

      if (match[1]) {
        let skipMatch: RegExpMatchArray | null
        let skipLen = 0

        if (skipStart && match[0].match(skipStart)) {
          skipMatch = match[0].match(skipStart)
          if (skipMatch && skipMatch[0]) {
            skipLen = skipMatch[0].length
            start += skipLen
          }
        }

        const textStart = start + match[0].indexOf(match[1]) - skipLen
        const textEnd = textStart + match[1].length

        if (textEnd < end) tr.delete(textEnd, end)
        if (textStart > start) tr.delete(start, textStart)

        end = start + match[1].length
      }

      tr.addMark(start, end, markType.create(attrs || {}))
      tr.removeStoredMark(markType)

      return tr
    }
  )
}

function getInputRules(): Plugin {
  return inputRules({
    rules: [
      // [ ] or [x] at the start of a regular_list_item → convert to task_list_item.
      // Overrides the broken rule in prosemirror-remark which miscalculates the
      // replacement end position, causing a RangeError when the list is at the
      // end of the document.
      new InputRule(
        /^\[([x\s]?)\][\s\S]$/u,
        (state: EditorState, match: RegExpMatchArray, start: number): Transaction | null => {
          const $start = state.doc.resolve(start)
          const listItem = $start.node(-1)
          if (listItem.type !== schema.nodes.regular_list_item) return null

          const listItemStart = $start.before(-1)
          return state.tr.replaceRangeWith(
            listItemStart,
            listItemStart + listItem.nodeSize,
            schema.nodes.task_list_item.create(
              { checked: match[1] === "x" },
              listItem.content.cut(3 + match[1].length)
            )
          )
        }
      ),
      // [link](href)
      markInputRule(/(?:\[([^\]]+)\])\(([^)]+)\)$/, schema.marks.link, function (match) {
        return { href: match[2] }
      }),
      // :emoji_shortcode: → unicode emoji
      new InputRule(
        /:([a-z0-9_+-]+):$/,
        (state: EditorState, match: RegExpMatchArray, start: number, end: number): Transaction | null => {
          const emoji = nameToEmoji[match[1]]
          if (!emoji) return null
          return state.tr.replaceWith(start, end, schema.text(emoji))
        }
      ),
    ],
  })
}

export { getInputRules }
