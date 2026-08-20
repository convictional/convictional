import { InputRule } from "prosemirror-inputrules"
import { Schema } from "prosemirror-model"
import {
  BlockquoteExtension,
  BoldExtension,
  BreakExtension,
  DefinitionExtension,
  HeadingExtension,
  HorizontalRuleExtension,
  ImageExtension,
  ImageReferenceExtension,
  InlineCodeExtension,
  ItalicExtension,
  LinkExtension,
  LinkReferenceExtension,
  ListItemExtension,
  MarkdownExtension,
  OrderedListExtension,
  ParagraphExtension,
  RootExtension,
  StrikethroughExtension,
  TaskListItemExtension,
  TextExtension,
  UnorderedListExtension,
} from "prosemirror-remark"
import { Command } from "prosemirror-state"
import { ProseMirrorUnified, MarkInputRule, Extension } from "prosemirror-unified"

import { CommentMarkExtension } from "./commentMark"
import { EmptyContentSafeCodeBlockExtension, EmptyTextNodeSafeExtension } from "./emptyTextHandling"
import { MarkNormalizationExtension } from "./markNormalization"
import { MentionExtension } from "./mentions"
import { ParagraphFormattingExtension } from "./paragraphFormatting"
import { QuotedHtmlExtension } from "./quotedHtml"
import { TableExtension, TableRowExtension, TableCellExtension, TableHeaderExtension } from "./tables"
import { UrlFormattingExtension } from "./urlFormatting"

export class TrailingSpaceItalicExtension extends ItalicExtension {
  public override proseMirrorInputRules(proseMirrorSchema: Schema<string, string>): Array<InputRule> {
    return [
      new MarkInputRule(/\*([^\s*][^*]*?[^\s*]|[^\s*])\*(\s)$/u, proseMirrorSchema.marks[this.proseMirrorMarkName()]),
      new MarkInputRule(
        /_{1}([^\s_][^_]*?[^\s_]|[^\s_])_{1}(\s)$/u,
        proseMirrorSchema.marks[this.proseMirrorMarkName()]
      ),
    ]
  }
}

export class TrailingSpaceBoldExtension extends BoldExtension {
  public override proseMirrorInputRules(proseMirrorSchema: Schema<string, string>): Array<InputRule> {
    return [
      new MarkInputRule(
        /\*\*([^\s*][^*]*?[^\s*]|[^\s*])\*\*(\s)$/u,
        proseMirrorSchema.marks[this.proseMirrorMarkName()]
      ),
      new MarkInputRule(/__([^\s_][^_]*?[^\s_]|[^\s_])__(\s)$/u, proseMirrorSchema.marks[this.proseMirrorMarkName()]),
    ]
  }
}

// ListItemExtension's parseDOM rule matches every <li> unconditionally. Without a priority
// bump, it wins over TaskListItemExtension's rule (which correctly filters <li>s whose first
// child is an <input type="checkbox">), so Google Docs checklists pasted as
// <li><input type="checkbox"> would parse as regular_list_item. Bump to priority 51 so the
// more specific task-list rule is tried first; if getAttrs returns false, parsing falls
// through to ListItemExtension as usual.
class PrioritizedTaskListItemExtension extends TaskListItemExtension {
  public override proseMirrorNodeSpec() {
    const spec = super.proseMirrorNodeSpec()
    return {
      ...spec,
      parseDOM: spec.parseDOM?.map(rule => ({ ...rule, priority: 51 })),
    }
  }

  public override proseMirrorKeymap(proseMirrorSchema: Schema<string, string>): Record<string, Command> {
    // Upstream Backspace converts a task_list_item to a regular_list_item with broken
    // range math: it crashes with "Position N out of range" on non-first paragraph
    // children (yjs collab can produce multi-paragraph items), and corrupts the doc on
    // non-first items. Our own convertTaskItemToParaBackspace + default joinBackward
    // cover the cases we want, so step aside entirely.
    return {
      ...super.proseMirrorKeymap(proseMirrorSchema),
      Backspace: () => false,
    }
  }
}

class CustomizedMarkdownExtension extends MarkdownExtension {
  public override dependencies(): Array<Extension> {
    return [
      new ParagraphExtension(),
      new BlockquoteExtension(),
      new TrailingSpaceBoldExtension(),
      new BreakExtension(),
      new EmptyContentSafeCodeBlockExtension(),
      new DefinitionExtension(),
      new HeadingExtension(),
      new HorizontalRuleExtension(),
      new ImageExtension(),
      new ImageReferenceExtension(),
      new InlineCodeExtension(),
      new TrailingSpaceItalicExtension(),
      new LinkExtension(),
      new LinkReferenceExtension(),
      new ListItemExtension(),
      new OrderedListExtension(),
      new RootExtension(),
      new TextExtension(),
      new UnorderedListExtension(),
      new MentionExtension(),
      new ParagraphFormattingExtension(),
      new QuotedHtmlExtension(),
      new UrlFormattingExtension(),
      new TableExtension(),
      new TableRowExtension(),
      new TableCellExtension(),
      new TableHeaderExtension(),
      new EmptyTextNodeSafeExtension(),
      new CommentMarkExtension(),
      new StrikethroughExtension(),
      new PrioritizedTaskListItemExtension(),
      new MarkNormalizationExtension(),
    ]
  }
}

export const pmu = new ProseMirrorUnified([new CustomizedMarkdownExtension()])
export const schema = pmu.schema()
