import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import {
  render as rtlRender,
  renderHook as rtlRenderHook,
  type RenderHookOptions,
  type RenderOptions,
} from "@testing-library/react"
import { type ReactElement, type ReactNode } from "react"

import { queryClient } from "~/react/shared/queryClient"

// Re-export RTL so test files import screen/fireEvent/waitFor/etc. from here too.
export * from "@testing-library/react"

// A fresh client for tests that exercise fetching in isolation (no shared cache
// across tests). Mirrors the production client's lone global default (retry: false,
// so a rejected query surfaces immediately instead of hanging on Query's retry/
// backoff); the channel-first posture rides each query's options, not the client.
// gcTime: Infinity keeps cached data alive for the duration of a test.
export function createTestQueryClient(): QueryClient {
  return new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } })
}

function wrapper(client: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>
  }
}

// Production mounts every root against the queryClient singleton; these mirror
// that so fixtures seeding the singleton cache (currentUserFixtures) are visible
// to the rendered tree.
export function render(ui: ReactElement, options?: Omit<RenderOptions, "wrapper">) {
  return rtlRender(ui, { wrapper: wrapper(queryClient), ...options })
}

export function renderHook<Result, Props>(
  callback: (props: Props) => Result,
  options?: Omit<RenderHookOptions<Props>, "wrapper">
) {
  return rtlRenderHook(callback, { wrapper: wrapper(queryClient), ...options })
}

// For tests that want an isolated fresh client instead of the singleton.
export function renderWithClient(ui: ReactElement, client: QueryClient = createTestQueryClient()) {
  return { client, ...rtlRender(ui, { wrapper: wrapper(client) }) }
}

export function renderHookWithClient<Result, Props>(
  callback: (props: Props) => Result,
  client: QueryClient = createTestQueryClient()
) {
  return { client, ...rtlRenderHook(callback, { wrapper: wrapper(client) }) }
}
