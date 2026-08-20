import type { Table, TableCell, TableRow, PhrasingContent, RowContent } from "mdast"
import { gfmTableFromMarkdown, gfmTableToMarkdown } from "mdast-util-gfm-table"
import { gfmTable } from "micromark-extension-gfm-table"
import { Node, NodeSpec, Schema } from "prosemirror-model"
import { tableNodes } from "prosemirror-tables"
import { NodeExtension } from "prosemirror-unified"
import { Processor } from "unified"
import { Node as UnistNode, Parent } from "unist"
import { visit } from "unist-util-visit"

// Reference specs from prosemirror-tables to ensure compatibility with its commands
const referenceSpecs = tableNodes({ tableGroup: "block", cellContent: "paragraph", cellAttributes: {} })

// Custom mdast type for annotated header cells (used only in the parse pipeline)
interface TableHeader extends Omit<TableCell, "type"> {
  type: "tableHeader"
}

export class TableExtension extends NodeExtension<Table> {
  proseMirrorNodeName(): string {
    return "table"
  }

  proseMirrorNodeSpec(): NodeSpec {
    return { ...referenceSpecs.table } as NodeSpec
  }

  proseMirrorNodeToUnistNodes(_node: Node, convertedChildren: UnistNode[]): Table[] {
    const rows = convertedChildren as TableRow[]
    const colCount = rows.length > 0 ? rows[0].children.length : 0
    return [
      {
        type: "table",
        align: Array<null>(colCount).fill(null),
        children: rows,
      },
    ]
  }

  unistNodeName(): "table" {
    return "table"
  }

  unistNodeToProseMirrorNodes(_node: Table, schema: Schema<string, string>, convertedChildren: Node[]): Node[] {
    return [schema.nodes.table.create(null, convertedChildren)]
  }

  unifiedInitializationHook(
    processor: Processor<UnistNode, UnistNode, UnistNode, UnistNode, string>
  ): Processor<UnistNode, UnistNode, UnistNode, UnistNode, string> {
    const data = processor.data()
    data.micromarkExtensions ??= []
    data.fromMarkdownExtensions ??= []
    data.toMarkdownExtensions ??= []

    data.micromarkExtensions.push(gfmTable())
    data.fromMarkdownExtensions.push(gfmTableFromMarkdown())
    data.toMarkdownExtensions.push(gfmTableToMarkdown())

    // Annotate first-row cells with our invented "tableHeader" sentinel so
    // TableHeaderExtension.unistToProseMirrorTest can claim them downstream.
    // mdast has no header type; all GFM table cells are `tableCell` by
    // convention, so we rewrite the first-row entries as TableHeader shapes.
    // Fresh objects (no in-place mutation) keep any cached references safe.
    return processor.use(function annotateTableHeaders() {
      return (tree: UnistNode) => {
        visit(tree, "table", node => {
          const table = node as Table
          if (table.children.length === 0) return
          const firstRow = table.children[0]
          const headers: TableHeader[] = firstRow.children.map(cell => ({
            ...cell,
            type: "tableHeader",
          }))
          firstRow.children = headers as unknown as RowContent[]
        })
      }
    })
  }
}

export class TableRowExtension extends NodeExtension<TableRow> {
  proseMirrorNodeName(): string {
    return "table_row"
  }

  proseMirrorNodeSpec(): NodeSpec {
    return { ...referenceSpecs.table_row } as NodeSpec
  }

  proseMirrorNodeToUnistNodes(_node: Node, convertedChildren: UnistNode[]): TableRow[] {
    return [
      {
        type: "tableRow",
        children: convertedChildren as RowContent[],
      },
    ]
  }

  unistNodeName(): "tableRow" {
    return "tableRow"
  }

  unistNodeToProseMirrorNodes(_node: TableRow, schema: Schema<string, string>, convertedChildren: Node[]): Node[] {
    return [schema.nodes.table_row.create(null, convertedChildren)]
  }
}

export class TableCellExtension extends NodeExtension<TableCell> {
  proseMirrorNodeName(): string {
    return "table_cell"
  }

  proseMirrorNodeSpec(): NodeSpec {
    return { ...referenceSpecs.table_cell } as NodeSpec
  }

  proseMirrorNodeToUnistNodes(_node: Node, convertedChildren: UnistNode[]): TableCell[] {
    // PM cell contains a paragraph; unwrap to get inline content for mdast
    const paragraph = convertedChildren[0] as Parent | undefined
    return [
      {
        type: "tableCell",
        children: (paragraph?.children ?? []) as PhrasingContent[],
      },
    ]
  }

  unistNodeName(): "tableCell" {
    return "tableCell"
  }

  unistNodeToProseMirrorNodes(_node: TableCell, schema: Schema<string, string>, convertedChildren: Node[]): Node[] {
    const paragraph = schema.nodes.paragraph.create(null, convertedChildren)
    return [schema.nodes.table_cell.create(null, [paragraph])]
  }
}

export class TableHeaderExtension extends NodeExtension<TableHeader> {
  proseMirrorNodeName(): string {
    return "table_header"
  }

  proseMirrorNodeSpec(): NodeSpec {
    return { ...referenceSpecs.table_header } as NodeSpec
  }

  proseMirrorNodeToUnistNodes(_node: Node, convertedChildren: UnistNode[]): TableHeader[] {
    // Emit mdast tableCell: gfmTableToMarkdown treats the first row as the
    // header by convention, and mdast has no distinct header type. The
    // NodeExtension<TableHeader> generic forces the return type, so we cast
    // the tableCell shape at the return boundary — localized to this one line.
    const paragraph = convertedChildren[0] as Parent | undefined
    const cell: TableCell = {
      type: "tableCell",
      children: (paragraph?.children ?? []) as PhrasingContent[],
    }
    return [cell] as unknown as TableHeader[]
  }

  unistNodeName(): "tableHeader" {
    return "tableHeader"
  }

  unistToProseMirrorTest(node: UnistNode): boolean {
    return node.type === "tableHeader"
  }

  unistNodeToProseMirrorNodes(_node: TableHeader, schema: Schema<string, string>, convertedChildren: Node[]): Node[] {
    const paragraph = schema.nodes.paragraph.create(null, convertedChildren)
    return [schema.nodes.table_header.create(null, [paragraph])]
  }
}
