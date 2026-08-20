import { useSyncExternalStore } from "react"

import {
  type ResolvedTheme,
  type ThemeSetting,
  getCurrentTheme,
  getThemeSetting,
  setThemeSetting,
  subscribeToTheme,
} from "~/shared/themeApplicator"

interface UseThemeReturn {
  setting: ThemeSetting
  current: ResolvedTheme
  setTheme: (value: ThemeSetting) => void
}

// React-side wrapper over the vanilla theme module. `useSyncExternalStore`
// keeps the rendered value in sync with external sources — another tab via
// storage event, or the OS-preference matchMedia listener for "system" mode.
export function useTheme(): UseThemeReturn {
  const setting = useSyncExternalStore(subscribeToTheme, getThemeSetting, getThemeSetting)
  const current = useSyncExternalStore(subscribeToTheme, getCurrentTheme, getCurrentTheme)
  return { setting, current, setTheme: setThemeSetting }
}
