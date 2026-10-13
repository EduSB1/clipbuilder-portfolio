import React, { useEffect, useState } from "react";
import { Sun, Moon } from "lucide-react";

const THEME_STORAGE_KEY = "CLIPBUILDER_DARK";

function getInitialTheme() {
    try {
        return localStorage.getItem(THEME_STORAGE_KEY) !== "0";
    } catch {
        return true;
    }
}

export default function ThemeToggle() {
    const [isDark, setIsDark] = useState(getInitialTheme);

    useEffect(() => {
        document.documentElement.classList.toggle("dark", isDark);
        document.documentElement.classList.toggle("light", !isDark);
        try {
            localStorage.setItem(THEME_STORAGE_KEY, isDark ? "1" : "0");
        } catch {
            // ignore localStorage failures
        }
    }, [isDark]);

    return (
        <button
            type="button"
            onClick={() => setIsDark((value) => !value)}
            className="theme-toggle-minimal"
            aria-label={isDark ? "Ativar modo claro" : "Ativar modo escuro"}
            title={isDark ? "Modo claro" : "Modo escuro"}
        >
            {isDark ? (
                <Sun size={15} className="animate-in fade-in zoom-in duration-300" />
            ) : (
                <Moon size={15} className="animate-in fade-in zoom-in duration-300" />
            )}
        </button>
    );
}
