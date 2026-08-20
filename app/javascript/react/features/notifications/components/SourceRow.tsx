import { useEffect, useState } from "react"
import { sourceMetaFor, type SourceMeta } from "~/react/shared/notificationSources"
import type { NotificationLevel, NotificationPreference } from "../types"

interface Props {
  preference: NotificationPreference
  onChange: (level: NotificationLevel) => Promise<void>
  children?: React.ReactNode
}

interface LevelOption {
  level: NotificationLevel
  label: string
  description: string
}

function levelsFor(meta: SourceMeta): LevelOption[] {
  const options: LevelOption[] = [{ level: "all", label: "All", description: meta.allDescription }]
  if (meta.broadcastsLabel && meta.broadcastsDescription) {
    options.push({
      level: "broadcasts",
      label: meta.broadcastsLabel,
      description: meta.broadcastsDescription,
    })
  }
  options.push({ level: "relevant_only", label: "Relevant to me", description: meta.relevantDescription })
  return options
}

export function SourceRow({ preference, onChange, children }: Props) {
  const meta = sourceMetaFor(preference.resource_type)
  const [showCheck, setShowCheck] = useState(false)

  useEffect(() => {
    if (!showCheck) return
    const id = setTimeout(() => setShowCheck(false), 1500)
    return () => clearTimeout(id)
  }, [showCheck])

  if (!meta) return null

  async function handleSelect(level: NotificationLevel) {
    if (level === preference.default_level) return
    await onChange(level)
    setShowCheck(true)
  }

  return (
    <section className="px-4 py-2.5 bg-base-50">
      <div className="flex flex-col md:flex-row md:gap-6 md:items-start">
        <div className="mb-3 md:mb-0 md:w-40 md:flex-shrink-0 md:pt-1">
          <div className="flex items-center gap-2">
            <span className="material-symbols-outlined text-lg shrink-0 text-base-content/70" aria-hidden>
              {meta.icon}
            </span>
            <h3 className="text-sm font-semibold">{meta.label}</h3>
            {showCheck && (
              <span className="material-symbols-outlined text-base text-success ml-auto" aria-label="Saved">
                check
              </span>
            )}
          </div>
          {meta.note && <p className="text-xs text-base-content/60 mt-0.5">{meta.note}</p>}
        </div>

        <div className="flex-1 min-w-0">
          <div className="space-y-2">
            {levelsFor(meta).map(({ level, label, description }) => {
              const isSelected = preference.default_level === level
              return (
                <label key={level} className="flex gap-3 cursor-pointer items-start">
                  <input
                    type="radio"
                    name={`level-${preference.resource_type}`}
                    className={`radio radio-sm mt-0.5 ${isSelected ? "radio-primary" : "hover:radio-primary"}`}
                    checked={isSelected}
                    onChange={() => handleSelect(level)}
                  />
                  <div className="flex-1">
                    <div className={`text-sm font-semibold ${isSelected ? "" : "text-base-content/60"}`}>{label}</div>
                    <div className={`text-xs ${isSelected ? "text-base-content/70" : "text-base-content/50"}`}>
                      {description}
                    </div>
                  </div>
                </label>
              )
            })}
          </div>
        </div>
      </div>

      {children && <div className="mt-3">{children}</div>}
    </section>
  )
}
