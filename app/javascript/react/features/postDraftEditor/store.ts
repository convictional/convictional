import { createCommentUIStore } from "~/react/composites/editor/features/comments/createCommentUIStore"

export const postDraftCommentUIStore = createCommentUIStore()

export const postDraftCommentsPath = (postId: string) => `/api/posts/${postId}/draft/comments`
