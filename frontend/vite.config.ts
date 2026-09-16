import { defineConfig } from "vite";

export default defineConfig({
  appType: "mpa",
  server: {
    port: 5173,
    proxy: {
      "/health": "http://127.0.0.1:8765",
      "/ws": {
        target: "ws://127.0.0.1:8765",
        ws: true,
      },
    },
  },
  optimizeDeps: {
    include: ["three", "@pixiv/three-vrm", "@pixiv/three-vrm-animation"],
  },
});
