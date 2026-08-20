import { useIsMobile } from "~/react/shared/hooks/useIsMobile"

import { DOC_TEMPLATES, type DocTemplate } from "../templates"

// The Google-Docs-style "Start a new document" row above the docs list. Each card creates a doc
// from that template (see DocumentsIndex). Simple icon tiles rather than rendered previews.
export function DocumentTemplates({
  onSelect,
  disabled,
}: {
  onSelect: (template: DocTemplate) => void
  disabled?: boolean
}) {
  // The template tiles need the width to sit side by side; hidden on mobile in favor of the list.
  if (useIsMobile()) return null

  return (
    <div className="mb-8">
      <p className="px-3 pt-2 pb-2 text-xs font-semibold text-base-600">Start a new document</p>
      <div className="flex gap-3 overflow-x-auto px-3 pb-1">
        {DOC_TEMPLATES.map(template => (
          <button
            key={template.key}
            type="button"
            onClick={() => onSelect(template)}
            disabled={disabled}
            className="group w-28 shrink-0 cursor-pointer text-center disabled:cursor-not-allowed disabled:opacity-50"
          >
            <div className="flex aspect-[3/4] items-center justify-center rounded-xl border border-base-300 bg-base-50 shadow-xs transition-colors group-hover:border-primary/40 group-hover:bg-base-100">
              <span
                className={`material-symbols-outlined text-2xl ${
                  template.key === "blank" ? "text-primary" : "text-base-content/50"
                }`}
              >
                {template.icon}
              </span>
            </div>
            <div className="mt-2 text-xs font-medium text-base-content">{template.label}</div>
          </button>
        ))}
      </div>
    </div>
  )
}
