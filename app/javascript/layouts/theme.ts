import type { Stores } from "alpinejs"

import { getCurrentTheme, getThemeSetting, setThemeSetting, subscribeToTheme } from "../shared/themeApplicator"

// Thin Alpine wrapper over `themeApplicator`, kept for non-migrated consumers
// (emailThreads/content.ts, public.html.jinja). All state lives in the
// applicator; this just mirrors it onto the Alpine
// store so x-data templates can keep reading `$store.theme.current` and
// `$store.theme.setting`.
export interface ThemeStore extends Stores {
  setting: string
  current: string
  setTheme: (value?: string) => void
}

export const createThemeStore = (): ThemeStore => ({
  setting: getThemeSetting(),
  current: getCurrentTheme(),
  init() {
    subscribeToTheme(() => {
      this.setting = getThemeSetting()
      this.current = getCurrentTheme()
    })
  },
  setTheme(value?: string) {
    if (value === "system" || value === "light" || value === "dark") {
      setThemeSetting(value)
    }
    this.setting = getThemeSetting()
    this.current = getCurrentTheme()
  },
})
