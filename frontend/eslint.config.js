import js from "@eslint/js";
import globals from "globals";
import react from "eslint-plugin-react";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";

export default [
    { ignores: ["dist/**", "node_modules/**", "public/gif.worker.js"] },
    {
        files: ["**/*.{js,jsx}"],
        languageOptions: {
            ecmaVersion: "latest",
            sourceType: "module",
            globals: { ...globals.browser, ...globals.es2021 },
            parserOptions: { ecmaFeatures: { jsx: true } },
        },
        settings: { react: { version: "detect" } },
        plugins: {
            react,
            "react-hooks": reactHooks,
            "react-refresh": reactRefresh,
        },
        rules: {
            ...js.configs.recommended.rules,
            ...react.configs.recommended.rules,
            ...react.configs["jsx-runtime"].rules,
            ...reactHooks.configs.recommended.rules,

            // O projeto não usa PropTypes nem TypeScript.
            "react/prop-types": "off",
            // `try { ... } catch {}` é o padrão usado para acessos a
            // localStorage/sessionStorage que podem falhar e não têm plano B.
            "no-empty": ["error", { allowEmptyCatch: true }],
            // Textos em português usam aspas com frequência; escapar todas
            // prejudicaria a leitura do JSX sem ganho real.
            "react/no-unescaped-entities": "off",
            // Variáveis intencionalmente ignoradas devem começar com "_".
            "no-unused-vars": [
                "warn",
                { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
            ],
            // Logs de diagnóstico devem ficar atrás de import.meta.env.DEV.
            "no-console": ["warn", { allow: ["warn", "error"] }],
            "react-refresh/only-export-components": [
                "warn",
                { allowConstantExport: true },
            ],
        },
    },
];
