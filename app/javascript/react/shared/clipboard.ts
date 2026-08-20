import { showFlash } from "~/shared/flash"

interface CopyToClipboardOptions {
  successMessage: string
  errorMessage: string
}

// Copy text and flash the outcome. navigator.clipboard is undefined on insecure
// origins and in some private-browsing modes, so we always flash rather than
// throw. Shared by every "copy" affordance (action sheets, copy-link menus) so
// the guard and flash behavior stay consistent.
export async function copyToClipboard(text: string, { successMessage, errorMessage }: CopyToClipboardOptions) {
  if (!navigator.clipboard) {
    showFlash(errorMessage, "error")
    return
  }
  try {
    await navigator.clipboard.writeText(text)
    showFlash(successMessage, "success")
  } catch {
    showFlash(errorMessage, "error")
  }
}
