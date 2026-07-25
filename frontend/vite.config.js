import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import path from "path";

// Builds the SPA into ../duckies/public/cafe and emits an HTML entry that
// Frappe serves at /cafe. During dev, `proxyOptions` forwards /api to the
// local bench so session cookies work.
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "src") },
  },
  base: "/assets/duckies/cafe/",
  build: {
    outDir: path.resolve(__dirname, "../duckies/public/cafe"),
    emptyOutDir: true,
    target: "es2015",
    sourcemap: true,
    manifest: true,
  },
  server: {
    port: 8081,
    proxy: {
      "^/(api|assets|files|private)": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
