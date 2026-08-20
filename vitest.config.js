import path from "path"

export default {
  resolve: {
    alias: {
      "~": path.resolve(import.meta.dirname, "app/javascript"),
    },
  },
  test: {
    exclude: [
      '**/node_modules/**',
    ],
    environment: 'jsdom',
    setupFiles: ['./vitest.setup.ts'],
    server: {
      deps: {
        inline: ["prosemirror-remark", "prosemirror-unified", "mdast-util-gfm-table", "micromark-extension-gfm-table"],
      },
    },
  },
}
