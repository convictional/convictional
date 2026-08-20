import { useQueryClient } from "@tanstack/react-query"
import { useRef } from "react"

import { SaveForm } from "~/react/composites/settings/SaveForm"
import { SettingsSection } from "~/react/composites/settings/SettingsSection"
import { apiFetch } from "~/react/shared/apiFetch"
import { showFlash } from "~/shared/flash"

import { organizationQueryOptions } from "../queries"
import type { OrganizationData } from "../types"
import { SystemPromptEditor, type SystemPromptEditorHandle } from "./SystemPromptEditor"

// The superuser-only "Support Fields" system prompt. Markdown in, markdown out —
// no HTML conversion. The endpoint additionally enforces superuser server-side.
export function SystemPromptSection({ initialContent }: { initialContent: string }) {
  const queryClient = useQueryClient()
  const editorRef = useRef<SystemPromptEditorHandle | null>(null)

  async function save() {
    const content = editorRef.current?.getContent() ?? ""
    await apiFetch<OrganizationData>("/api/organization", {
      method: "PATCH",
      body: JSON.stringify({ system_prompt: content }),
    })
    // Background refresh, off the save's critical path. exact: see BasicsSection —
    // avoid a prefix match refetching the updates configuration.
    void queryClient.invalidateQueries({ queryKey: organizationQueryOptions.queryKey, exact: true })
    showFlash("System prompt saved.", "success")
  }

  return (
    <SettingsSection title="Support Fields" description={<span>These fields can only be seen by super users</span>}>
      <SaveForm onSave={save} errorMessage="Could not save the system prompt. Please try again.">
        <div className="fieldset">
          <label className="label">
            <span className="label-text">System prompt</span>
          </label>
          <SystemPromptEditor
            ref={editorRef}
            initialContent={initialContent}
            placeholder="The system prompt for this organization"
          />
        </div>
      </SaveForm>
    </SettingsSection>
  )
}
