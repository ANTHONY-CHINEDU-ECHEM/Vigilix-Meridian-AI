import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The interface talks to the FastAPI service at /api when it is reachable and
// falls back to the in browser engine (src/engine) otherwise.
export default defineConfig({
  plugins: [react()],
  base: "./",
  server: { proxy: { "/api": "http://localhost:8000" } },
  build: { outDir: "dist", assetsDir: "assets", chunkSizeWarningLimit: 900 },
});
