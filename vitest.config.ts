import { defineConfig } from "vitest/config";
export default defineConfig({
  test: { include: ["apps/web/src/**/*.test.tsx", "packages/api-client/src/**/*.test.ts"], environment: "jsdom" },
});
