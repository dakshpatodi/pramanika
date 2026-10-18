import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

// Minimal Vitest setup for the Next.js app.
// - "@/..." mirrors the tsconfig.json path alias ("@/*" -> "./src/*").
// - tsconfig uses "jsx": "preserve" (Next.js compiles JSX itself), so tell
//   the test transformer to use React's automatic runtime instead.
export default defineConfig({
  oxc: { jsx: { runtime: "automatic" } },
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  test: {
    environment: "jsdom",
    include: ["tests/**/*.test.{ts,tsx}"],
    setupFiles: ["./tests/setup.ts"],
  },
});
