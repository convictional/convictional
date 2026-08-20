import globals from "globals";
import pluginJs from "@eslint/js";
import pluginRouter from "@tanstack/eslint-plugin-router";
import importPlugin from "eslint-plugin-import";
import reactHooks from "eslint-plugin-react-hooks";
import tseslint from "typescript-eslint";
import eslintPluginPrettier from "eslint-config-prettier";

export default tseslint.config(
  pluginJs.configs.recommended,
  importPlugin.flatConfigs.recommended,
  tseslint.configs.recommended,
  eslintPluginPrettier,
  {
    ignores: [
      "node_modules/*",
      "static/*",
      "tailwind.config.js",
    ]
  },
  {
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      globals: {
        ...globals.browser,
        Alpine: "readonly",
      },
      parserOptions: {
        project: './tsconfig.json',
        tsconfigRootDir: import.meta.dirname
      }
    }
  },
  {
    plugins: {
      "react-hooks": reactHooks,
    },
    rules: {
      camelcase: ["error", { properties: "never" }],
      ...reactHooks.configs.recommended.rules,
      // The React Compiler is this rule's only consumer: it reports that the
      // compiler couldn't prove a useMemo/useCallback is safe to preserve, never
      // that the code is wrong. No compiler is installed here (no
      // babel-plugin-react-compiler; vite.config.ts uses plain
      // @vitejs/plugin-react), so it has nothing to report against. Turn it back
      // on as part of adopting the compiler and re-derive the findings then.
      "react-hooks/preserve-manual-memoization": "off",
      // eslint-plugin-react-hooks 7.1 promoted these React Compiler checks to
      // errors in its recommended preset. Deferred to warn so the toolchain bump
      // wasn't blocked on the refactor; each flips to error as its group closes.
      // See docs/plans/2026-07-27-001-refactor-react-hooks-lint-warnings-plan.md.
      "react-hooks/refs": "warn",
      "react-hooks/set-state-in-effect": "warn",
      "import/order": [
        "error",
        {
          "groups": ["builtin", "external", "internal", "parent", "sibling", "index"],
          "alphabetize": { "order": "asc", "caseInsensitive": true }
        }
      ],
      "import/no-named-as-default": "off",
      "import/no-named-as-default-member": "off",
      "@typescript-eslint/no-explicit-any": "error",
      "@typescript-eslint/no-unused-vars": ["error", { "argsIgnorePattern": "^_" }],
      "no-restricted-imports": ["error", {
        "patterns": [{
          "regex": "^\\.\\./\\.\\./",
          "message": "Use the ~/ alias instead of deep relative imports (../../ or deeper)."
        }]
      }]
    }
  },
  {
    settings: {
      "import/resolver": {
        typescript: true
      }
    }
  },
  // The route tree is built only in react/app/ (see docs/react-migration.md →
  // Client-Side Router ADR). The app-is-the-top dependency-cruiser rule stops
  // features from importing the tree *file*, but it can't see named imports
  // from a node_module — so this blocks features from building a parallel tree
  // with the router's construction APIs. Features get typed routing from the
  // global Register augmentation instead (Link/useNavigate/getRouteApi), and
  // createLazyRoute stays allowed for the route.lazy.tsx half of each route.
  // Re-declares the deep-relative pattern because flat config replaces (not
  // merges) a rule's options when a later block sets the same rule.
  {
    files: ["app/javascript/react/**"],
    ignores: ["app/javascript/react/app/**"],
    rules: {
      "no-restricted-imports": ["error", {
        "patterns": [{
          "regex": "^\\.\\./\\.\\./",
          "message": "Use the ~/ alias instead of deep relative imports (../../ or deeper)."
        }],
        "paths": [{
          "name": "@tanstack/react-router",
          "importNames": ["createRouter", "createRootRoute", "createRoute"],
          "message": "Route-tree construction lives only in react/app/. Import Link/useNavigate/getRouteApi/createLazyRoute instead — features get typed routing from the Register augmentation."
        }]
      }]
    }
  },
  // TanStack Router rules, scoped to the React tree where all route definitions
  // live (react/app/ tree + features/*/route.tsx). create-route-property-order
  // enforces the createRoute option order TanStack relies on for type inference
  // (a wrong order silently breaks loader/search typing); route-param-names
  // checks path params. Inert until routes exist. Pre-wired so the pilot route
  // doesn't also have to touch tooling.
  {
    files: ["app/javascript/react/**/*.{ts,tsx}"],
    plugins: { "@tanstack/router": pluginRouter },
    rules: {
      "@tanstack/router/create-route-property-order": "error",
      "@tanstack/router/route-param-names": "error",
    },
  },
  // JavaScript tests live in tests/javascript/, mirroring the source path (see
  // tests/CLAUDE.md). Nothing else catches a co-located test: vitest sets no
  // `include`, so its default glob collects *.test.tsx anywhere and the file
  // passes from the wrong place — which is how agents conclude the tree has no
  // tests and start a second, parallel convention. Fail lint instead.
  {
    files: ["app/javascript/**/*.{test,spec}.{ts,tsx}"],
    rules: {
      "no-restricted-syntax": ["error", {
        selector: "Program",
        message: "JavaScript tests live in tests/javascript/, mirroring the source path: app/javascript/react/composites/Foo.tsx → tests/javascript/react/composites/Foo.test.tsx"
      }]
    }
  },
  // styles/ entry points intentionally import from app/styles/ (outside app/javascript/)
  // so they cannot use the ~/ alias and are exempt from the deep-relative-import rule.
  {
    files: ["app/javascript/styles/**"],
    rules: {
      "no-restricted-imports": "off"
    }
  }
)
