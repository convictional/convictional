import { createCommentUIStore } from "~/react/composites/editor/features/comments/createCommentUIStore"

export const documentCommentUIStore = createCommentUIStore()

export const documentCommentsPath = (documentId: string) => `/api/documents/${documentId}/comments`
