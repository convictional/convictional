import { type RegisteredRouter, useRouter } from "@tanstack/react-router"

// Returns the TanStack router when rendered inside a RouterProvider (SPA shell),
// or undefined on legacy Jinja pages (htmx island mode). This is the single
// island-vs-shell discriminator: components branch on `router ? shell : island`.
//
// `useRouter` is typed to return the router non-optionally, but at runtime it
// reads context and returns undefined outside a provider (with `warn: false`
// suppressing the dev console warning). Centralizing the cast keeps that
// undocumented behavior asserted in one place rather than at each call site.
export function useOptionalRouter(): RegisteredRouter | undefined {
  return useRouter({ warn: false }) as RegisteredRouter | undefined
}
