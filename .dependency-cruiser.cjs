// Enforces the Alpine/React seam during the migration and the layering inside
// react/. Layering (one-way, top-down):
//
//   app (route tree) → features (islands) → composites → ui
//                                        ↘            ↘
//                                         shared (hooks, stores, utilities)
//
// - ui/ is the bottom: pure React components with no domain knowledge,
//   no app state, no API calls. Imports nothing else in react/.
// - composites/ holds domain-aware reusable UI (editor, markdown, dialogs,
//   chat composer, message bubble, comment threads, etc.). Imports ui/ and
//   shared/. Composites may import each other.
// - shared/ holds cross-cutting hooks, stores, and utilities (apiFetch,
//   types, reactions, channel hooks). Imports ui/. Cannot import composites
//   or features.
// - features/ contains one dir per island. Islands are sealed from each
//   other but can import ui/, composites/, and shared/.
// - app/ is the top: the TanStack Router route tree, the one place allowed to
//   import across features/. Nothing below it may import app/ — features get
//   route type-safety via the global Register augmentation, not by importing
//   the tree (see docs/react-migration.md → Client-Side Router ADR).

const LEGACY_MODULES =
  "(commands|emailContacts|emailDrafts|emailThreads|goals|layouts|meetingsCollections|onboarding|posts|pwaInstall|users)"

