import type { ReactNode } from "react"

interface SettingsGroupProps {
  title?: string
  children: ReactNode
}

// A titled group of related settings rows joined into one bordered, divided
// card — the settings page is a stack of these (Account, Integrations, etc.),
// mirroring the notification settings card.
export function SettingsGroup({ title, children }: SettingsGroupProps) {
  return (
    <section className="space-y-2">
      {title && <h2 className="text-sm font-semibold text-base-content/60 px-1">{title}</h2>}
      <div className="rounded-2xl border border-base-300 divide-y divide-base-300 overflow-hidden">{children}</div>
    </section>
  )
}
