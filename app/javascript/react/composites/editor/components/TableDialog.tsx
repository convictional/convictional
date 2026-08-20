import { addColumnAfter, addRowAfter, deleteColumn, deleteRow, deleteTable } from "prosemirror-tables"

import { useEditorActions } from "../useEditorActions"
import { ToolButton } from "./ToolButton"

interface TableDialogProps {
  inTable: boolean
  onClose: () => void
}

export function TableDialog({ inTable, onClose }: TableDialogProps) {
  const { runCmd, insertTable, canDeleteRow, canDeleteColumn } = useEditorActions()

  if (!inTable) {
    return (
      <div className="absolute left-0 top-full mt-1 floating-card !p-3 z-50 w-48">
        <button
          type="button"
          className="btn btn-sm btn-ghost w-full justify-start gap-2"
          onMouseDown={e => {
            e.preventDefault()
            insertTable()
            onClose()
          }}
        >
          <span className="material-symbols-outlined !text-lg">table</span>
          Insert 3×3 table
        </button>
      </div>
    )
  }

  return (
    <div className="absolute left-0 top-full mt-1 floating-card !p-2 z-50 flex items-center gap-0.5">
      <ToolButton icon="add_row_below" title="Add row" size="sm" onMouseDown={() => runCmd(addRowAfter)} />
      <ToolButton icon="add_column_right" title="Add column" size="sm" onMouseDown={() => runCmd(addColumnAfter)} />
      <div className="border-l border-base-300 h-5 mx-0.5" />
      <ToolButton
        icon="remove"
        title="Delete row"
        size="sm"
        disabled={!canDeleteRow()}
        onMouseDown={() => runCmd(deleteRow)}
      />
      <ToolButton
        icon="splitscreen_left"
        title="Delete column"
        size="sm"
        disabled={!canDeleteColumn()}
        onMouseDown={() => runCmd(deleteColumn)}
      />
      <div className="border-l border-base-300 h-5 mx-0.5" />
      <ToolButton
        icon="grid_off"
        title="Delete table"
        size="sm"
        onMouseDown={() => {
          runCmd(deleteTable)
          onClose()
        }}
      />
    </div>
  )
}
