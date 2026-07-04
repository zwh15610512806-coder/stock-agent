/// <reference types="vitest" />
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    chunkSizeWarningLimit: 1500,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes("node_modules/react") || id.includes("node_modules/react-dom") || id.includes("node_modules/react-router-dom")) {
            return "react";
          }
          if (id.includes("node_modules/@tanstack/react-query") || id.includes("node_modules/zustand")) {
            return "query";
          }
          if (id.includes("node_modules/echarts") || id.includes("node_modules/lightweight-charts")) {
            return "charts";
          }
        },
      },
    },
  },
  server: {
    allowedHosts: true,
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/healthz": "http://127.0.0.1:8000",
    },
  },
  preview: {
    allowedHosts: true,
  },
  test: {
    environment: "jsdom",
    globals: true,
  },
});
