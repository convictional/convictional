import { CollectionForm } from "~/react/composites/meetings/CollectionForm"
import { Dialog } from "~/react/ui/Dialog"

interface NewCollectionDialogProps {
  isOpen: boolean
  onClose: () => void
  onCreate: (title: string, description: string | null) => Promise<string | null>
}

export function NewCollectionDialog({ isOpen, onClose, onCreate }: NewCollectionDialogProps) {
  return (
    <Dialog
      isOpen={isOpen}
      onClose={onClose}
      ariaLabel="New collection"
      className="bg-base-100 rounded-2xl shadow-xl w-full max-w-md p-6"
    >
      <h2 className="text-lg font-semibold mb-4">New collection</h2>
      <CollectionForm
        submitLabel="Create"
        onSubmit={async (title, description) => {
          const err = await onCreate(title, description)
          if (!err) onClose()
          return err
        }}
        onCancel={onClose}
      />
    </Dialog>
  )
}
