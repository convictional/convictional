// Mirrors `app.routers.api.schemas.OrganizationResponse`. `system_prompt` is
// *omitted* (undefined) for non-superusers, `null` only for a superuser with no
// prompt set — see the schema's comment.
export interface OrganizationData {
  id: string
  name: string | null
  system_prompt?: string | null
}
