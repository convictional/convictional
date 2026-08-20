import { useQueryClient } from "@tanstack/react-query"
import { useState } from "react"

import { SaveForm } from "~/react/composites/settings/SaveForm"
import { SettingsSection } from "~/react/composites/settings/SettingsSection"
import { apiFetch } from "~/react/shared/apiFetch"
import { showFlash } from "~/shared/flash"

import { organizationQueryOptions } from "../queries"
import type { OrganizationData } from "../types"

// The org name field. Seeded from the parent's GET /api/organization, saved via
// PATCH. `name` is nullable on the model, so a null initial value shows as empty.
export function BasicsSection({ initialName }: { initialName: string | null }) {
  const queryClient = useQueryClient()
  const [name, setName] = useState(initialName ?? "")

  async function save() {
    const updated = await apiFetch<OrganizationData>("/api/organization", {
      method: "PATCH",
      body: JSON.stringify({ name }),
    })
    setName(updated.name ?? "")
    // Refresh the org cache in the background — it's not on the save's critical
    // path, so don't make the success flash wait for the refetch. exact: the
    // updates-configuration query is keyed under ["organization", …]; a prefix
    // match would needlessly refetch it when only the org changed.
    void queryClient.invalidateQueries({ queryKey: organizationQueryOptions.queryKey, exact: true })
    showFlash("Organization name saved.", "success")
  }

  return (
    <SettingsSection title="Basics">
      <SaveForm onSave={save} errorMessage="Could not save the name. Please try again.">
        <div className="fieldset">
          <label className="label" htmlFor="organization_name">
            <span className="label-text">Name</span>
          </label>
          <input
            className="input input-sm w-full bg-base-200 placeholder-base-500"
            id="organization_name"
            name="name"
            type="text"
            required
            placeholder="Organization name"
            value={name}
            onChange={e => setName(e.target.value)}
          />
        </div>
      </SaveForm>
    </SettingsSection>
  )
}
