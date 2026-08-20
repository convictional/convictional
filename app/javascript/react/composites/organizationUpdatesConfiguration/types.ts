// Mirrors `app.routers.api.schemas.UpdatesConfigurationResponse`. The schedule
// fields are null until a schedule is configured (no raw cron is exposed), and
// day_of_week is also null for monthly schedules.
export type UpdateFrequency = "weekly" | "monthly"

export interface UpdatesConfiguration {
  frequency: UpdateFrequency | null
  hour: number | null
  day_of_week: string | null
  goal_update_question: string
  has_goals: boolean
  // Updates only actually send when a schedule, a question, and open goals all exist.
  enabled: boolean
}
