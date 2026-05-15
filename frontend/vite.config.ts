import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    allowedHosts: ["frontend", "host.docker.internal"],
  },
  build: {
    rolldownOptions: {
      output: {
        codeSplitting: {
          groups: [
            { name: "vendor-react", test: /[\\/]node_modules[\\/](react|react-dom|react-router-dom|zustand)[\\/]/ },
            { name: "vendor-charts", test: /[\\/]node_modules[\\/](recharts|d3-|victory-vendor)[\\/]/ },
            { name: "vendor-icons", test: /[\\/]node_modules[\\/]lucide-react[\\/]/ },
          ],
        },
      },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    globals: true,
    css: true,
    testTimeout: 30000,
    include: ["src/**/*.{test,spec}.{ts,tsx}", "tests/**/*.{test,spec}.{ts,tsx}"],
    coverage: {
      provider: "v8",
      reporter: ["text", "json", "html"],
    },
  },
});
