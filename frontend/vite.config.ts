import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // 프론트 dev 서버 → FastAPI 백엔드(:8000)로 프록시
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
