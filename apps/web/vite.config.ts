import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath, URL } from "node:url";

export default defineConfig(({ command }) => ({
  plugins: [react(), {
    name: "livingworld-development-session",
    resolveId(id) { return id === "virtual:core-connection" ? "\0virtual:core-connection" : undefined; },
    load(id) {
      if (id !== "\0virtual:core-connection") return;
      // Ephemeral, loopback-only development delivery. Build artifacts contain no session.
      const connection = command === "serve" && process.env.LW_CORE_ENDPOINT ? {
        endpoint: process.env.LW_CORE_ENDPOINT, token: process.env.LW_CORE_TOKEN,
        generation: process.env.LW_CORE_GENERATION,
      } : null;
      return `export default ${JSON.stringify(connection)};`;
    },
  }],
  clearScreen: false,
  resolve: { alias: { "@dreamtalk/api-client": fileURLToPath(new URL("../../packages/api-client/src/index.ts", import.meta.url)) } },
  server: { host: "127.0.0.1", strictPort: true },
}));
