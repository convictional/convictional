import type { ReactNode } from "react"

interface SettingsSectionProps {
  title: ReactNode
  description?: ReactNode
  children: ReactNode
}

// A settings row: a left label/description column and a right content column,
// sized to sit inside a bordered `divide-y` card (matching the notification
// settings design). Each settings section is self-chroming with this.
export function SettingsSection({ title, description, children }: SettingsSectionProps) {
  return (
    <section className="px-4 py-5 bg-base-50">
      <div className="flex flex-col md:flex-row md:gap-6 md:items-start">
        <div className="mb-3 md:mb-0 md:w-56 md:flex-shrink-0 md:pt-1">
          <p className="text-sm font-semibold flex items-center gap-2">{title}</p>
          {description && <p className="text-xs text-base-content/60 mt-1">{description}</p>}
        </div>
        <div className="flex-1 min-w-0 space-y-4">{children}</div>
      </div>
    </section>
  )
}
