import { CONTENT_TYPE_ICONS } from "~/react/shared/contentTypes"

const COMMAND_TYPE_ICONS: Record<string, string> = {
  research: "lab_research",
  create_quick_link: "add_link",
  quick_link: "link",
}

export function iconForCommandType(type: string): string {
  return COMMAND_TYPE_ICONS[type] || "command"
}

export function iconForContentType(contentType: string): string {
  return CONTENT_TYPE_ICONS[contentType] || "description"
}

// resource_type → content_type key (only "emailthread" differs from API form)
const RESOURCE_TYPE_KEY: Record<string, string> = { emailthread: "email_thread" }

export function iconForResourceType(resourceType: string): string {
  const normalized = resourceType.toLowerCase().replace(/[^a-z0-9]/g, "")
  return CONTENT_TYPE_ICONS[RESOURCE_TYPE_KEY[normalized] ?? normalized] || "description"
}
