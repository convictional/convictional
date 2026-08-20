export interface StatusOption {
  value: string
  text: string
  // Full chip styling (background + text + border) for the pill presentation.
  classes: string
  // Text colour only, for presentations that show the status as plain text (e.g. timeline updates).
  textClass: string
}

export const STATUS_OPTIONS: StatusOption[] = [
  {
    value: "on_track",
    text: "On Track",
    classes: "bg-success/30 text-success-content border-success-content/20",
    textClass: "text-success-content",
  },
  {
    value: "at_risk",
    text: "At Risk",
    classes: "bg-warning/30 text-warning-content border-warning-content/20",
    textClass: "text-warning-content",
  },
  {
    value: "off_track",
    text: "Off Track",
    classes: "bg-error/30 text-error-content border-error-content/20",
    textClass: "text-error-content",
  },
]

export const STATUS_CONFIG: Record<string, StatusOption> = Object.fromEntries(STATUS_OPTIONS.map(s => [s.value, s]))
