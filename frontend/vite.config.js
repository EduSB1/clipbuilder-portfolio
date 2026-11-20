import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Os ícones do app ficam versionados em public/, servidos pelo Vite tanto no
// dev server quanto no build.
export default defineConfig({
    plugins: [react()],
    build: {
        // Sem sourcemap em produção: não expõe o código original e reduz o
        // tamanho do dist/.
        sourcemap: false,
        // Com as rotas em lazy loading os chunks ficam bem abaixo disso; o
        // aviso volta a ser útil como sinal de regressão.
        chunkSizeWarningLimit: 700,
        rollupOptions: {
            output: {
                // Separa as bibliotecas pesadas do código da aplicação para que
                // uma mudança no app não invalide o cache dos vendors.
                manualChunks: {
                    react: ["react", "react-dom", "react-router-dom"],
                    clerk: ["@clerk/clerk-react", "@clerk/localizations"],
                    editor: ["fabric", "react-image-crop"],
                    export: ["gif.js", "jszip", "marked"],
                    forms: ["react-hook-form", "@hookform/resolvers", "zod"],
                },
            },
        },
    },
    server: {
        port: 5173,
        strictPort: true,
        proxy: {
            "/api": {
                target: "http://127.0.0.1:8000",
                changeOrigin: true,
                rewrite: (p) => p.replace(/^\/api/, ""),
            },
        },
    },
});
