import { sentryVitePlugin } from "@sentry/vite-plugin"
import react from "@vitejs/plugin-react"
import { defineConfig, type Plugin } from "vite"
import tailwindcss from "@tailwindcss/vite"
import path from "path"

// Templates are rendered by the FastAPI backend, not bundled by Vite, so the dev server
// holds no state derived from them — a browser full-reload (not a server restart) is all
// we need when one changes. Replaces vite-plugin-restart, which gated us on its own Vite
// support cadence.
function reloadOnTemplateChange(): Plugin {
  return {
    name: "reload-on-template-change",
    configureServer(server) {
      server.watcher.add("templates/**/*.html.jinja")
      server.watcher.on("change", (file) => {
        if (file.endsWith(".html.jinja")) {
          server.ws.send({ type: "full-reload" })
        }
      })
    },
  }
}

export default defineConfig({
  appType: "custom",
  root: "app",
  base: process.env.VITE_BASE_PATH || "/",
  define: {},
  envDir: "../",
  server: {
    port: parseInt(process.env.VITE_PORT || "5173"),
    cors: {
      origin: "*",
    },
    allowedHosts: true,
    fs: {
      allow: [".."],
    },
    watch: {
      ignored: ["!**/styles/**"],
    },
  },
  resolve: {
    alias: {
      "~": path.resolve(__dirname, "app/javascript"),
    },
    // Force a single React instance. Without this, a dynamically-imported dep
    // that depends on React (e.g. the TanStack Router devtools) can get its own
    // optimized copy, triggering "Invalid hook call / more than one copy of React".
    dedupe: ["react", "react-dom"],
  },
  optimizeDeps: {
    include: ["prosemirror-remark", "prosemirror-unified", "mdast-util-to-markdown", "unified"],
    force: true,
  },
  build: {
    sourcemap: "hidden",
    emptyOutDir: true,
    cssCodeSplit: true,
    manifest: true,
    outDir: "../static/build",
    assetsDir: "",
    rolldownOptions: {
      input: {
        main: path.resolve(__dirname, "app/javascript/main.ts"),
        spa: path.resolve(__dirname, "app/javascript/spa.tsx"),
        style: path.resolve(__dirname, "app/styles/main.css"),
        email: path.resolve(__dirname, "app/styles/email.css"),
      },
    },
  },
  plugins: [
    react({
      include: "**/*.tsx",
    }),
    reloadOnTemplateChange(),
    ...(process.env.SENTRY_AUTH_TOKEN
      ? [
          sentryVitePlugin({
            org: "convictional",
            project: "convictional",
            authToken: process.env.SENTRY_AUTH_TOKEN,
            release: {
              name: process.env.GITHUB_SHA,
              setCommits: {
                commit: process.env.GITHUB_SHA,
                repo: "convictional/convictional",
              },
              inject: false, // Injecting relase ID into the bundle causes it to change needlessly on every build
            },
            sourcemaps: {
              filesToDeleteAfterUpload: ["**/*.js.map"],
            },
          }),
        ]
      : []),
    tailwindcss(),
  ],
})
