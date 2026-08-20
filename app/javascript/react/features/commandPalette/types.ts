// Palette-specific types. Lookup response shapes are shared with the mobile
// search overlay and live in ~/react/shared/lookup.

export type { FilterMeta, LookupResult, LookupResults } from "~/react/shared/lookup"

export interface Collaborator {
  id: string
  display_name: string
}

export interface RecentItem {
  workspace_id: string
  resource_type: string
  title: string
  url: string
  updated_at: string
  collaborators: Collaborator[]
  preview: string | null
}

export interface Command {
  key: string
  type: string
  label: string
  description: string | null
  url: string | null
  options: { open_in_new_tab?: boolean; editable?: boolean } | null
  quick_link_id: string | null
}

export interface QuickLink {
  id: string
  label: string
  url: string
  open_in_new_tab: boolean
}

export interface ResearchQuestion {
  id: string
  body: string
  title: string | null
  created_at: string
}

export type Mode = "recent" | "search" | "commands" | "active"
