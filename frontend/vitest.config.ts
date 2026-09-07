import { defineConfig } from "vitest/config";
import { fileURLToPath } from "node:url";

export default defineConfig({
  resolve: {
    alias: { "@": fileURLToPath(new URL(".", import.meta.url)) },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./tests/setup.ts"],
    css: false,
    include: ["tests/**/*.test.{ts,tsx}"],
    env: {
      NEXT_PUBLIC_ORCA_API_BASE_URL: "http://127.0.0.1:8000",
      NEXT_PUBLIC_ORCA_REQUEST_TIMEOUT_MS: "1000",
      NEXT_PUBLIC_ORCA_POLL_INTERVAL_MS: "10",
    },
  },
});
