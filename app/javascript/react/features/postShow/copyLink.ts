import { copyToClipboard } from "~/react/shared/clipboard"

export function copyCommentLink(commentId: string) {
  const url = new URL(window.location.href)
  url.hash = `comment-${commentId}`
  return copyToClipboard(url.toString(), { successMessage: "Link copied", errorMessage: "Couldn't copy link" })
}