/** @type {import('dependency-cruiser').IConfiguration} */
module.exports = {
  forbidden: [
    {
      name: "no-circular",
      severity: "error",
      from: {},
      to: { circular: true },
    },

    {
      name: "no-orphans",
      severity: "warn",
      comment:
        "Catches files nothing imports — useful for spotting leftovers as Alpine modules get deleted. Entry points (main.ts, mount files), config, and type declaration files are exempt.",
      from: {
        orphan: true,
        pathNot: "(\\.d\\.ts$|/main\\.ts$|/mount\\.tsx?$|vite\\.config|eslint\\.config|\\.dependency-cruiser|vitest\\.config|vitest\\.setup)",
      },
      to: {},
    },

    {
      name: "react-not-from-legacy",
      severity: "error",
      from: { path: `^app/javascript/${LEGACY_MODULES}/` },
      to: { path: "^app/javascript/react/" },
    },

    {
      name: "legacy-not-from-react",
      severity: "error",
      from: { path: "^app/javascript/react/" },
      to: { path: `^app/javascript/${LEGACY_MODULES}/` },
    },

    {
      name: "app-is-the-top",
      severity: "error",
      comment:
        "react/app/ is the route-tree top layer. It may import features/composites/shared/ui, but nothing below it may import app/. Features get route type-safety via the global Register augmentation in react/app/router.tsx, never by importing the tree. Inert until react/app/ is imported from below.",
      from: { path: "^app/javascript/react/(ui|shared|composites|features)/" },
      to: { path: "^app/javascript/react/app/" },
    },

    {
      name: "ui-is-the-bottom",
      severity: "error",
      comment:
        "react/ui/ is the foundation. It must not import anything else from react/. No domain knowledge, no app state, no API calls. If a UI component needs anything from shared/ or composites/, it doesn't belong in ui/ — promote it to composites/.",
      from: { path: "^app/javascript/react/ui/" },
      to: { path: "^app/javascript/react/(?!ui/)([^/]+)/" },
    },

    {
      name: "ui-stays-pure",
      severity: "error",
      comment:
        "ui/ components are pure rendering. They must not subscribe to realtime channels, own Zustand stores, or pull data fetching libraries — those belong in composites/ or above. ui-is-the-bottom already blocks anything in react/; this extends the discipline to external state/realtime plumbing that doesn't live under react/.",
      from: { path: "^app/javascript/react/ui/" },
      to: { path: "^(app/javascript/channels/|node_modules/(zustand|@tanstack/(query|react-query)))" },
    },

    {
      name: "ui-hooks-live-in-ui-hooks",
      severity: "error",
      comment:
        "use*.ts(x) files anywhere under react/ui/ must live in ui/hooks/. Mirrors the discipline applied to shared/hooks/. Keeps hooks discoverable and prevents them from leaking sideways into component files. Matched in `to:` so the rule fires on incoming edges — `from:` would miss hooks with zero outgoing imports.",
      from: {},
      to: {
        path: [
          "^app/javascript/react/ui/use[A-Z][^/]*\\.tsx?$",
          "^app/javascript/react/ui/[^/]+/use[A-Z][^/]*\\.tsx?$",
        ],
        pathNot: "^app/javascript/react/ui/hooks/",
      },
    },

    {
      name: "ui-components-live-at-ui-root",
      severity: "error",
      comment:
        "PascalCase .tsx files under react/ui/ must live at ui/ root, not in subdirs. ui/ stays intentionally flat; the only nested dir is ui/hooks/ (for hooks, not components). Forces ui/ to remain a clear, discoverable surface of pure UI components. Matched in `to:` so the rule fires on incoming edges.",
      from: {},
      to: {
        path: "^app/javascript/react/ui/[^/]+/[A-Z][^/]*\\.tsx$",
      },
    },

    {
      name: "composites-cannot-import-features",
      severity: "error",
      comment:
        "react/composites/ is reusable across multiple islands; it must not reach into any specific feature island. Composites may import ui/, shared/, and each other.",
      from: { path: "^app/javascript/react/composites/" },
      to: { path: "^app/javascript/react/features/" },
    },

    {
      name: "islands-are-sealed",
      severity: "error",
      comment:
        "Feature islands are sealed from each other. Hoist anything genuinely shared to shared/ (cross-cutting utilities), ui/ (pure UI), or composites/ (domain-aware reusable UI).",
      from: { path: "^app/javascript/react/features/([^/]+)/" },
      to: {
        path: "^app/javascript/react/features/([^/]+)/",
        pathNot: "^app/javascript/react/features/$1/",
      },
    },

    {
      name: "platform-shared-is-framework-agnostic",
      severity: "error",
      from: { path: "^app/javascript/(channels|shared|types)/" },
      to: { path: "^(app/javascript/react/|node_modules/(react|react-dom)(/|$))" },
    },

    {
      name: "shared-cannot-import-islands-or-composites",
      severity: "error",
      comment:
        "react/shared is cross-cutting infrastructure (hooks, stores, utilities). It can import ui/ but must not reach into composites/ or feature islands — those are above it in the layering.",
      from: { path: "^app/javascript/react/shared/" },
      to: { path: "^app/javascript/react/(?!shared|ui)[^/]+/" },
    },

    {
      name: "hooks-live-in-shared-hooks",
      severity: "error",
      comment:
        "Files matching use*.ts(x) anywhere under react/shared/ must live in shared/hooks/, including hooks co-located with components. Matched in `to:` so the rule fires on every incoming edge — a `from:` match silently misses hooks with zero outgoing imports.",
      from: {},
      to: {
        path: [
          "^app/javascript/react/shared/use[A-Z][^/]*\\.tsx?$",
          "^app/javascript/react/shared/[^/]+/use[A-Z][^/]*\\.tsx?$",
        ],
        pathNot: "^app/javascript/react/shared/hooks/",
      },
    },

    {
      name: "hooks-live-in-composites-hooks",
      severity: "error",
      comment:
        "Files matching use*.ts(x) at react/composites/ root must live in composites/hooks/. Mirrors the shared/hooks/ discipline. Sub-libraries (e.g. composites/editor/) keep their internal hook organization — this rule only polices the composites root. Matched in `to:` so the rule fires on every incoming edge; a `from:` match silently misses hooks with zero outgoing imports.",
      from: {},
      to: {
        path: "^app/javascript/react/composites/use[A-Z][^/]*\\.tsx?$",
        pathNot: "^app/javascript/react/composites/hooks/",
      },
    },

    {
      name: "hooks-dont-import-react-dom",
      severity: "error",
      comment:
        "Hooks should return values, not manipulate the DOM directly. Use refs and effects instead. If a UI component genuinely needs createPortal, it's a component, not a hook. Applies to both shared/hooks/ and ui/hooks/.",
      from: { path: "^app/javascript/react/(shared|ui)/hooks/" },
      to: { path: "node_modules/react-dom(/|$)" },
    },

    {
      name: "no-alpine-in-react",
      severity: "error",
      from: { path: "^app/javascript/react/" },
      to: { path: "node_modules/(alpinejs|@alpinejs|@ryangjchandler|htmx\\.org|htmx-ext-)" },
    },
  ],

  options: {
    tsConfig: { fileName: "tsconfig.json" },
    tsPreCompilationDeps: true,
    enhancedResolveOptions: {
      exportsFields: ["exports"],
      conditionNames: ["import", "require", "node", "default"],
    },
    doNotFollow: { path: "node_modules" },
    progress: { type: "none" },
    reporterOptions: {
      text: { highlightFocused: true },
    },
  },
}
