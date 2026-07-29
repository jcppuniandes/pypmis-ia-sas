import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    allowedHosts: ["frontend", "host.docker.internal"],
  },
  build: {
    // web-ifc is isolated behind the BIM module lazy import; this limit keeps
    // the intentional geometry engine chunk from hiding real initial-bundle risk.
    chunkSizeWarningLimit: 3600,
    rolldownOptions: {
      output: {
        codeSplitting: {
          groups: [
            { name: "bim-ifc-engine", test: /[\\/]node_modules[\\/]web-ifc[\\/]/ },
            { name: "bim-three", test: /[\\/]node_modules[\\/]three[\\/]/ },
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
    // Tests exercise the full guided control flow, not the narrowed
    // field-validation navigation.
    env: { VITE_FRONTEND_VALIDATION_MODE: "false" },
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
