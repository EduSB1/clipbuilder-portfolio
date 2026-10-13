import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Pasta centralizada de ícones (ClipBuilder/Icons/)
const ICONS_DIR = path.resolve(__dirname, "../Icons");

/**
 * Plugin de desenvolvimento: serve os arquivos de Icons/ como estáticos
 * na raiz "/" do dev server.
 *
 * Em produção os ícones já são copiados para public/ pelo Dockerfile
 * antes do `npm run build`, então nenhum hook de build é necessário.
 */
function iconsDevPlugin() {
    return {
        name: "vite-plugin-central-icons-dev",
        apply: "serve", // só ativo no dev server

        configureServer(server) {
            server.middlewares.use((req, res, next) => {
                // Remove query-string (?v=3) e decodifica %20 etc.
                const urlPath = decodeURIComponent(req.url.split("?")[0]);
                const filePath = path.join(ICONS_DIR, urlPath);

                if (fs.existsSync(filePath) && fs.statSync(filePath).isFile()) {
                    const ext = path.extname(filePath).toLowerCase();
                    const mimeMap = {
                        ".png": "image/png",
                        ".ico": "image/x-icon",
                        ".svg": "image/svg+xml",
                        ".webp": "image/webp",
                        ".jpg": "image/jpeg",
                        ".jpeg": "image/jpeg",
                        ".gif": "image/gif",
                    };
                    res.setHeader(
                        "Content-Type",
                        mimeMap[ext] || "application/octet-stream",
                    );
                    fs.createReadStream(filePath).pipe(res);
                    return;
                }
                next();
            });
        },
    };
}

export default defineConfig({
    plugins: [react(), iconsDevPlugin()],
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
