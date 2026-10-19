import { defineConfig } from "vite";

// 웹 프로토타입 빌드 (0017): web.html 하나를 dist-web/에 낸다. 두뇌 웹 모드(python -m brain.web)가 이 폴더를 내보낸다
export default defineConfig({
  build: {
    outDir: "dist-web",
    emptyOutDir: true,
    rollupOptions: { input: { web: "web.html" } },
  },
});
