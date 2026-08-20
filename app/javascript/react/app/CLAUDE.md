# Route tree (`react/app/`)

The TanStack Router route tree and SPA shell. `docs/react-migration.md` → "Client-Side Router (ADR)" is the authority — read it before changing the routing foundation or cutting a page over. This file is the checklist for the steps that span files, where forgetting one fails **silently** rather than as a type error.

`routes/notifications.tsx` is the worked reference for a route definition.

## Adding or cutting over a route

1. **Route file** — one per route at `routes/<name>.tsx`: `createRoute({ getParentRoute: () => shellRoute, path, component })`. Import the page only as a *component*; the feature must stay unaware it's a route (that's what keeps the `app/` seal exception-free).
2. **Code-split with `lazyRouteComponent`**, not a second `route.lazy.tsx` file and not `createLazyRoute` — that split was walked back for duplicating the path as a brittle route-id string. `createLazyRoute` is still correct only when the *whole* route, loader included, must be lazy.
3. **Attach to the tree** in `router.tsx`, nested under `shellRoute`.
4. **Register the path server-side** in `SPA_ROUTES` (`app/routers/spa.py`). Until you do, the server keeps serving the Jinja page and the new route never runs — nothing type-errors. Include the route name if anything resolves the path via `url_for`; the list's comments say which do and why.
5. **Retire the Jinja page** — template, island `mount.ts` and its `main.ts` import, HTML route handler. Any surviving `url_for('<old_route_name>')` will raise once the named route is gone.
6. **Test with a `createMemoryHistory` router** (TanStack has no `MemoryRouter`). See `tests/javascript/react/features/documentShow/DocumentShow.test.tsx`.

Guards go in `beforeLoad` using `redirectToLogin` / `redirectToOnboarding` from `shared/routerGuards.ts` — route-level only for page-specific guards, since the shell already handles auth and onboarding. Titles use `useDocumentTitle` (`shared/hooks/useDocumentTitle.ts`), which reproduces the server's `format_page_title` including the environment prefix.

## The shell is hand-maintained

`app/templates/layouts/spa.html.jinja` is a hand-maintained subset of `application.html.jinja`. React code that reads server-computed values straight off the document — `csrf-token`, `page-title-prefix`, `data-is-mobile`, `window.EMAIL_CSS_URL` — only works on client routes if the shell carries them.

**Adding a new server→DOM read means adding it to the shell and asserting it in the shell test.** Otherwise it degrades quietly: absent `data-is-mobile` reads as desktop on every device, across 40+ components.

## Server state

Server state belongs in the TanStack Query cache, kept live by patching from channel handlers (`queryClient.setQueryData` on a `DataMessage`) — channel-first, `staleTime: Infinity`, not background refetch. Zustand and local state are for UI and ephemeral realtime only (open/editing/draft/hover, presence, typing). Never add a new hand-rolled server-state store; `composites/editor/features/comments/commentThreads.ts` is the canonical migration away from one.
