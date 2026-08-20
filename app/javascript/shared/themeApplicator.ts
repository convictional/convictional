// Single source of truth for the app theme. Both the Alpine `$store.theme`
// wrapper and the React `useTheme` hook delegate here, so localStorage and the
// `<html data-theme>` attribute have exactly one writer. This module runs at
// import time (eagerly imported from main.ts), which sets `data-theme` before
// Alpine boots and eliminates a small FOUC the old Alpine-only path had.

const STORAGE_KEY = "themeSetting"
const DARK_THEME_VALUE = "convictional-dark"
const LIGHT_THEME_VALUE = "convictional-light"

export type ThemeSetting = "system" | "light" | "dark"
export type ResolvedTheme = "light" | "dark"

const listeners = new Set<() => void>()

function readSettingFromStorage(): ThemeSetting {
  const raw = typeof localStorage !== "undefined" ? localStorage.getItem(STORAGE_KEY) : null
  return raw === "light" || raw === "dark" ? raw : "system"
}

function resolve(setting: ThemeSetting): ResolvedTheme {
  if (setting !== "system") return setting
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return "light"
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"
}

function applyToDocument(theme: ResolvedTheme): void {
  if (typeof document === "undefined") return
  document.documentElement.dataset.theme = theme === "dark" ? DARK_THEME_VALUE : LIGHT_THEME_VALUE
}

let currentSetting: ThemeSetting = readSettingFromStorage()
let currentTheme: ResolvedTheme = resolve(currentSetting)
applyToDocument(currentTheme)

function notify(): void {
  for (const fn of listeners) fn()
}

if (typeof window !== "undefined" && typeof window.matchMedia === "function") {
  const mq = window.matchMedia("(prefers-color-scheme: dark)")
  mq.addEventListener("change", () => {
    if (currentSetting !== "system") return
    currentTheme = resolve(currentSetting)
    applyToDocument(currentTheme)
    notify()
  })
}

if (typeof window !== "undefined") {
  // Cross-tab sync: another tab calls setTheme → storage event fires here.
  window.addEventListener("storage", event => {
    if (event.key !== STORAGE_KEY) return
    currentSetting = readSettingFromStorage()
    currentTheme = resolve(currentSetting)
    applyToDocument(currentTheme)
    notify()
  })
}

export function getThemeSetting(): ThemeSetting {
  return currentSetting
}

export function getCurrentTheme(): ResolvedTheme {
  return currentTheme
}

export function setThemeSetting(setting: ThemeSetting): void {
  currentSetting = setting
  if (typeof localStorage !== "undefined") {
    localStorage.setItem(STORAGE_KEY, setting)
  }
  currentTheme = resolve(setting)
  applyToDocument(currentTheme)
  notify()
}

export function subscribeToTheme(fn: () => void): () => void {
  listeners.add(fn)
  return () => {
    listeners.delete(fn)
  }
}
